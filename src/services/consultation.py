"""Ce que les écrans consultent : inventaires, bouteilles paginées, fiche
d'une bouteille, export en mémoire.

Fonctions de service comme les autres (decisions.md 0080, 0118) : l'API ne fait
que les appeler et mettre leur résultat en forme. Rien n'est calculé dans une
route.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.donnees.modeles import Correction, FicheBouteille, Inventaire
from src.export.excel_writer import a_relire
from src.services.extraction import BouteilleIntrouvable, extractions_de
from src.services.inventaires import charger_inventaire, config_figee
from src.services.pilotage import Avancement, avancement
from src.services.relecture import (
    CHAMP_STATUT,
    champs_corrigeables,
    corrections_de,
    valeur_courante,
    valeurs_courantes,
    valeurs_modele,
)
from src.services.restitution import StatsInventaire, exporter, stats_inventaire

PAR_PAGE_MAX = 200


# --- inventaires -----------------------------------------------------------------------------


@dataclass(frozen=True)
class EtatInventaire:
    inventaire: Inventaire
    avancement: Avancement
    stats: StatsInventaire


def etat_inventaire(session: Session, inventaire_id: int) -> EtatInventaire:
    """Statut, progression et statistiques d'un inventaire."""
    return EtatInventaire(
        inventaire=charger_inventaire(session, inventaire_id),
        avancement=avancement(session, inventaire_id),
        stats=stats_inventaire(session, inventaire_id),
    )


def exporter_en_octets(session: Session, inventaire_id: int) -> tuple[str, bytes]:
    """L'Excel de l'inventaire, en mémoire : (nom de fichier proposé, contenu)."""
    inventaire = charger_inventaire(session, inventaire_id)
    with tempfile.TemporaryDirectory(prefix="cave-scan-export-") as dossier:
        chemin = exporter(session, inventaire_id, Path(dossier) / "export.xlsx")
        contenu = Path(chemin).read_bytes()
    return f"inventaire_{inventaire.id}.xlsx", contenu


# --- bouteilles ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumeBouteille:
    id: int
    position: int
    identifiant: str
    statut: str
    quantite: int
    a_verifier: bool
    domaine: Any
    appellation: Any
    millesime: Any


@dataclass(frozen=True)
class PageBouteilles:
    total: int
    page: int
    par_page: int
    bouteilles: list[ResumeBouteille] = field(default_factory=list)


def parcourir_bouteilles(
    session: Session,
    inventaire_id: int,
    statut: str | None = None,
    a_verifier: bool | None = None,
    page: int = 1,
    par_page: int = 50,
) -> PageBouteilles:
    """Les bouteilles d'un inventaire, dans l'ordre, filtrées puis paginées.

    « À vérifier » est la MÊME règle que le surlignage de l'export (`a_relire`,
    decisions.md 0055) : l'écran et l'Excel disent la même chose.
    """
    inventaire = charger_inventaire(session, inventaire_id)
    config = config_figee(inventaire)
    resumes = []
    for bouteille in inventaire.bouteilles:
        if statut is not None and bouteille.statut != statut:
            continue
        valeurs = valeurs_courantes(session, bouteille.id)
        douteuse = a_relire(valeurs, config)
        if a_verifier is not None and douteuse != a_verifier:
            continue
        resumes.append(
            ResumeBouteille(
                id=bouteille.id,
                position=bouteille.position,
                identifiant=bouteille.identifiant,
                statut=bouteille.statut,
                quantite=valeurs.quantite,
                a_verifier=douteuse,
                domaine=valeur_courante(valeurs, "domaine"),
                appellation=valeur_courante(valeurs, "appellation"),
                millesime=valeur_courante(valeurs, "millesime"),
            )
        )
    debut = (page - 1) * par_page
    return PageBouteilles(total=len(resumes), page=page, par_page=par_page, bouteilles=resumes[debut : debut + par_page])


def bouteille_de(session: Session, inventaire_id: int, bouteille_id: int) -> FicheBouteille:
    """La bouteille, si et seulement si elle appartient à CET inventaire."""
    charger_inventaire(session, inventaire_id)
    bouteille = session.get(FicheBouteille, bouteille_id)
    if bouteille is None or bouteille.inventaire_id != inventaire_id:
        raise BouteilleIntrouvable(f"Aucune bouteille n°{bouteille_id} dans l'inventaire n°{inventaire_id}.")
    return bouteille


@dataclass(frozen=True)
class FicheComplete:
    """Tout ce que la future relecture affiche pour une bouteille."""

    bouteille: FicheBouteille
    valeurs_courantes: dict[str, Any]
    valeurs_modele: dict[str, Any]
    champs_corriges: list[str]
    champs_a_verifier: list[str]
    a_verifier: bool
    notes: Any
    historique: list[Correction]
    nb_extractions: int
    photo_etiquette_id: int
    photo_contre_id: int | None
    precedente_id: int | None
    suivante_id: int | None


def fiche_bouteille(session: Session, inventaire_id: int, bouteille_id: int) -> FicheComplete:
    bouteille = bouteille_de(session, inventaire_id, bouteille_id)
    config = config_figee(bouteille.inventaire)
    courantes, modele = valeurs_courantes(session, bouteille.id), valeurs_modele(session, bouteille.id)
    champs = champs_corrigeables(config)
    historique = corrections_de(bouteille)
    voisines = session.execute(
        select(
            select(func.max(FicheBouteille.id))
            .where(FicheBouteille.inventaire_id == inventaire_id, FicheBouteille.position == bouteille.position - 1)
            .scalar_subquery(),
            select(func.max(FicheBouteille.id))
            .where(FicheBouteille.inventaire_id == inventaire_id, FicheBouteille.position == bouteille.position + 1)
            .scalar_subquery(),
        )
    ).one()
    return FicheComplete(
        bouteille=bouteille,
        valeurs_courantes={champ: valeur_courante(courantes, champ) for champ in champs},
        valeurs_modele={
            champ: valeur_courante(modele, champ)
            for champ in champs
            if not _saisie_expert(config, champ)  # le modèle ne remplit jamais ces colonnes
        },
        champs_corriges=sorted({c.champ for c in historique if c.champ != CHAMP_STATUT}),
        champs_a_verifier=list(modele.champs_a_verifier),
        a_verifier=a_relire(courantes, config),
        notes=modele.notes,
        historique=historique,
        nb_extractions=len(extractions_de(bouteille)),
        photo_etiquette_id=bouteille.photo_etiquette_id,
        photo_contre_id=bouteille.photo_contre_id,
        precedente_id=voisines[0],
        suivante_id=voisines[1],
    )


def _saisie_expert(config, champ: str) -> bool:
    colonne = config.colonne(champ)
    return colonne is not None and colonne.source == "expert"


def tableau_des_inventaires(session: Session) -> list[tuple[Inventaire, Avancement]]:
    """L'accueil : chaque inventaire avec son avancement, le plus récent d'abord."""
    from src.services.inventaires import lister_inventaires

    return [(inventaire, avancement(session, inventaire.id)) for inventaire in reversed(lister_inventaires(session))]
