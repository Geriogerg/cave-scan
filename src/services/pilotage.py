"""Pilotage de l'extraction d'un inventaire : lancer, relancer les erreurs.

Des actions explicites et IDEMPOTENTES (decisions.md 0111, 0112) : les répéter
ne crée jamais de doublon, puisque seule la file d'attente en base décide de ce
qui est extrait, et qu'une bouteille n'y est réservée qu'une fois.
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from src.donnees.modeles import FicheBouteille, maintenant
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
