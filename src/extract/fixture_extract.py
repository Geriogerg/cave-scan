"""Extracteur de fixtures : rejoue des réponses enregistrées, sans réseau.

C'est ce qui rend `--dry-run` possible (decisions.md 0012) : toute la plomberie
— extraction, normalisation, export, comparaison — tourne sans clé API ni
vraies photos, en attendant leur arrivée.

Il implémente le même Protocol `Extractor` que le VLM : si le pipeline marche
avec celui-ci, la seule inconnue restante est la qualité de lecture du modèle.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from src.extract.base import CheminPhoto
from src.extract.schema import Bouteille, from_tool_input

if TYPE_CHECKING:
    from src.config.maison import ConfigMaison


class FixtureExtractor:
    """Rejoue, dans l'ordre, des charges utiles d'appel d'outil enregistrées.

    Les charges ont exactement la forme que le VLM renvoie : elles passent par
    le même `from_tool_input()`, donc le dry-run exerce le vrai chemin de
    désérialisation, pas un raccourci.
    """

    def __init__(self, charges: Sequence[dict], config: ConfigMaison | None = None) -> None:
        self._charges = list(charges)
        self.config = config
        self._index = 0

    @classmethod
    def depuis_json(cls, chemin: str | Path, config: ConfigMaison | None = None) -> FixtureExtractor:
        chemin = Path(chemin)
        charges = json.loads(chemin.read_text(encoding="utf-8"))
        if not isinstance(charges, list):
            raise ValueError(f"{chemin} : une liste de charges utiles est attendue.")
        return cls(charges, config)

    def __len__(self) -> int:
        return len(self._charges)

    def extract(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> Bouteille:
        """Renvoie la fixture suivante. Les photos passées sont ignorées.

        L'ordre d'appel fait foi, comme l'alignement ligne à ligne du reste de
        la v0 (decisions.md 0010).
        """
        if self._index >= len(self._charges):
            raise IndexError(
                f"Fixtures épuisées : {len(self._charges)} charge(s) disponible(s), "
                f"un {self._index + 1}e appel a été fait."
            )
        charge = self._charges[self._index]
        self._index += 1
        return from_tool_input(charge, self.config)
