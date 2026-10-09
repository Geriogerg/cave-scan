"""Inventaires : créer avec les photos, consulter, piloter l'extraction, valider, exporter."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, Response, UploadFile

from src.api import schemas
from src.api.dependances import Auteur, SessionBase, Stockage
from src.services.consultation import etat_inventaire, exporter_en_octets
from src.services.envoi import creer_inventaire_depuis_envoi
from src.services.inventaires import lister_inventaires
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
    photos: Annotated[list[UploadFile], File(description="Photos JPEG ou PNG, dans l'ordre de prise de vue.")],
    sans_contre: Annotated[bool, Form(description="Étiquettes seules : une photo par bouteille.")] = False,
):
    cree = creer_inventaire_depuis_envoi(
        base,
        maison,
        nom,
        [(photo.filename or "photo", photo.file) for photo in photos],
        stockage,
        request.app.state.configs,
        sans_contre=sans_contre,
    )
    return schemas.depuis_creation(cree)


@routeur.get("", response_model=list[schemas.InventaireResume], summary="Lister les inventaires")
def lister(base: SessionBase):
    return [schemas.depuis_inventaire(i) for i in lister_inventaires(base)]


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
    "/{inventaire_id}/valider", response_model=schemas.Action, summary="Valider toutes les bouteilles extraites"
)
def valider(inventaire_id: int, base: SessionBase, auteur: Auteur):
    nombre = valider_inventaire(base, inventaire_id, auteur)
    return _action(base, inventaire_id, nombre > 0, nombre)


@routeur.get(
    "/{inventaire_id}/export",
    response_class=Response,
    responses={200: {"content": {EXCEL: {}}, "description": "Le fichier Excel de l'inventaire."}},
    summary="Télécharger l'export Excel",
)
def exporter(inventaire_id: int, base: SessionBase):
    nom, contenu = exporter_en_octets(base, inventaire_id)
    return Response(contenu, media_type=EXCEL, headers={"Content-Disposition": f'attachment; filename="{nom}"'})
