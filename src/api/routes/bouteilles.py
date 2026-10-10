"""Bouteilles d'un inventaire : lister, consulter, corriger, modifier la quantité,
valider — et les cas particuliers de la relecture (session 5) : revenir à la
valeur du modèle, réanalyser, inverser les photos, signaler une paire, séparer.

Mêmes fonctions de service que l'écran de relecture ; une `version` lue avec la
bouteille peut être renvoyée pour être prévenu (409) d'une modification faite
ailleurs (decisions.md 0142)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from src.api import schemas
from src.api.dependances import Auteur, BouteilleVerifiee, SessionBase
from src.config.maison import COLONNE_QUANTITE
from src.donnees.modeles import STATUTS_BOUTEILLE
from src.services.cas_particuliers import inverser_photos, lever_signalement, reanalyser, separer, signaler_paire
from src.services.consultation import PAR_PAGE_MAX, fiche_bouteille, parcourir_bouteilles
from src.services.relecture import corriger, revenir_a_la_valeur_du_modele, valider, verifier_version

routeur = APIRouter(
    prefix="/inventaires/{inventaire_id}/bouteilles", tags=["Bouteilles"], responses=schemas.REPONSES_ERREUR
)

FILTRE_STATUT = "^(" + "|".join(STATUTS_BOUTEILLE) + ")$"


@routeur.get("", response_model=schemas.PageBouteillesReponse, summary="Lister les bouteilles (paginé, filtrable)")
def lister(
    inventaire_id: int,
    base: SessionBase,
    statut: Annotated[str | None, Query(description=" / ".join(STATUTS_BOUTEILLE), pattern=FILTRE_STATUT)] = None,
    a_verifier: Annotated[bool | None, Query(description="Seulement celles à vérifier (true) ou non (false).")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    par_page: Annotated[int, Query(ge=1, le=PAR_PAGE_MAX)] = 50,
):
    return schemas.depuis_page(parcourir_bouteilles(base, inventaire_id, statut, a_verifier, page, par_page))


@routeur.get("/{bouteille_id}", response_model=schemas.BouteilleDetail, summary="Consulter une bouteille")
def consulter(inventaire_id: int, bouteille: BouteilleVerifiee, base: SessionBase):
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


@routeur.post("/{bouteille_id}/corrections", response_model=schemas.BouteilleDetail, summary="Corriger un champ")
def corriger_champ(
    inventaire_id: int,
    bouteille: BouteilleVerifiee,
    demande: schemas.CorrectionDemandee,
    base: SessionBase,
    auteur: Auteur,
):
    verifier_version(base, bouteille.id, demande.version)
    corriger(base, bouteille.id, demande.champ, demande.valeur, auteur)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


@routeur.post(
    "/{bouteille_id}/revenir", response_model=schemas.BouteilleDetail, summary="Revenir à la valeur lue par le modèle"
)
def revenir(
    inventaire_id: int,
    bouteille: BouteilleVerifiee,
    demande: schemas.RetourDemande,
    base: SessionBase,
    auteur: Auteur,
):
    revenir_a_la_valeur_du_modele(base, bouteille.id, demande.champ, auteur, demande.version)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


@routeur.put("/{bouteille_id}/quantite", response_model=schemas.BouteilleDetail, summary="Modifier la quantité")
def modifier_quantite(
    inventaire_id: int,
    bouteille: BouteilleVerifiee,
    demande: schemas.QuantiteDemandee,
    base: SessionBase,
    auteur: Auteur,
):
    corriger(base, bouteille.id, COLONNE_QUANTITE, demande.quantite, auteur)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


@routeur.post("/{bouteille_id}/valider", response_model=schemas.BouteilleDetail, summary="Valider la bouteille")
def valider_bouteille(
    inventaire_id: int,
    bouteille: BouteilleVerifiee,
    base: SessionBase,
    auteur: Auteur,
    demande: schemas.ValidationDemandee | None = None,
):
    demande = demande or schemas.ValidationDemandee()
    verifier_version(base, bouteille.id, demande.version)
    valider(base, bouteille.id, auteur, demande.temps_ms)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


# --- cas particuliers (session 5) ----------------------------------------------------------


@routeur.post(
    "/{bouteille_id}/reanalyser",
    response_model=schemas.BouteilleDetail,
    summary="Réanalyser la bouteille (le worker l'extrait de nouveau)",
)
def demander_reanalyse(inventaire_id: int, bouteille: BouteilleVerifiee, base: SessionBase, auteur: Auteur):
    reanalyser(base, bouteille.id, auteur)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


@routeur.post(
    "/{bouteille_id}/inverser-photos", response_model=schemas.BouteilleDetail, summary="Inverser étiquette et contre-étiquette"
)
def inverser(inventaire_id: int, bouteille: BouteilleVerifiee, base: SessionBase, auteur: Auteur):
    inverser_photos(base, bouteille.id, auteur)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


@routeur.post(
    "/{bouteille_id}/signalement", response_model=schemas.BouteilleDetail, summary="Signaler un problème de paire"
)
def signaler(
    inventaire_id: int,
    bouteille: BouteilleVerifiee,
    base: SessionBase,
    auteur: Auteur,
    demande: schemas.SignalementDemande | None = None,
):
    signaler_paire(base, bouteille.id, auteur, (demande or schemas.SignalementDemande()).motif)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


@routeur.delete(
    "/{bouteille_id}/signalement", response_model=schemas.BouteilleDetail, summary="Lever le signalement de paire"
)
def lever(inventaire_id: int, bouteille: BouteilleVerifiee, base: SessionBase, auteur: Auteur):
    lever_signalement(base, bouteille.id, auteur)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))


@routeur.post(
    "/{bouteille_id}/separer",
    status_code=201,
    response_model=schemas.BouteilleDetail,
    summary="Séparer des exemplaires d'état différent (renvoie la nouvelle bouteille)",
)
def separer_exemplaires(
    inventaire_id: int,
    bouteille: BouteilleVerifiee,
    demande: schemas.SeparationDemandee,
    base: SessionBase,
    auteur: Auteur,
):
    nouvelle = separer(base, bouteille.id, demande.quantite, auteur)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, nouvelle.id))
