"""Chargement du listing manuel de l'expert — la référence de la comparaison.

Lit un .xlsx (le format attendu du fichier de l'expert) ou un .json (fixtures).

Ce qui reste ouvert : la correspondance entre les en-têtes RÉELS de la maison
et nos champs canoniques. Seuls nos propres en-têtes d'export sont connus, ce
qui suffit à se comparer à soi-même en attendant. Inventer les siens serait
deviner (decisions.md 0007) ; à défaut de correspondance, le chargement échoue
bruyamment plutôt que de rendre un rapport vide et crédible (0034).

Reste une simple fonction : pas d'abstraction de formats, pas de registre de
loaders tant que deux `if` suffisent (decisions.md 0013, YAGNI).

Hypothèse v0 (decisions.md 0010) : les lignes sortent dans le MÊME ORDRE que les
photos. C'est ce qui permet la comparaison ligne à ligne.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.extract.schema import CHAMPS_COMPARABLES


def load_manual(chemin: str | Path) -> list[dict[str, Any]]:
    """Charge le listing manuel et l'aligne sur les champs canoniques.

    Renvoie une ligne par bouteille, dans l'ordre du fichier. Les clés sont
    celles de `Bouteille` ; une case non renseignée par l'expert vaut ``""``
    (case vide) et sera comptée `manuel_vide`, jamais comme une erreur.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"Listing manuel introuvable : {chemin}")

    suffixe = chemin.suffix.lower()

    if suffixe == ".json":
        brut = json.loads(chemin.read_text(encoding="utf-8"))
        if not isinstance(brut, list):
            raise ValueError(
                f"{chemin} : une liste de lignes est attendue, reçu {type(brut).__name__}."
            )
        lignes = [_aligner(ligne) for ligne in brut]
        _verifier_correspondance(lignes, chemin)
        return lignes

    if suffixe == ".xlsx":
        lignes = [_aligner(ligne) for ligne in _lire_xlsx(chemin)]
        _verifier_correspondance(lignes, chemin)
        return lignes

    raise NotImplementedError(
        f"Format de listing manuel non pris en charge : {suffixe or '(sans extension)'}. "
        f"Formats lus : .xlsx et .json. Pour un autre format, ajouter sa "
        f"lecture dans {__file__}."
    )


def _normaliser_entete(entete: Any) -> str:
    """Réduit un en-tête à sa forme comparable : sans casse, accents ni ponctuation.

    « Millésime » et « millesime » désignent la même colonne ; « Degré (% vol.) »
    demande en plus un alias, cf. `ENTETES_CONNUES`.
    """
    texte = unicodedata.normalize("NFKD", str(entete or ""))
    sans_accents = "".join(c for c in texte if not unicodedata.combining(c))
    return "".join(c for c in sans_accents.casefold() if c.isalnum())


# En-têtes que NOUS produisons (config/maisons/exemple.yaml) et qui ne se
# devinent pas par simple normalisation. Permet de relire un fichier sorti de
# l'outil — utile pour se comparer à soi-même en attendant l'expert.
#
# Les en-têtes RÉELS de la maison ne sont PAS ici : ils ne sont pas connus, et
# les inventer serait deviner (decisions.md 0007). Ils s'ajouteront à cette
# table en regardant son fichier ; d'ici là, `_verifier_correspondance()`
# refuse bruyamment un fichier dont rien ne correspond (0034).
ENTETES_CONNUES = {
    "domaineproducteur": "domaine",
    "degrevol": "degre",
    "couleursource": "couleur_source",
    "averifier": "champs_a_verifier",
}


def _lire_xlsx(chemin: Path) -> list[dict[str, Any]]:
    """Lit la 1re feuille : 1re ligne = en-têtes, le reste = les bouteilles.

    Les colonnes non reconnues sont ignorées (lot, estimation...), les valeurs
    numériques restent numériques — c'est `plier()` qui règle 75 face à 75.0
    (decisions.md 0032).
    """
    from openpyxl import load_workbook

    feuille = load_workbook(chemin, data_only=True).worksheets[0]
    rangees = feuille.iter_rows(values_only=True)

    entetes_brutes = next(rangees, None)
    if entetes_brutes is None:
        raise ValueError(f"{chemin} : feuille vide, aucun en-tête.")

    champs_normalises = {_normaliser_entete(c): c for c in CHAMPS_COMPARABLES}
    colonnes: dict[int, str] = {}
    for index, entete in enumerate(entetes_brutes):
        cle = _normaliser_entete(entete)
        champ = champs_normalises.get(cle) or ENTETES_CONNUES.get(cle)
        if champ in CHAMPS_COMPARABLES:
            colonnes[index] = champ

    lignes: list[dict[str, Any]] = []
    for rangee in rangees:
        if all(cellule is None or str(cellule).strip() == "" for cellule in rangee):
            continue  # ligne vide : séparateur ou fin de tableau
        lignes.append(
            {
                champ: rangee[index] if index < len(rangee) else ""
                for index, champ in colonnes.items()
            }
        )
    return lignes


def _verifier_correspondance(lignes: list[dict[str, Any]], chemin: Path) -> None:
    """Refuse un listing dont AUCUNE colonne ne correspond aux champs canoniques.

    Mode de défaillance qu'on ferme ici : le fichier de l'expert nomme sa colonne
    « Producteur » et pas « domaine ». `_aligner()` remplit alors des chaînes
    vides sans broncher, et le rapport sort `manuel_vide` partout — propre,
    crédible, et entièrement faux. Pour un outil de MESURE, c'est la pire panne
    possible : elle ne se voit pas (decisions.md 0034).
    """
    if not lignes:
        raise ValueError(f"{chemin} : listing manuel vide.")

    renseignes = [
        champ
        for champ in CHAMPS_COMPARABLES
        if any(str(ligne.get(champ, "")).strip() for ligne in lignes)
    ]
    if not renseignes:
        raise ValueError(
            f"{chemin} : aucune colonne ne correspond aux champs canoniques "
            f"({', '.join(CHAMPS_COMPARABLES)}). Les en-têtes du fichier sont "
            f"probablement différents — la correspondance est à écrire dans "
            f"load_manual(), pas à subir : sans elle le rapport afficherait "
            f"« manuel_vide » partout sans rien signaler."
        )


def colonnes_toujours_vides(lignes: Sequence[Mapping[str, Any]]) -> list[str]:
    """Champs canoniques que l'expert n'a renseignés sur AUCUNE ligne.

    Légitime (une colonne qu'il ne remplit jamais) ou symptôme d'un en-tête mal
    mappé — impossible de trancher ici, donc on le signale sans le sanctionner.
    `run_v0` l'affiche en tête de rapport.
    """
    return [
        champ
        for champ in CHAMPS_COMPARABLES
        if not any(str(ligne.get(champ, "")).strip() for ligne in lignes)
    ]


def _aligner(ligne: Any) -> dict[str, Any]:
    """Ramène une ligne brute aux champs canoniques, cases manquantes vides.

    Les clés inconnues sont ignorées silencieusement : le fichier de l'expert
    contient des colonnes qui ne nous concernent pas (lot, estimation...).
    """
    if not isinstance(ligne, dict):
        raise ValueError(
            f"Ligne de listing manuel invalide : dict attendu, reçu {type(ligne).__name__}."
        )
    return {champ: ligne.get(champ, "") for champ in CHAMPS_COMPARABLES}
