"""Le contrat d'un extracteur — la seule couture abstraite de la v0.

`run_v0` et les tests dépendent de ce Protocol, jamais d'une implémentation
concrète (decisions.md 0014). C'est l'exception assumée à la règle « interface
au 2e cas d'usage » : le 2e extracteur est déjà prévisible (comparaison de
modèles, relecture OCR du millésime, rejeu de fixtures hors ligne).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.extract.schema import Bouteille

# Une photo est désignée par son chemin sur disque.
CheminPhoto = str | Path


@runtime_checkable
class Extractor(Protocol):
    """Transforme les photos d'UNE bouteille en champs de catalogage."""

    def extract(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> Bouteille:
        """Renvoie une `Bouteille` — jamais une exception pour cause d'illisibilité.

        Une photo floue, coupée ou vide doit produire des abstentions
        (`non_lisible` / `non_determinable` / `None`), pas une erreur et surtout
        pas une valeur devinée (decisions.md 0002, 0003).

        `etiquette` est obligatoire ; `contre_etiquette` et `autres` sont des
        vues supplémentaires de la MÊME bouteille.
        """
        ...
