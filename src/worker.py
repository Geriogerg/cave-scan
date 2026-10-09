"""Le worker : extrait en arrière-plan, plusieurs bouteilles à la fois.

Une boucle, sans logique métier propre (CLAUDE.md, « API et tâches de fond ») :

1. reprendre les bouteilles abandonnées par un worker mort (file_attente) ;
2. réserver, de façon atomique, jusqu'à `simultanees` bouteilles d'inventaires
   lancés ;
3. les extraire dans un pool de threads, chacune avec SA session, par le même
   `traiter_reservee` que la ligne de commande ;
4. pendant ce temps, un thread rafraîchit l'horodatage de vie des réservations.

Le travail en attente vit dans la base, jamais ici : tuer ce processus ne perd
rien, et un autre worker reprend ce qu'il traitait (decisions.md 0109-0115). La
seule chose en mémoire est la liste des tâches qu'il exécute en ce moment.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.config.maison import ConfigMaison
from src.donnees.modeles import FicheBouteille, Inventaire
from src.extract.base import Extractor
from src.services.extraction import (
    ExtractionArretee,
    charger_bouteille,
    conclure_sans_appel,
    traiter_reservee,
)
from src.services.file_attente import (
    DELAI_ABANDON,
    PERIODE_SIGNE_DE_VIE_S,
    identite_worker,
    liberer,
    reprendre_les_abandonnees,
    reserver_bouteille,
    signes_de_vie,
)
from src.services.inventaires import config_figee

journal = logging.getLogger("cave_scan.worker")

SIMULTANEES_DEFAUT = 4  # prudent : le guide le demande, la limite de débit fait le reste

# Fabrique l'extracteur d'une bouteille, avec la config FIGÉE de son inventaire.
FabriqueExtracteur = Callable[[ConfigMaison], Extractor]


@dataclass(frozen=True)
class ReglagesWorker:
    simultanees: int = SIMULTANEES_DEFAUT
    delai_abandon: timedelta = DELAI_ABANDON
    periode_vie_s: float = PERIODE_SIGNE_DE_VIE_S
    attente_s: float = 2.0  # file vide : on regarde de nouveau dans…


class Worker:
    def __init__(
        self,
        moteur: Engine,
        stockage: Path,
        fabrique: FabriqueExtracteur,
        reglages: ReglagesWorker = ReglagesWorker(),
        nom: str | None = None,
    ) -> None:
        if reglages.simultanees < 1:
            raise ValueError("Au moins une extraction simultanée.")
        self.moteur = moteur
        self.stockage = stockage
        self.fabrique = fabrique
        self.reglages = reglages
        self.nom = nom or identite_worker()

    def tourner(self, arret: threading.Event | None = None, jusqu_a_vide: bool = False) -> None:
        """Tourne jusqu'à `arret` — ou, avec `jusqu_a_vide`, jusqu'à ce qu'il n'y ait
        plus rien à extraire ni en cours dans aucun inventaire lancé. Un arrêt
        demandé laisse terminer les extractions commencées."""
        arret = arret or threading.Event()
        taches: set[Future] = set()
        journal.info("Worker %s : %d extraction(s) simultanée(s).", self.nom, self.reglages.simultanees)
        with (
            signes_de_vie(self.moteur, self.nom, self.reglages.periode_vie_s),
            ThreadPoolExecutor(self.reglages.simultanees, thread_name_prefix="extraction") as pool,
            Session(self.moteur) as session,
        ):
            try:
                while not arret.is_set():
                    self._reprendre(session)
                    while len(taches) < self.reglages.simultanees:
                        bouteille_id = reserver_bouteille(session, self.nom)
                        if bouteille_id is None:
                            break
                        taches.add(pool.submit(self._traiter, bouteille_id))
                    if not taches:
                        if jusqu_a_vide and self._plus_rien_a_faire(session):
                            break
                        arret.wait(self.reglages.attente_s)
                        continue
                    _, taches = wait(taches, timeout=self.reglages.attente_s, return_when=FIRST_COMPLETED)
            except KeyboardInterrupt:
                journal.info("Arrêt demandé : les extractions commencées se terminent.")
            wait(taches)

    def _reprendre(self, session: Session) -> None:
        reprises = reprendre_les_abandonnees(session, self.nom, self.reglages.delai_abandon)
        for bouteille_id in reprises.a_conclure:
            conclure_sans_appel(session, bouteille_id)
        if reprises.remises_a_extraire or reprises.a_conclure:
            journal.warning(
                "Reprise après arrêt d'un worker : %d remise(s) à extraire, %d conclue(s) sans nouvel appel.",
                len(reprises.remises_a_extraire),
                len(reprises.a_conclure),
            )

    def _traiter(self, bouteille_id: int) -> None:
        """Une bouteille réservée, dans un thread du pool, avec sa propre session."""
        with Session(self.moteur) as session:
            try:
                config = config_figee(charger_bouteille(session, bouteille_id).inventaire)
                extraction = traiter_reservee(
                    session, bouteille_id, self.fabrique(config), self.stockage, self.nom
                )
                bouteille = charger_bouteille(session, bouteille_id)
                journal.info(
                    "Inventaire n°%d, bouteille n°%d : %s.",
                    bouteille.inventaire_id,
                    bouteille.position,
                    "extraite" if extraction.erreur is None else f"erreur ({extraction.erreur[:80]})",
                )
            except ExtractionArretee as arret:
                journal.error("%s — inventaire arrêté.", arret)
            except Exception:  # imprévu (base, disque…) : la bouteille retourne à la file
                journal.exception("Bouteille %d : échec imprévu, rendue à la file.", bouteille_id)
                liberer(session, bouteille_id, self.nom)

    def _plus_rien_a_faire(self, session: Session) -> bool:
        session.commit()
        a_extraire = session.scalar(
            select(func.count())
            .select_from(FicheBouteille)
            .join(Inventaire, Inventaire.id == FicheBouteille.inventaire_id)
            .where(FicheBouteille.statut == "a_extraire", Inventaire.extraction == "lancee")
        )
        en_cours = session.scalar(
            select(func.count()).select_from(FicheBouteille).where(FicheBouteille.statut == "en_cours")
        )
        session.commit()
        return a_extraire == 0 and en_cours == 0
