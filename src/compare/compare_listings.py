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
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
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
class SignauxModele:
    """Ce que le modèle dit de LUI-MÊME, sans référence à l'expert.

    Ces chiffres ne se comparent à rien : ils répondent à deux questions de
    décision que l'accuracy ne peut pas trancher (decisions.md 0043) —
    « la couleur est-elle lue ou déduite ? » et « quelle charge de relecture
    humaine ce pipeline génère-t-il ? ».
    """

    n_lignes: int
    couleur_source: dict[str, int] = field(default_factory=dict)
    lignes_a_relire: int = 0
    champs_a_verifier: dict[str, int] = field(default_factory=dict)

    @property
    def taux_relecture(self) -> float | None:
        if self.n_lignes == 0:
            return None
        return self.lignes_a_relire / self.n_lignes


@dataclass(frozen=True)
class RapportComparaison:
    """Résultat complet d'une comparaison."""

    n_lignes: int
    scores: list[ScoreChamp]
    desaccords: list[Desaccord]
    signaux: SignauxModele


def _canoniser_nombre(valeur: Any) -> str | None:
    """Forme canonique d'une valeur NUMÉRIQUE, ou ``None`` si ce n'en est pas une.

    Un tableur ne distingue pas 75 de 75.0 : openpyxl rend les entiers d'un
    .xlsx en `float`, si bien que la contenance de l'expert arrive en `75.0`
    face au `75` du modèle. Sans cette canonicalisation, TOUTES les contenances
    et TOUS les degrés sortiraient en désaccord (decisions.md 0042).

    Ne s'applique qu'aux vrais types numériques, jamais aux chaînes : une cuvée
    nommée « 890 » ou « 007 » doit rester le texte qu'elle est.
    """
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float, Decimal)):
        return None
    try:
        nombre = Decimal(str(valeur))
    except InvalidOperation:  # nan, inf
        return None
    if nombre == nombre.to_integral_value():
        return str(int(nombre))
    return format(nombre.normalize(), "f")


def plier(valeur: Any) -> str:
    """Réduit une valeur à sa forme comparable : sans casse, sans accents.

    Beaucoup d'« erreurs » ne sont que des écarts de convention d'écriture ; sans
    ce pliage on sous-estimerait le modèle (decisions.md 0008).

    Le pliage s'arrête là. Il ne retire ni ponctuation, ni préfixe « Domaine »,
    ni article : ce serait de la normalisation, et la v0 doit justement laisser
    ces écarts VISIBLES dans le rapport pour qu'on écrive plus tard les bonnes
    règles en regardant les vrais cas (decisions.md 0007).
    """
    canonique = _canoniser_nombre(valeur)
    if canonique is not None:
        return canonique

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
        n_lignes=len(auto),
        scores=scores,
        desaccords=desaccords,
        signaux=relever_signaux(auto),
    )


def relever_signaux(auto: Sequence[Bouteille]) -> SignauxModele:
    """Agrège ce que le modèle a déclaré sur son propre travail."""
    return SignauxModele(
        n_lignes=len(auto),
        couleur_source=dict(
            Counter(bouteille.couleur_source.value for bouteille in auto).most_common()
        ),
        lignes_a_relire=sum(1 for bouteille in auto if bouteille.champs_a_verifier),
        champs_a_verifier=dict(
            Counter(
                champ for bouteille in auto for champ in bouteille.champs_a_verifier
            ).most_common()
        ),
    )


def _pourcentage(valeur: float | None) -> str:
    return "  n/a" if valeur is None else f"{valeur * 100:5.1f}%"


def formater_signaux(signaux: SignauxModele) -> str:
    """Les signaux seuls, sans comparaison.

    Utile avant l'arrivée du listing de l'expert : on ne peut alors rien
    SCORER, mais on voit déjà ce que le modèle produit et ce qu'il refuse de
    trancher — ce qui suffit à repérer un pipeline qui déraille.
    """
    return "\n".join(_formater_signaux(signaux))


def _formater_signaux(signaux: SignauxModele) -> list[str]:
    """Section « signaux du modèle » : deux chiffres de décision, hors accuracy."""
    lignes = ["Signaux du modèle (sans référence à l'expert) :"]

    if signaux.couleur_source:
        detail = "  ".join(
            f"{source} {nombre}/{signaux.n_lignes}"
            for source, nombre in signaux.couleur_source.items()
        )
        lignes.append(f"  couleur   {detail}")
        lignes.append(
            "            « inferee » = déduite de l'appellation, pas lue sur la photo"
        )

    lignes.append(
        f"  relecture {signaux.lignes_a_relire}/{signaux.n_lignes} bouteille(s) "
        f"({_pourcentage(signaux.taux_relecture).strip()}) portent au moins un doute"
    )
    if signaux.champs_a_verifier:
        detail = "  ".join(
            f"{champ} {nombre}" for champ, nombre in signaux.champs_a_verifier.items()
        )
        lignes.append(f"            {detail}")

    return lignes


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

    lignes.extend(_formater_signaux(rapport.signaux))
    lignes.append("")

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
