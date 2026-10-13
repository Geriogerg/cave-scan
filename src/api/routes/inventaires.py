"""Inventaires : créer avec les photos, consulter, piloter l'extraction, valider, exporter."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile

from src.api import schemas
from src.api.dependances import Auteur, SessionBase, Stockage
from src.services.consultation import entete_telechargement, etat_inventaire, exporter_en_octets, recapitulatif
from src.services.cycle_de_vie import archiver, clore, desarchiver, renommer, restaurer, rouvrir, supprimer
from src.services.envoi import creer_inventaire_depuis_envoi
from src.services.inventaires import charger_inventaire, lister_inventaires
from src.services.pilotage import annuler, avancement, lancer, relancer_erreurs
from src.services.relecture import valider_inventaire

routeur = APIRouter(prefix="/inventaires", tags=["Inventaires"], responses=schemas.REPONSES_ERREUR)

EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@routeur.post(
    "", status_code=201, response_model=schemas.InventaireCreeReponse, summary="Créer un inventaire avec ses photos"
)
def creer(
    base: SessionBase,
    stockage: Stockage,
    request: Request,
    nom: Annotated[str, Form(description="Nom de l'inventaire.")],
    maison: Annotated[str, Form(description="Nom de la maison (voir /maisons).")],
    photos: Annotated[list[UploadFile], File(description="Photos JPEG, PNG ou HEIC, dans l'ordre de prise de vue.")],
    photos_par_bouteille: Annotated[
        str | None,
        Form(description="« 2,2,1 » : photos de chaque bouteille, dans l'ordre d'envoi. Sans : une photo par bouteille."),
    ] = None,
):
    cree = creer_inventaire_depuis_envoi(
        base,
        maison,
        nom,
        [(photo.filename or "photo", photo.file) for photo in photos],
        stockage,
        request.app.state.configs,
        photos_par_bouteille=photos_par_bouteille,
    )
    return schemas.depuis_creation(cree)


@routeur.get("", response_model=list[schemas.InventaireResume], summary="Lister les inventaires")
def lister(base: SessionBase, corbeille: Annotated[bool, Query(description="Ceux de la corbeille.")] = False):
    return [schemas.depuis_inventaire(i) for i in lister_inventaires(base, corbeille=corbeille)]


@routeur.get("/{inventaire_id}", response_model=schemas.InventaireDetail, summary="Statut, progression, statistiques")
def consulter(inventaire_id: int, base: SessionBase):
    return schemas.depuis_etat(etat_inventaire(base, inventaire_id))


def _action(base, inventaire_id: int, effectuee: bool, nombre: int | None = None) -> schemas.Action:
    return schemas.Action(
        effectuee=effectuee, nombre=nombre, progression=schemas.depuis_avancement(avancement(base, inventaire_id))
    )


@routeur.post("/{inventaire_id}/lancer", response_model=schemas.Action, summary="Lancer l'extraction (idempotent)")
def lancer_extraction(inventaire_id: int, base: SessionBase):
    return _action(base, inventaire_id, lancer(base, inventaire_id))


@routeur.post("/{inventaire_id}/annuler", response_model=schemas.Action, summary="Annuler l'extraction")
def annuler_extraction(inventaire_id: int, base: SessionBase):
    return _action(base, inventaire_id, annuler(base, inventaire_id))


@routeur.post(
    "/{inventaire_id}/relancer-erreurs",
    response_model=schemas.Action,
    summary="Remettre les bouteilles en erreur à extraire",
)
def relancer(inventaire_id: int, base: SessionBase):
    nombre = relancer_erreurs(base, inventaire_id)
    return _action(base, inventaire_id, nombre > 0, nombre)


@routeur.post(
    "/{inventaire_id}/valider",
    response_model=schemas.Action,
    summary="Constater que toutes les bouteilles ont été validées une par une",
)
def valider(inventaire_id: int, base: SessionBase, auteur: Auteur):
    """Ne valide AUCUNE bouteille (decisions.md 0138) : refusé (409), avec ce qui
    reste à faire, tant qu'une bouteille n'a pas été validée après relecture."""
    nombre = valider_inventaire(base, inventaire_id, auteur)
    return _action(base, inventaire_id, nombre > 0, nombre)


@routeur.get(
    "/{inventaire_id}/recapitulatif",
    response_model=schemas.RecapitulatifReponse,
    summary="Récapitulatif de la relecture : ce qui reste, ce qui a été mesuré",
)
def recapituler(inventaire_id: int, base: SessionBase):
    return schemas.depuis_recapitulatif(recapitulatif(base, inventaire_id))


@routeur.get(
    "/{inventaire_id}/export",
    response_class=Response,
    responses={200: {"content": {EXCEL: {}}, "description": "Le fichier Excel de l'inventaire."}},
    summary="Télécharger l'export Excel",
)
def exporter(inventaire_id: int, base: SessionBase):
    nom, contenu = exporter_en_octets(base, inventaire_id)
    return Response(contenu, media_type=EXCEL, headers={"Content-Disposition": entete_telechargement(nom)})


# --- cycle de vie (session 6 ; decisions.md 0168) -----------------------------------------------


def _detail(base, inventaire_id: int) -> schemas.InventaireDetail:
    return schemas.depuis_etat(etat_inventaire(base, inventaire_id))


@routeur.patch("/{inventaire_id}", response_model=schemas.InventaireDetail, summary="Renommer l'inventaire")
def renommer_l_inventaire(inventaire_id: int, demande: schemas.RenommageDemande, base: SessionBase, auteur: Auteur):
    renommer(base, inventaire_id, demande.nom, auteur)
    return _detail(base, inventaire_id)


@routeur.post("/{inventaire_id}/archiver", response_model=schemas.InventaireDetail, summary="Archiver")
def archiver_l_inventaire(inventaire_id: int, base: SessionBase, auteur: Auteur):
    archiver(base, inventaire_id, auteur)
    return _detail(base, inventaire_id)


@routeur.post("/{inventaire_id}/desarchiver", response_model=schemas.InventaireDetail, summary="Sortir des archives")
def desarchiver_l_inventaire(inventaire_id: int, base: SessionBase, auteur: Auteur):
    desarchiver(base, inventaire_id, auteur)
    return _detail(base, inventaire_id)


@routeur.delete(
    "/{inventaire_id}",
    response_model=schemas.InventaireResume,
    summary="Mettre à la corbeille (rien n'est effacé, l'inventaire se restaure)",
)
def supprimer_l_inventaire(inventaire_id: int, base: SessionBase, auteur: Auteur):
    supprimer(base, inventaire_id, auteur)
    return schemas.depuis_inventaire(charger_inventaire(base, inventaire_id, corbeille=True))


@routeur.post("/{inventaire_id}/restaurer", response_model=schemas.InventaireDetail, summary="Sortir de la corbeille")
def restaurer_l_inventaire(inventaire_id: int, base: SessionBase, auteur: Auteur):
    restaurer(base, inventaire_id, auteur)
    return _detail(base, inventaire_id)


@routeur.post(
    "/{inventaire_id}/clore",
    response_model=schemas.InventaireDetail,
    summary="Clore (lecture seule) : chaque bouteille doit avoir sa ligne ; valider reste facultatif",
)
def clore_l_inventaire(inventaire_id: int, base: SessionBase, auteur: Auteur):
    clore(base, inventaire_id, auteur)
    return _detail(base, inventaire_id)


@routeur.post("/{inventaire_id}/rouvrir", response_model=schemas.InventaireDetail, summary="Rouvrir un inventaire clos")
def rouvrir_l_inventaire(inventaire_id: int, base: SessionBase, auteur: Auteur):
    rouvrir(base, inventaire_id, auteur)
    return _detail(base, inventaire_id)
