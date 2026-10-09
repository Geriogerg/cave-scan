"""Extracteur FACTICE : sans réseau ni clé, une latence réglable.

Pour développer et tester le worker sans quota (decisions.md 0122) : chaque
appel attend `latence_s`, puis rend une réponse plausible et déterministe —
le nom du fichier de l'étiquette dans le domaine, pour qu'une réponse se
rattache à sa photo. Ce n'est PAS une lecture : son contenu ne mesure rien.

Il peut journaliser chaque appel (début, fin, processus) dans un fichier, en
ajout seul : c'est ce qui permet de vérifier, même entre processus, qu'une
bouteille n'est jamais extraite deux fois en même temps.
"""

from __future__ import annotations

import os
import random
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from src.extract.base import CheminPhoto, SortieModele, bouteille_depuis_sortie
from src.extract.consignes import version_prompt
from src.extract.schema import Bouteille, schema_extraction

if TYPE_CHECKING:
    from src.config.maison import ConfigMaison


# Un seul verrou par processus : le worker crée un extracteur par bouteille, et
# tous écrivent dans le même journal.
_VERROU_JOURNAL = threading.Lock()


class ExtracteurFactice:
    modele = "factice"

    def __init__(
        self,
        config: ConfigMaison | None = None,
        latence_s: float = 0.0,
        variation_s: float = 0.0,
        journal: Path | None = None,
    ) -> None:
        self.config = config
        self.latence_s = latence_s
        self.variation_s = variation_s
        self.journal = Path(journal) if journal else None
        self.version_prompt = version_prompt(schema_extraction(config))
        self.limiteur = None
        self._verrou = threading.Lock()
        self.en_cours = 0
        self.max_simultanes = 0  # dans ce processus : pour vérifier le parallélisme

    def extraire_brut(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> SortieModele:
        nom = Path(etiquette).stem
        with self._verrou:
            self.en_cours += 1
            self.max_simultanes = max(self.max_simultanes, self.en_cours)
        self._noter("debut", nom)
        try:
            if self.limiteur is not None:
                self.limiteur.attendre_mon_tour()
            time.sleep(self.latence_s + random.uniform(0, self.variation_s))
        finally:
            self._noter("fin", nom)
            with self._verrou:
                self.en_cours -= 1
        return SortieModele(
            brut={"domaine": f"Domaine factice {nom[:12]}", "appellation": "Appellation factice"},
            modele=self.modele,
            version_prompt=self.version_prompt,
            tokens_entree=1000,
            tokens_sortie=200,
        )

    def extract(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> Bouteille:
        return bouteille_depuis_sortie(self.extraire_brut(etiquette, contre_etiquette, autres), self.config)

    def _noter(self, evenement: str, nom: str) -> None:
        if self.journal is None:
            return
        ligne = f"{evenement} {nom} {os.getpid()} {time.time():.6f}\n"
        with _VERROU_JOURNAL, open(self.journal, "a", encoding="utf-8") as fichier:
            fichier.write(ligne)


def lire_journal(journal: Path) -> list[tuple[str, str, int, float]]:
    lignes = []
    for ligne in Path(journal).read_text(encoding="utf-8").splitlines():
        evenement, nom, pid, instant = ligne.split()
        lignes.append((evenement, nom, int(pid), float(instant)))
    return lignes


def appels_simultanes_sur_une_meme_photo(journal: Path, morts: set[int] = frozenset()) -> list[str]:
    """Les photos appelées deux fois EN MÊME TEMPS (doit être vide).

    Un appel d'un processus tué (`morts`) n'a jamais de « fin » : il s'est
    arrêté avec le processus, avant toute reprise — il ne compte pas comme
    simultané avec l'appel qui le reprend.
    """
    ouverts: dict[str, list[int]] = {}
    fautives = []
    for evenement, nom, pid, _instant in lire_journal(journal):
        vivants = ouverts.setdefault(nom, [])
        if evenement == "debut":
            if any(autre not in morts for autre in vivants):
                fautives.append(nom)
            vivants.append(pid)
        else:
            vivants.remove(pid)
    return fautives
