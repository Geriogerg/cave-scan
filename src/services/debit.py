"""Limite de débit du modèle, PARTAGÉE par tous les workers (decisions.md 0114).

Deux règles, en base (table `limite_debit`), donc communes à tous les threads et
processus et respectées après un redémarrage :

- espacement : deux appels à un même modèle sont séparés d'au moins
  `espacement_s` — chaque appel réserve son créneau ;
- pause : une limite de débit atteinte (429) suspend TOUT LE MONDE pendant un
  temps, au lieu que chaque worker multiplie ses tentatives.

L'extracteur ne connaît que le Protocol `Limiteur` (src/extract/base.py) ; rien
de ce module n'y est importé.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.donnees.modeles import LimiteDebit, maintenant


class LimiteDebitPartagee:
    """Implémente `Limiteur` sur la base."""

    def __init__(
        self,
        moteur: Engine,
        modele: str,
        espacement_s: float,
        attendre: Callable[[float], None] = time.sleep,
        horloge: Callable[[], datetime] = maintenant,
    ) -> None:
        self.moteur = moteur
        self.modele = modele
        self.espacement = timedelta(seconds=espacement_s)
        self._attendre = attendre
        self._horloge = horloge

    def attendre_mon_tour(self) -> None:
        """Bloque jusqu'au créneau de cet appel, pause commune comprise."""
        while True:
            attente = self._reserver_un_creneau()
            if attente is None:
                return
            self._attendre(attente)

    def _reserver_un_creneau(self) -> float | None:
        """None : le créneau est pris, on peut appeler (après l'attente déjà faite).
        Sinon : secondes à attendre avant de réessayer."""
        with Session(self.moteur) as session:
            self._verrouiller(session)
            ligne = session.get(LimiteDebit, self.modele)
            instant = self._horloge()
            if ligne.pause_jusqu_a is not None and ligne.pause_jusqu_a > instant:
                session.commit()
                return (ligne.pause_jusqu_a - instant).total_seconds()
            creneau = max(instant, ligne.prochain_appel or instant)
            ligne.prochain_appel = creneau + self.espacement
            session.commit()
        attente = (creneau - instant).total_seconds()
        if attente > 0:
            self._attendre(attente)
        return None

    def ralentir(self, pause_s: float) -> None:
        """Limite de débit atteinte : tous les workers attendent `pause_s`."""
        with Session(self.moteur) as session:
            self._verrouiller(session)
            ligne = session.get(LimiteDebit, self.modele)
            fin = self._horloge() + timedelta(seconds=pause_s)
            if ligne.pause_jusqu_a is None or ligne.pause_jusqu_a < fin:
                ligne.pause_jusqu_a = fin
            session.commit()

    def _verrouiller(self, session: Session) -> None:
        """Crée la ligne au besoin ET prend le verrou d'écriture avant toute
        lecture : lire puis écrire sans lui laisserait deux workers prendre le
        même créneau. (PostgreSQL : SELECT … FOR UPDATE.)"""
        session.execute(insert(LimiteDebit).prefix_with("OR IGNORE").values(modele=self.modele))
        session.execute(
            update(LimiteDebit).where(LimiteDebit.modele == self.modele).values(modele=self.modele)
        )


def etat_du_debit(session: Session, modele: str) -> LimiteDebit | None:
    return session.scalar(select(LimiteDebit).where(LimiteDebit.modele == modele))
