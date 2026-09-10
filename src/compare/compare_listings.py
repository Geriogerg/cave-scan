"""Comparaison champ par champ du listing automatique et du listing de l'expert.

C'est le livrable de la v0 : le tableau de scores. Le reste du pipeline n'existe
que pour alimenter ce module.

Ce que les métriques séparent volontairement (decisions.md 0009) :

- ``manuel_vide``  : l'expert n'a rien mis — la ligne n'est pas évaluable.
- ``abstention``   : l'expert a une valeur, le modèle a refusé de se prononcer.
                     Ce n'est PAS une erreur, c'est le comportement voulu.
- ``desaccord``    : les deux sont renseignés et diffèrent — les vrais ratés.
- ``accuracy``     : part d'accords parmi les seules lignes réellement
                     comparables (expert renseigné ET modèle non abstenu).

Confondre abstention et désaccord donnerait un score faux et pousserait à
« réparer » un modèle qui se comporte correctement.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.extract.schema import CHAMPS_COMPARABLES, Bouteille, est_abstention


@dataclass(frozen=True)
class ScoreChamp:
    """Scores d'un champ sur l'ensemble des lignes comparées."""

    champ: str
    total: int
    manuel_vide: int
    abstention: int
    comparables: int
    exact: int
    desaccord: int

    @property
    def evaluables(self) -> int:
        """Lignes où l'expert a mis une valeur (donc où une réponse est attendue)."""
        return self.total - self.manuel_vide

    @property
    def accuracy(self) -> float | None:
        """Part d'accords parmi les lignes comparables. ``None`` si aucune."""
        if self.comparables == 0:
            return None
        return self.exact / self.comparables

    @property
    def taux_abstention(self) -> float | None:
        """Part d'abstentions parmi les lignes évaluables. ``None`` si aucune."""
        if self.evaluables == 0:
            return None
        return self.abstention / self.evaluables


@dataclass(frozen=True)
class Desaccord:
    """Un désaccord ponctuel, destiné à la file d'inspection."""

    ligne: int
    champ: str
    auto: str
    manuel: str


@dataclass(frozen=True)
class RapportComparaison:
    """Résultat complet d'une comparaison."""

    n_lignes: int
    scores: list[ScoreChamp]
    desaccords: list[Desaccord]


def plier(valeur: Any) -> str:
    """Réduit une valeur à sa forme comparable : sans casse, sans accents.

    Beaucoup d'« erreurs » ne sont que des écarts de convention d'écriture ; sans
    ce pliage on sous-estimerait le modèle (decisions.md 0008).

    Le pliage s'arrête là. Il ne retire ni ponctuation, ni préfixe « Domaine »,
    ni article : ce serait de la normalisation, et la v0 doit justement laisser
    ces écarts VISIBLES dans le rapport pour qu'on écrive plus tard les bonnes
    règles en regardant les vrais cas (decisions.md 0007).
    """
    texte = str(valeur).strip()
    decompose = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans_accents.casefold().split())


def _affichage(valeur: Any) -> str:
    """Représentation lisible d'une valeur dans le rapport de désaccords."""
    if valeur is None:
        return "None"
    return str(valeur)


def _manuel_est_vide(valeur: Any) -> bool:
    """L'expert n'a rien renseigné sur cette case."""
    return valeur is None or str(valeur).strip() == ""


def comparer(
    auto: Sequence[Bouteille],
    manuel: Sequence[Mapping[str, Any]],
    champs: Sequence[str] = CHAMPS_COMPARABLES,
) -> RapportComparaison:
    """Compare deux listings alignés ligne à ligne.

    L'alignement ligne à ligne est l'hypothèse de la v0 (decisions.md 0010) :
    la n-ième bouteille photographiée correspond à la n-ième ligne de l'expert.
    Des longueurs différentes signifient que l'hypothèse est fausse — on
    s'arrête plutôt que de comparer des bouteilles décalées, ce qui produirait
    un score faux et crédible.
    """
    if len(auto) != len(manuel):
        raise ValueError(
            f"Alignement ligne à ligne rompu : {len(auto)} bouteille(s) extraite(s) "
            f"pour {len(manuel)} ligne(s) de listing manuel. La v0 suppose le même "
            f"ordre des deux côtés (decisions.md 0010)."
        )

    scores: list[ScoreChamp] = []
    desaccords: list[Desaccord] = []

    for champ in champs:
        manuel_vide = abstention = exact = desaccord = 0

        for index, (bouteille, ligne_manuel) in enumerate(zip(auto, manuel)):
            valeur_auto = getattr(bouteille, champ)
            valeur_manuel = ligne_manuel.get(champ)

            if _manuel_est_vide(valeur_manuel):
                manuel_vide += 1
            elif est_abstention(valeur_auto):
                abstention += 1
            elif plier(valeur_auto) == plier(valeur_manuel):
                exact += 1
            else:
                desaccord += 1
                desaccords.append(
                    Desaccord(
                        ligne=index,
                        champ=champ,
                        auto=_affichage(valeur_auto),
                        manuel=_affichage(valeur_manuel),
                    )
                )

        scores.append(
            ScoreChamp(
                champ=champ,
                total=len(auto),
                manuel_vide=manuel_vide,
                abstention=abstention,
                comparables=exact + desaccord,
                exact=exact,
                desaccord=desaccord,
            )
        )

    return RapportComparaison(
        n_lignes=len(auto), scores=scores, desaccords=desaccords
    )


def _pourcentage(valeur: float | None) -> str:
    return "  n/a" if valeur is None else f"{valeur * 100:5.1f}%"


def formater_rapport(rapport: RapportComparaison) -> str:
    """Met en forme le rapport pour la console. Le livrable de la v0."""
    largeur_champ = max((len(s.champ) for s in rapport.scores), default=10)
    largeur_champ = max(largeur_champ, len("champ"))

    lignes = [
        f"Comparaison auto vs manuel — {rapport.n_lignes} bouteille(s)",
        "",
        f"{'champ':<{largeur_champ}}  {'accuracy':>8}  {'absten.':>8}  "
        f"{'compar.':>7}  {'exact':>5}  {'desac.':>6}  {'m.vide':>6}",
        "-" * (largeur_champ + 50),
    ]

    for score in rapport.scores:
        lignes.append(
            f"{score.champ:<{largeur_champ}}  {_pourcentage(score.accuracy):>8}  "
            f"{_pourcentage(score.taux_abstention):>8}  {score.comparables:>7}  "
            f"{score.exact:>5}  {score.desaccord:>6}  {score.manuel_vide:>6}"
        )

    lignes.extend(
        [
            "",
            "accuracy = exact / comparables (expert renseigné ET modèle non abstenu)",
            "absten.  = abstentions / lignes où l'expert a une valeur — pas une erreur",
            "",
        ]
    )

    if not rapport.desaccords:
        lignes.append("Aucun désaccord.")
        return "\n".join(lignes)

    lignes.append(f"Désaccords à inspecter ({len(rapport.desaccords)}) :")
    for desaccord in rapport.desaccords:
        lignes.append(
            f"  ligne {desaccord.ligne:>3}  {desaccord.champ:<14}  "
            f"auto={desaccord.auto!r}  manuel={desaccord.manuel!r}"
        )

    return "\n".join(lignes)
