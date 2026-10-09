"""Pilotage de l'extraction d'un inventaire : lancer, annuler, relancer les
erreurs, suivre l'avancement.

Des actions explicites et IDEMPOTENTES (decisions.md 0111, 0112) : les répéter
ne crée jamais de doublon, puisque seule la file d'attente en base décide de ce
qui est extrait, et qu'une bouteille n'y est réservée qu'une fois.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.donnees.modeles import STATUTS_BOUTEILLE, Extraction, FicheBouteille, maintenant
from src.services.inventaires import charger_inventaire


def lancer(session: Session, inventaire_id: int) -> bool:
    """Ouvre l'inventaire au worker. Renvoie False s'il était déjà lancé."""
    inventaire = charger_inventaire(session, inventaire_id)
    if inventaire.extraction == "lancee":
        return False
    inventaire.extraction = "lancee"
    inventaire.extraction_lancee_le = maintenant()
    inventaire.motif_arret = None
    session.commit()
    return True


def relancer_erreurs(session: Session, inventaire_id: int) -> int:
    """Remet les bouteilles en erreur « à extraire ». Renvoie leur nombre."""
    charger_inventaire(session, inventaire_id)
    nombre = session.execute(
        update(FicheBouteille)
        .where(FicheBouteille.inventaire_id == inventaire_id, FicheBouteille.statut == "erreur")
        .values(statut="a_extraire")
        .execution_options(synchronize_session="fetch")
    ).rowcount
    session.commit()
    return nombre


def annuler(session: Session, inventaire_id: int) -> bool:
    """Plus aucune bouteille de l'inventaire n'est réservée : celles pas encore
    commencées restent « à extraire » sans être traitées, celles en cours
    terminent proprement. Renvoie False si l'inventaire n'était pas lancé."""
    inventaire = charger_inventaire(session, inventaire_id)
    if inventaire.extraction != "lancee":
        return False
    inventaire.extraction = "annulee"
    session.commit()
    return True


@dataclass(frozen=True)
class Avancement:
    """Où en est l'extraction d'un inventaire — tout est lu en base."""

    inventaire_id: int
    extraction: str  # non_lancee, lancee, annulee, arretee
    motif_arret: str | None
    par_statut: dict[str, int]
    total: int
    restantes: int  # à extraire ou en cours
    tokens_entree: int
    tokens_sortie: int
    lancee_le: datetime | None
    ecoule_s: float | None
    restant_estime_s: float | None  # au rythme observé depuis le lancement

    @property
    def terminee(self) -> bool:
        return self.restantes == 0


def avancement(session: Session, inventaire_id: int) -> Avancement:
    session.expire_all()  # le worker écrit ailleurs : relire l'état réel
    inventaire = charger_inventaire(session, inventaire_id)
    statuts = Counter(b.statut for b in inventaire.bouteilles)
    ids = [b.id for b in inventaire.bouteilles]
    tokens = session.execute(
        select(func.coalesce(func.sum(Extraction.tokens_entree), 0), func.coalesce(func.sum(Extraction.tokens_sortie), 0))
        .where(Extraction.bouteille_id.in_(ids))
    ).one()
    restantes = statuts["a_extraire"] + statuts["en_cours"]

    ecoule = estime = None
    if inventaire.extraction_lancee_le is not None:
        ecoule = (maintenant() - inventaire.extraction_lancee_le).total_seconds()
        faites = session.scalar(
            select(func.count(func.distinct(Extraction.bouteille_id))).where(
                Extraction.bouteille_id.in_(ids), Extraction.cree_le >= inventaire.extraction_lancee_le
            )
        )
        if faites and restantes:
            estime = ecoule * restantes / faites
        elif not restantes:
            estime = 0.0
    return Avancement(
        inventaire_id=inventaire.id,
        extraction=inventaire.extraction,
        motif_arret=inventaire.motif_arret,
        par_statut={statut: statuts.get(statut, 0) for statut in STATUTS_BOUTEILLE},
        total=len(ids),
        restantes=restantes,
        tokens_entree=tokens[0],
        tokens_sortie=tokens[1],
        lancee_le=inventaire.extraction_lancee_le,
        ecoule_s=ecoule,
        restant_estime_s=estime,
    )
