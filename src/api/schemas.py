"""Formes des réponses et des requêtes de l'API — et leur mise en forme.

Les fonctions `depuis_*` ne font que recopier ce que les services ont calculé
dans la forme publiée ; aucune décision ici. Jamais de chemin de stockage ni de
métadonnée de photo dans une réponse (decisions.md 0117).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.services.consultation import EtatInventaire, FicheComplete, PageBouteilles, Recapitulatif
from src.services.envoi import ConfigDisponible
from src.services.inventaires import InventaireCree
from src.services.pilotage import Avancement
from src.services.restitution import StatsInventaire


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
    avertissements: list[str]


def depuis_creation(cree: InventaireCree) -> InventaireCreeReponse:
    return InventaireCreeReponse(
        id=cree.inventaire_id,
        nb_bouteilles=cree.nb_bouteilles,
        config_numero=cree.config_numero,
        nouvelle_config=cree.nouvelle_config,
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
    corrections_par_bouteille: dict[str, int] = Field(description="Identifiant -> corrections de l'expert.")
    temps_relecture_total_ms: int = Field(description="Mesuré par l'écran, absences longues exclues.")
    temps_relecture_moyen_ms: float | None
    bouteilles_chronometrees: int
    nb_reanalysees: int
    nb_separees: int
    nb_signalees: int


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
    return InventaireDetail(
        **depuis_inventaire(etat.inventaire).model_dump(),
        config_numero=etat.inventaire.config_version.numero,
        progression=depuis_avancement(etat.avancement),
        statistiques=depuis_stats(etat.stats),
    )


def depuis_stats(s: StatsInventaire) -> Statistiques:
    return Statistiques(
        nb_extractions=s.nb_extractions,
        nb_extractions_en_erreur=s.nb_extractions_en_erreur,
        tokens_par_bouteille=s.tokens_par_bouteille,
        duree_par_extraction_ms=s.duree_par_extraction_ms,
        nb_corrections=s.nb_corrections,
        nb_bouteilles_corrigees=s.nb_bouteilles_corrigees,
        champs_les_plus_corriges=s.champs_les_plus_corriges,
        corrections_par_bouteille=s.corrections_par_bouteille,
        temps_relecture_total_ms=s.temps_relecture_total_ms,
        temps_relecture_moyen_ms=s.temps_relecture_moyen_ms,
        bouteilles_chronometrees=s.bouteilles_chronometrees,
        nb_reanalysees=s.nb_reanalysees,
        nb_separees=s.nb_separees,
        nb_signalees=s.nb_signalees,
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


class EvenementHistorique(BaseModel):
    type: str = Field(description="reanalyse, signalement_paire, signalement_leve, separation (inversion_photos : historique d'avant les groupes de photos)")
    auteur: str
    le: datetime
    detail: Any = None


class LienPhoto(BaseModel):
    numero: int = Field(description="Sa place parmi les photos de la bouteille (« Photo 1 sur 3 »).")
    reduite: str
    originale: str


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
    evenements: list[EvenementHistorique]
    nb_extractions: int
    photos: list[LienPhoto] = Field(description="Toutes ses photos, dans l'ordre de l'expert.")
    precedente_id: int | None
    suivante_id: int | None
    version: str = Field(description="L'état affiché : à renvoyer pour être prévenu d'une modification faite ailleurs.")
    paire_signalee: bool
    separee_de_id: int | None
    temps_relecture_ms: int


def depuis_fiche(fiche: FicheComplete) -> BouteilleDetail:
    b = fiche.bouteille
    base = f"/inventaires/{b.inventaire_id}/photos"

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
        evenements=[
            EvenementHistorique(type=e.type, auteur=e.auteur, le=e.cree_le, detail=e.detail) for e in fiche.evenements
        ],
        nb_extractions=fiche.nb_extractions,
        photos=[
            LienPhoto(numero=numero, reduite=f"{base}/{photo_id}", originale=f"{base}/{photo_id}?taille=originale")
            for numero, photo_id in enumerate(fiche.photos, start=1)
        ],
        precedente_id=fiche.precedente_id,
        suivante_id=fiche.suivante_id,
        version=fiche.version,
        paire_signalee=b.paire_signalee,
        separee_de_id=b.separee_de_id,
        temps_relecture_ms=b.temps_relecture_ms,
    )


VERSION = Field(None, description="Version lue avec la bouteille : refusé (409) si elle a changé depuis.")


class CorrectionDemandee(BaseModel):
    champ: str = Field(examples=["millesime"])
    valeur: str | int | float | None = Field(
        examples=["2015"], description="Liste : code ou libellé. Nombre : « 13,5 » accepté."
    )
    version: str | None = VERSION


class RetourDemande(BaseModel):
    champ: str = Field(examples=["millesime"])
    version: str | None = VERSION


class ValidationDemandee(BaseModel):
    version: str | None = VERSION
    temps_ms: int | None = Field(None, ge=0, description="Temps passé sur la bouteille, absences exclues.")


class SignalementDemande(BaseModel):
    motif: str = Field("", max_length=500, examples=["contre-étiquette d'un autre vin"])


class SeparationDemandee(BaseModel):
    quantite: int = Field(ge=1, examples=[1], description="Exemplaires qui passent dans la nouvelle bouteille.")


class EtatRelecture(BaseModel):
    id: int
    position: int
    identifiant: str
    statut: str


class RecapitulatifReponse(BaseModel):
    inventaire_id: int
    statut: str
    termine: bool
    total: int
    validees: int
    restantes: list[EtatRelecture] = Field(description="À relire : extraites, non validées, non signalées.")
    en_erreur: list[EtatRelecture]
    signalees: list[EtatRelecture]
    pas_encore_extraites: list[EtatRelecture]
    statistiques: Statistiques


def depuis_recapitulatif(recap: Recapitulatif) -> RecapitulatifReponse:
    def etats(liste) -> list[EtatRelecture]:
        return [EtatRelecture(id=e.id, position=e.position, identifiant=e.identifiant, statut=e.statut) for e in liste]

    return RecapitulatifReponse(
        inventaire_id=recap.inventaire.id,
        statut=recap.inventaire.statut,
        termine=recap.termine,
        total=recap.compteurs.total,
        validees=recap.compteurs.validees,
        restantes=etats(recap.restantes),
        en_erreur=etats(recap.en_erreur),
        signalees=etats(recap.signalees),
        pas_encore_extraites=etats(recap.pas_encore_extraites),
        statistiques=depuis_stats(recap.stats),
    )


class QuantiteDemandee(BaseModel):
    quantite: int = Field(ge=1, examples=[2])


# --- dépôt des photos, bouteille par bouteille (sessions 4 et 6) -------------------------------


class BrouillonDemande(BaseModel):
    nom: str = Field(min_length=1, examples=["Vente de printemps"])
    maison: str = Field(examples=["Maison Test"])


class BrouillonReponse(BaseModel):
    id: int
    config_numero: int
    nouvelle_config: bool
    avertissements: list[str]


class PhotoRecueReponse(BaseModel):
    photo_id: int
    bouteille: str = Field(description="La clé de la bouteille qui l'a reçue.")
    numero: int = Field(description="Le numéro de cette bouteille dans le dépôt.")
    rang: int = Field(description="Sa place parmi les photos de la bouteille.")
    nom: str
    deja_recue: bool = Field(description="Déjà reçue : rien n'a été ajouté.")


class SignaturesDemande(BaseModel):
    signatures: list[str] = Field(max_length=2000)


class SignaturesReponse(BaseModel):
    deja_recues: list[str]


class QuantiteDeBouteille(BaseModel):
    quantite: int = Field(ge=1, description="Nombre de bouteilles identiques (« × N »).")


class PhotoApercu(BaseModel):
    id: int
    rang: int
    nom: str
    miniature: str


class BouteilleApercu(BaseModel):
    groupe_id: int
    cle: str | None = Field(description="La clé donnée par l'appareil (absente pour une bouteille créée par coupure).")
    numero: int = Field(description="Sa future position dans l'inventaire.")
    quantite: int
    photos: list[PhotoApercu]


class ApercuReponse(BaseModel):
    inventaire_id: int
    statut: str
    nb_photos: int = Field(description="Photos des bouteilles en attente.")
    deja_formees: int = Field(description="Bouteilles déjà dans l'inventaire.")
    photos_max: int = Field(description="Plafond de photos par bouteille de la maison.")
    prochain_numero: int
    peut_lancer: bool
    anomalies: list[str]
    bouteilles: list[BouteilleApercu] = Field(description="Les bouteilles en attente, pas encore analysées.")


def depuis_photo_recue(recue) -> PhotoRecueReponse:
    return PhotoRecueReponse(
        photo_id=recue.photo_id,
        bouteille=recue.bouteille,
        numero=recue.numero,
        rang=recue.rang,
        nom=recue.nom,
        deja_recue=recue.deja_recue,
    )


def depuis_apercu(apercu) -> ApercuReponse:
    inventaire_id = apercu.inventaire.id
    return ApercuReponse(
        inventaire_id=inventaire_id,
        statut=apercu.inventaire.statut,
        nb_photos=apercu.nb_photos,
        deja_formees=apercu.deja_formees,
        photos_max=apercu.photos_max,
        prochain_numero=apercu.prochain_numero,
        peut_lancer=apercu.peut_lancer,
        anomalies=apercu.anomalies,
        bouteilles=[
            BouteilleApercu(
                groupe_id=b.groupe.id,
                cle=b.groupe.cle,
                numero=b.numero,
                quantite=b.groupe.quantite,
                photos=[
                    PhotoApercu(
                        id=p.id, rang=p.rang, nom=p.nom_origine,
                        miniature=f"/inventaires/{inventaire_id}/photos/{p.id}?taille=miniature",
                    )
                    for p in b.photos
                ],
            )
            for b in apercu.bouteilles
        ],
    )


class Finalisation(BaseModel):
    nb_bouteilles: int
    progression: Progression
