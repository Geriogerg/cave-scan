"""Normalisation des champs extraits — IDENTITÉ en v0. C'est volontaire.

>>> normalize(bouteille) is équivalent à bouteille

Pourquoi vide (decisions.md 0007) : les règles de convention (préfixe
« Domaine », cuvée fondue ou non dans l'appellation, accents, « Ch. » pour
« Château »...) dépendent de la maison. Les écrire maintenant, ce serait les
deviner — exactement ce qu'on interdit au modèle. On les écrira en regardant
les VRAIS désaccords que le rapport de comparaison fera remonter.

La couture existe donc dès aujourd'hui pour que le pipeline n'ait pas à bouger
quand les règles arriveront ; elle ne fait juste rien.

Forme prévue : des fonctions pures `Bouteille -> Bouteille`, composées en
pipeline (decisions.md 0015). Ajouter une règle = écrire une fonction et
l'ajouter à `REGLES`, pas créer une classe ni une fabrique.
"""

from __future__ import annotations

from collections.abc import Callable

from src.extract.schema import Bouteille

# Une règle : pure, sans effet de bord, renvoie une nouvelle `Bouteille`.
Regle = Callable[[Bouteille], Bouteille]

# ======================================================================
# VIDE EN V0 — NE PAS REMPLIR SANS AVOIR VU LES VRAIS ÉCARTS.
# Ce que le rapport de comparaison devra montrer avant qu'une règle soit
# légitime : le désaccord est-il un écart de CONVENTION (à normaliser) ou
# une erreur de LECTURE (à ne surtout pas masquer) ?
# ======================================================================
REGLES: list[Regle] = []


def normalize(bouteille: Bouteille) -> Bouteille:
    """Applique la chaîne de règles. Identité tant que `REGLES` est vide."""
    for regle in REGLES:
        bouteille = regle(bouteille)
    return bouteille
