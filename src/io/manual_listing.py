"""Chargement du listing manuel de l'expert — la référence de la comparaison.

Lit un .xlsx (le format attendu du fichier de l'expert) ou un .json (fixtures).

Avec la config de la maison, le fichier se lit dans SA langue : les en-têtes
sont reconnus par leur `nom` de colonne, et les libellés de liste (« Rosé »)
sont ramenés à leur code stable (« rose ») — c'est le code qu'on compare
(decisions.md 0057). Sans config, seuls les noms de champs canoniques sont
reconnus. Une correspondance nulle échoue bruyamment plutôt que de rendre un
rapport vide et crédible (0044).

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

from src.config.maison import ConfigMaison
from src.extract.schema import CHAMPS_COMPARABLES


def load_manual(chemin: str | Path, config: ConfigMaison | None = None) -> list[dict[str, Any]]:
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
    elif suffixe == ".xlsx":
        brut = _lire_xlsx(chemin, config)
    else:
        raise NotImplementedError(
            f"Format de listing manuel non pris en charge : {suffixe or '(sans extension)'}. "
            f"Formats lus : .xlsx et .json. Pour un autre format, ajouter sa "
            f"lecture dans {__file__}."
        )

    lignes = [_decoder(_aligner(ligne), config) for ligne in brut]
    _verifier_correspondance(lignes, chemin)
    return lignes


def _normaliser_entete(entete: Any) -> str:
    """Réduit un en-tête à sa forme comparable : sans casse, accents ni ponctuation.

    « Domaine / Château » et « domaine-chateau » désignent la même colonne.
    """
    texte = unicodedata.normalize("NFKD", str(entete or ""))
    sans_accents = "".join(c for c in texte if not unicodedata.combining(c))
    return "".join(c for c in sans_accents.casefold() if c.isalnum())


def _correspondances(config: ConfigMaison | None) -> dict[str, str]:
    """En-tête normalisé -> champ canonique.

    Les noms de champs canoniques sont toujours reconnus ; avec une config, les
    en-têtes de la maison (`nom` de chaque colonne) le sont aussi. Rien n'est
    inventé : un en-tête qui n'est dans aucun des deux reste ignoré.
    """
    table = {_normaliser_entete(champ): champ for champ in CHAMPS_COMPARABLES}
    if config is not None:
        for colonne in config.colonnes:
            if colonne.cle in CHAMPS_COMPARABLES:
                table[_normaliser_entete(colonne.nom)] = colonne.cle
    return table


def _lire_xlsx(chemin: Path, config: ConfigMaison | None) -> list[dict[str, Any]]:
    """Lit la 1re feuille : 1re ligne = en-têtes, le reste = les bouteilles.

    Les colonnes non reconnues sont ignorées (lot, estimation...), les valeurs
    numériques restent numériques — c'est `plier()` qui règle 75 face à 75.0
    (decisions.md 0042).
    """
    from openpyxl import load_workbook

    feuille = load_workbook(chemin, data_only=True).worksheets[0]
    rangees = feuille.iter_rows(values_only=True)

    entetes_brutes = next(rangees, None)
    if entetes_brutes is None:
        raise ValueError(f"{chemin} : feuille vide, aucun en-tête.")

    table = _correspondances(config)
    colonnes: dict[int, str] = {}
    for index, entete in enumerate(entetes_brutes):
        champ = table.get(_normaliser_entete(entete))
        if champ is not None:
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
    possible : elle ne se voit pas (decisions.md 0044).
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


def _decoder(ligne: dict[str, Any], config: ConfigMaison | None) -> dict[str, Any]:
    """Ramène les libellés de liste de la maison à leur code stable.

    « Rosé » devient « rose », « Demi-bouteille » devient « demi_bouteille » :
    c'est le code qu'on stocke et qu'on compare. Une valeur qui n'est ni un
    libellé ni un code de la liste est laissée telle quelle — elle ressortira
    en désaccord, visible, au lieu d'être corrigée en silence.
    """
    if config is None:
        return ligne
    for champ, valeur in ligne.items():
        colonne = config.colonne(champ)
        if colonne is not None and colonne.type == "liste":
            code = colonne.code_depuis(valeur)
            if code is not None:
                ligne[champ] = code
    return ligne
