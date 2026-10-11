"""La file d'attente des extractions : le statut des bouteilles, en base.

Pas de Redis ni de Celery (decisions.md 0109) : une bouteille « a_extraire »
d'un inventaire lancé attend ; la réserver la passe « en_cours », au nom d'un
worker, avec un horodatage de vie (`vu_le`) que ce worker rafraîchit pendant le
traitement (0110). Une réservation dont l'horodatage a dépassé le délai
d'abandon est celle d'un worker mort : elle est reprise.

Toute la concurrence tient dans les requêtes de ce module, chacune ATOMIQUE :
une seule instruction conditionnelle, qui ne réussit que pour un seul worker.
Au passage à PostgreSQL, seule `reserver_bouteille` changera (SKIP LOCKED).
"""

from __future__ import annotations

import os
import socket
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.donnees.modeles import Extraction, FicheBouteille, Inventaire, maintenant

DELAI_ABANDON = timedelta(minutes=2)  # sans signe de vie depuis : worker mort
PERIODE_SIGNE_DE_VIE_S = 15.0


def identite_worker(prefixe: str = "worker") -> str:
    """Qui réserve : machine, processus, et un suffixe propre à ce lancement."""
    return f"{prefixe}:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def reserver_bouteille(session: Session, worker: str, inventaire_id: int | None = None) -> int | None:
    """Réserve la prochaine bouteille à extraire d'un inventaire LANCÉ, ou None.

    Une seule instruction UPDATE … RETURNING : SQLite prend le verrou d'écriture
    avant de lire la sous-requête, si bien que deux workers ne peuvent jamais
    obtenir la même bouteille. Ordre : inventaire le plus ancien, puis position.
    """
    session.commit()  # aucune lecture en cours : la réservation voit l'état le plus récent
    prochaine = (
        select(FicheBouteille.id)
        .join(Inventaire, Inventaire.id == FicheBouteille.inventaire_id)
        .where(
            FicheBouteille.statut == "a_extraire",
            FicheBouteille.retiree.is_(False),  # retirée : jamais analysée (0168)
            Inventaire.extraction == "lancee",
            Inventaire.supprime_le.is_(None),  # à la corbeille : jamais traité
        )
        .order_by(Inventaire.id, FicheBouteille.position)
        .limit(1)
    )
    if inventaire_id is not None:
        prochaine = prochaine.where(Inventaire.id == inventaire_id)
    return _reserver(session, worker, FicheBouteille.id == prochaine.scalar_subquery(), ("a_extraire",))


def reserver_cette_bouteille(
    session: Session, bouteille_id: int, worker: str, statuts: tuple[str, ...]
) -> bool:
    """Réserve UNE bouteille précise si son statut le permet (relance forcée,
    ligne de commande). Même garantie d'atomicité."""
    session.commit()
    return _reserver(session, worker, FicheBouteille.id == bouteille_id, statuts) is not None


def _reserver(session: Session, worker: str, cible, statuts: tuple[str, ...]) -> int | None:
    instant = maintenant()
    reservee = session.execute(
        update(FicheBouteille)
        .where(cible, FicheBouteille.statut.in_(statuts))
        .values(statut="en_cours", reservee_par=worker, reservee_le=instant, vu_le=instant)
        .returning(FicheBouteille.id)
        .execution_options(synchronize_session=False)
    ).scalar()
    session.commit()
    if reservee is not None:
        _rafraichir(session, reservee)
    return reservee


def liberer(session: Session, bouteille_id: int, worker: str) -> None:
    """Rend une bouteille non traitée à la file (arrêt propre, Ctrl-C)."""
    session.rollback()
    session.execute(
        update(FicheBouteille)
        .where(
            FicheBouteille.id == bouteille_id,
            FicheBouteille.statut == "en_cours",
            FicheBouteille.reservee_par == worker,
        )
        .values(statut="a_extraire", reservee_par=None, reservee_le=None, vu_le=None)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    _rafraichir(session, bouteille_id)


def signe_de_vie(session: Session, worker: str) -> int:
    """Rafraîchit l'horodatage de vie de toutes les bouteilles que ce worker traite."""
    nombre = session.execute(
        update(FicheBouteille)
        .where(FicheBouteille.statut == "en_cours", FicheBouteille.reservee_par == worker)
        .values(vu_le=maintenant())
        .execution_options(synchronize_session=False)
    ).rowcount
    session.commit()
    return nombre


def _rafraichir(session: Session, bouteille_id: int) -> None:
    """Les UPDATE de ce module contournent l'ORM : une bouteille déjà chargée
    dans la session est relue, pour ne jamais travailler sur un statut périmé."""
    chargee = session.identity_map.get(session.identity_key(FicheBouteille, bouteille_id))
    if chargee is not None:
        session.refresh(chargee)


@contextmanager
def signes_de_vie(
    moteur: Engine, worker: str, periode_s: float = PERIODE_SIGNE_DE_VIE_S
) -> Iterator[None]:
    """Un thread qui rafraîchit les réservations de `worker` pendant le bloc —
    y compris pendant un long appel au modèle. Sa propre session : une session
    ne se partage pas entre threads."""
    arret = threading.Event()

    def battre() -> None:
        with Session(moteur) as session:
            while not arret.wait(periode_s):
                signe_de_vie(session, worker)

    battement = threading.Thread(target=battre, name=f"signes-de-vie {worker}", daemon=True)
    battement.start()
    try:
        yield
    finally:
        arret.set()
        battement.join()


@dataclass(frozen=True)
class Reprises:
    """Ce que la reprise des bouteilles abandonnées a fait."""

    remises_a_extraire: list[int]
    a_conclure: list[int]  # réponse déjà en base : à terminer SANS nouvel appel


def reprendre_les_abandonnees(
    session: Session,
    worker: str,
    delai: timedelta = DELAI_ABANDON,
    inventaire_id: int | None = None,
) -> Reprises:
    """Reprend les bouteilles « en_cours » dont le worker a cessé de donner signe
    de vie (arrêt brutal). Une réservation sans horodatage (antérieure à la
    session 3) compte comme abandonnée.

    Chaque reprise est conditionnelle : si deux workers la tentent, un seul
    l'obtient. Une bouteille dont la réponse était déjà enregistrée après sa
    réservation est renvoyée « à conclure » — le worker termine son
    interprétation, sans rappeler le modèle (decisions.md 0110).
    """
    session.commit()
    limite = maintenant() - delai
    sans_vie = (FicheBouteille.vu_le.is_(None)) | (FicheBouteille.vu_le < limite)
    requete = (
        select(FicheBouteille.id, FicheBouteille.reservee_le)
        .where(FicheBouteille.statut == "en_cours", sans_vie)
        .order_by(FicheBouteille.id)
    )
    if inventaire_id is not None:
        requete = requete.where(FicheBouteille.inventaire_id == inventaire_id)
    abandonnees = session.execute(requete).all()
    session.commit()

    remises, a_conclure = [], []
    for bouteille_id, reservee_le in abandonnees:
        # Prendre la main sur la réservation, sans toucher `reservee_le` : c'est
        # lui qui dit si la réponse enregistrée appartient à CETTE réservation.
        prise = session.execute(
            update(FicheBouteille)
            .where(FicheBouteille.id == bouteille_id, FicheBouteille.statut == "en_cours", sans_vie)
            .values(reservee_par=worker, vu_le=maintenant())
            .returning(FicheBouteille.id)
            .execution_options(synchronize_session=False)
        ).scalar()
        session.commit()
        if prise is None:
            continue  # un autre worker l'a reprise
        if _reponse_deja_recue(session, bouteille_id, reservee_le):
            _rafraichir(session, bouteille_id)
            a_conclure.append(bouteille_id)
        else:
            liberer(session, bouteille_id, worker)
            remises.append(bouteille_id)
    return Reprises(remises_a_extraire=remises, a_conclure=a_conclure)


def _reponse_deja_recue(session: Session, bouteille_id: int, reservee_le: datetime | None) -> bool:
    if reservee_le is None:
        return False
    return (
        session.scalar(
            select(Extraction.id)
            .where(
                Extraction.bouteille_id == bouteille_id,
                Extraction.erreur.is_(None),
                Extraction.cree_le >= reservee_le,
            )
            .limit(1)
        )
        is not None
    )


def reservations_de(session: Session, worker: str) -> list[int]:
    return list(
        session.scalars(
            select(FicheBouteille.id).where(
                FicheBouteille.statut == "en_cours", FicheBouteille.reservee_par == worker
            )
        )
    )
