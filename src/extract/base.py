"""Le contrat d'un extracteur — la seule couture abstraite du projet.

`run_v0`, les services et les tests dépendent de ce Protocol, jamais d'une
implémentation concrète (decisions.md 0014). C'est l'exception assumée à la
règle « interface au 2e cas d'usage » : le 2e extracteur est là (Gemini, à côté
d'Anthropic), plus le rejeu de fixtures hors ligne.

Deux méthodes, UNE implémentation (decisions.md 0077) :
- `extraire_brut()` appelle le modèle et rend sa réponse TELLE QUELLE, avec de
  quoi tracer le coût ; c'est elle qu'on enregistre en base, avant toute
  interprétation (0078) ;
- `extract()` n'en est que l'interprétation, via `bouteille_depuis_sortie()` —
  jamais un second chemin d'appel.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from src.extract.schema import Bouteille, from_tool_input

if TYPE_CHECKING:
    from src.config.maison import ConfigMaison

# Une photo est désignée par son chemin sur disque.
CheminPhoto = str | Path


@dataclass(frozen=True)
class SortieModele:
    """Ce que l'appel au modèle a produit, AVANT toute interprétation.

    `brut` est la réponse telle quelle : l'objet d'un appel d'outil, le texte
    d'une réponse JSON (pas encore relu), ou None si rien n'est revenu.
    `erreur` dit pourquoi il n'y a rien d'exploitable : panne passagère qui a
    épuisé ses nouvelles tentatives, réponse vide, refus du modèle.
    """

    brut: Any
    modele: str
    version_prompt: str
    tokens_entree: int | None = None
    tokens_sortie: int | None = None
    erreur: str | None = None


class ReponseInexploitable(ValueError):
    """La réponse du modèle est arrivée, mais on ne peut pas la lire."""


@runtime_checkable
class Extractor(Protocol):
    """Transforme les photos d'UNE bouteille en champs de catalogage."""

    modele: str
    version_prompt: str

    def extraire_brut(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> SortieModele:
        """Appelle le modèle et rend sa réponse brute.

        Ne lève QUE pour une panne systématique — clé invalide, modèle inconnu,
        requête mal formée —, qu'il serait vain de répéter sur les bouteilles
        suivantes. Une panne passagère (après ses nouvelles tentatives) ou une
        réponse vide revient comme une donnée, avec `erreur` renseignée
        (decisions.md 0079).
        """
        ...

    def extract(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> Bouteille:
        """`bouteille_depuis_sortie(self.extraire_brut(...), config)`, rien d'autre.

        Une photo floue, coupée ou vide produit des abstentions
        (`non_lisible` / `non_determinable` / `None`), jamais une valeur devinée
        (decisions.md 0002, 0003).
        """
        ...


def interpreter(brut: Any, config: ConfigMaison | None = None) -> Bouteille:
    """Lit la réponse brute avec la config de la maison. Lève `ReponseInexploitable`.

    Le texte d'une réponse JSON n'est relu qu'ici : s'il est illisible, la
    réponse a quand même été enregistrée telle quelle (decisions.md 0078).
    """
    if brut is None:
        raise ReponseInexploitable("aucune réponse du modèle")
    if isinstance(brut, str):
        try:
            brut = json.loads(brut)
        except json.JSONDecodeError as erreur:
            raise ReponseInexploitable(
                f"réponse non lisible en JSON malgré le schéma imposé : {erreur}"
            ) from erreur
    if not isinstance(brut, dict):
        raise ReponseInexploitable(
            f"réponse JSON inattendue : {type(brut).__name__} au lieu d'un objet"
        )
    return from_tool_input(brut, config)


def bouteille_depuis_sortie(sortie: SortieModele, config: ConfigMaison | None = None) -> Bouteille:
    """Ce que rend `extract()` : l'interprétation, ou une abstention qui dit pourquoi.

    Un refus, une réponse vide ou une panne passagère ne cassent pas une
    campagne : la bouteille sort entièrement en abstention, motif dans `notes`,
    pour qu'il soit visible en relecture.
    """
    motif = sortie.erreur
    if motif is None:
        try:
            return interpreter(sortie.brut, config)
        except ReponseInexploitable as erreur:
            motif = str(erreur)
    return Bouteille(champs_a_verifier=["tous"], notes=f"Extraction sans résultat : {motif}.")
