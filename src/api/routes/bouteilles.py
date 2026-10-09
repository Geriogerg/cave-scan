"""Bouteilles d'un inventaire : lister, consulter, corriger, modifier la quantité, valider."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from src.api import schemas
from src.api.dependances import Auteur, BouteilleVerifiee, SessionBase
from src.config.maison import COLONNE_QUANTITE
from src.donnees.modeles import STATUTS_BOUTEILLE
from src.services.consultation import PAR_PAGE_MAX, fiche_bouteille, parcourir_bouteilles
from src.services.relecture import corriger, valider

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
    corriger(base, bouteille.id, demande.champ, demande.valeur, auteur)
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
def valider_bouteille(inventaire_id: int, bouteille: BouteilleVerifiee, base: SessionBase, auteur: Auteur):
    valider(base, bouteille.id, auteur)
    return schemas.depuis_fiche(fiche_bouteille(base, inventaire_id, bouteille.id))
