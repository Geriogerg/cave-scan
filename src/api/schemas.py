"""Formes des réponses et des requêtes de l'API — et leur mise en forme.

Les fonctions `depuis_*` ne font que recopier ce que les services ont calculé
dans la forme publiée ; aucune décision ici. Jamais de chemin de stockage ni de
métadonnée de photo dans une réponse (decisions.md 0117).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.services.consultation import EtatInventaire, FicheComplete, PageBouteilles
from src.services.envoi import ConfigDisponible
from src.services.inventaires import InventaireCree
from src.services.pilotage import Avancement


class Erreur(BaseModel):
    code: str = Field(description="Code stable, pour les écrans.")
    message: str = Field(description="Message en français, pour l'expert.")
    detail: Any = None


REPONSES_ERREUR = {
    404: {"model": Erreur, "description": "Introuvable"},
    409: {"model": Erreur, "description": "Action impossible dans l'état actuel"},
    422: {"model": Erreur, "description": "Saisie ou envoi refusé"},
}


class Maison(BaseModel):
    maison: str
    fichier: str
    version_declaree: int | None
    config_numero: int | None = Field(description="Version enregistrée ; vide si jamais utilisée.")
    erreur: str | None = None


def depuis_config(config: ConfigDisponible) -> Maison:
    return Maison(**config.__dict__)


class InventaireCreeReponse(BaseModel):
    id: int
    nb_bouteilles: int
    config_numero: int
    nouvelle_config: bool
    tri: str
    sans_date: list[str]
    avertissements: list[str]


def depuis_creation(cree: InventaireCree) -> InventaireCreeReponse:
    return InventaireCreeReponse(
        id=cree.inventaire_id,
        nb_bouteilles=cree.nb_bouteilles,
        config_numero=cree.config_numero,
        nouvelle_config=cree.nouvelle_config,
        tri=cree.tri,
        sans_date=cree.sans_date,
        avertissements=cree.avertissements,
    )


class Progression(BaseModel):
    extraction: str = Field(description="non_lancee, lancee, annulee ou arretee")
    motif_arret: str | None
    par_statut: dict[str, int]
    total: int
    restantes: int
    terminee: bool
    tokens_entree: int
    tokens_sortie: int
    lancee_le: datetime | None
    ecoule_s: float | None
    restant_estime_s: float | None


class Statistiques(BaseModel):
    nb_extractions: int
    nb_extractions_en_erreur: int
    tokens_par_bouteille: tuple[float, float] | None
    duree_par_extraction_ms: float | None
    nb_corrections: int
    nb_bouteilles_corrigees: int
    champs_les_plus_corriges: list[tuple[str, int]]


class InventaireResume(BaseModel):
    id: int
    nom: str
    maison: str
    statut: str
    extraction: str
    nb_bouteilles: int
    cree_le: datetime


class InventaireDetail(InventaireResume):
    config_numero: int
    progression: Progression
    statistiques: Statistiques


def depuis_inventaire(inventaire) -> InventaireResume:
    return InventaireResume(
        id=inventaire.id,
        nom=inventaire.nom,
        maison=inventaire.maison.nom,
        statut=inventaire.statut,
        extraction=inventaire.extraction,
        nb_bouteilles=len(inventaire.bouteilles),
        cree_le=inventaire.cree_le,
    )


def depuis_avancement(a: Avancement) -> Progression:
    return Progression(
        extraction=a.extraction,
        motif_arret=a.motif_arret,
        par_statut=a.par_statut,
        total=a.total,
        restantes=a.restantes,
        terminee=a.terminee,
        tokens_entree=a.tokens_entree,
        tokens_sortie=a.tokens_sortie,
        lancee_le=a.lancee_le,
        ecoule_s=a.ecoule_s,
        restant_estime_s=a.restant_estime_s,
    )


def depuis_etat(etat: EtatInventaire) -> InventaireDetail:
    s = etat.stats
    return InventaireDetail(
        **depuis_inventaire(etat.inventaire).model_dump(),
        config_numero=etat.inventaire.config_version.numero,
        progression=depuis_avancement(etat.avancement),
        statistiques=Statistiques(
            nb_extractions=s.nb_extractions,
            nb_extractions_en_erreur=s.nb_extractions_en_erreur,
            tokens_par_bouteille=s.tokens_par_bouteille,
            duree_par_extraction_ms=s.duree_par_extraction_ms,
            nb_corrections=s.nb_corrections,
            nb_bouteilles_corrigees=s.nb_bouteilles_corrigees,
            champs_les_plus_corriges=s.champs_les_plus_corriges,
        ),
    )


class Action(BaseModel):
    """Résultat d'une action de pilotage."""

    effectuee: bool = Field(description="False si rien n'a changé (action idempotente).")
    nombre: int | None = None
    progression: Progression | None = None


class BouteilleResume(BaseModel):
    id: int
    position: int
    identifiant: str
    statut: str
    quantite: int
    a_verifier: bool
    domaine: Any
    appellation: Any
    millesime: Any


class PageBouteillesReponse(BaseModel):
    total: int
    page: int
    par_page: int
    bouteilles: list[BouteilleResume]


def depuis_page(page: PageBouteilles) -> PageBouteillesReponse:
    return PageBouteillesReponse(
        total=page.total,
        page=page.page,
        par_page=page.par_page,
        bouteilles=[BouteilleResume(**b.__dict__) for b in page.bouteilles],
    )


class CorrectionHistorique(BaseModel):
    champ: str
    ancienne_valeur: Any
    nouvelle_valeur: Any
    auteur: str
    le: datetime


class LiensPhotos(BaseModel):
    etiquette: str
    etiquette_originale: str
    contre_etiquette: str | None
    contre_etiquette_originale: str | None


class BouteilleDetail(BaseModel):
    id: int
    inventaire_id: int
    position: int
    identifiant: str
    statut: str
    quantite: int
    a_verifier: bool
    valeurs_courantes: dict[str, Any] = Field(description="Modèle + dernière correction de chaque champ.")
    valeurs_modele: dict[str, Any] = Field(description="Ce que le modèle a lu, jamais modifié.")
    champs_corriges: list[str]
    champs_a_verifier: list[str] = Field(description="Doutes signalés par le modèle.")
    notes: Any
    historique: list[CorrectionHistorique]
    nb_extractions: int
    photos: LiensPhotos
    precedente_id: int | None
    suivante_id: int | None


def depuis_fiche(fiche: FicheComplete) -> BouteilleDetail:
    b = fiche.bouteille
    base = f"/inventaires/{b.inventaire_id}/photos"

    def lien(photo_id: int | None, originale: bool) -> str | None:
        if photo_id is None:
            return None
        return f"{base}/{photo_id}" + ("?taille=originale" if originale else "")

    return BouteilleDetail(
        id=b.id,
        inventaire_id=b.inventaire_id,
        position=b.position,
        identifiant=b.identifiant,
        statut=b.statut,
        quantite=b.quantite,
        a_verifier=fiche.a_verifier,
        valeurs_courantes=fiche.valeurs_courantes,
        valeurs_modele=fiche.valeurs_modele,
        champs_corriges=fiche.champs_corriges,
        champs_a_verifier=fiche.champs_a_verifier,
        notes=fiche.notes,
        historique=[
            CorrectionHistorique(
                champ=c.champ,
                ancienne_valeur=c.ancienne_valeur,
                nouvelle_valeur=c.nouvelle_valeur,
                auteur=c.auteur,
                le=c.cree_le,
            )
            for c in fiche.historique
        ],
        nb_extractions=fiche.nb_extractions,
        photos=LiensPhotos(
            etiquette=lien(fiche.photo_etiquette_id, False),
            etiquette_originale=lien(fiche.photo_etiquette_id, True),
            contre_etiquette=lien(fiche.photo_contre_id, False),
            contre_etiquette_originale=lien(fiche.photo_contre_id, True),
        ),
        precedente_id=fiche.precedente_id,
        suivante_id=fiche.suivante_id,
    )


class CorrectionDemandee(BaseModel):
    champ: str = Field(examples=["millesime"])
    valeur: str | int | float | None = Field(
        examples=["2015"], description="Liste : code ou libellé. Nombre : « 13,5 » accepté."
    )


class QuantiteDemandee(BaseModel):
    quantite: int = Field(ge=1, examples=[2])
