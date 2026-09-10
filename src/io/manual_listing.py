"""Chargement du listing manuel de l'expert — la référence de la comparaison.

STUB ASSUMÉ : tant que le vrai fichier de l'expert n'est pas arrivé, seul le
format de fixtures JSON est lu. Le point d'extension est balisé ci-dessous.

Reste une simple fonction tant qu'il n'y a qu'un format à lire : pas
d'abstraction de formats, pas de registre de loaders (decisions.md 0013, YAGNI).

Hypothèse v0 (decisions.md 0010) : les lignes sortent dans le MÊME ORDRE que les
photos. C'est ce qui permet la comparaison ligne à ligne.
"""

from __future__ import annotations

import json
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

    # ==================================================================
    # À COMPLÉTER À L'ARRIVÉE DU FICHIER DE L'EXPERT
    # ------------------------------------------------------------------
    # Le vrai listing sera vraisemblablement un .xlsx (ou .csv). Il faudra ici :
    #   1. lire les lignes du fichier ;
    #   2. mapper ses en-têtes RÉELS vers les champs canoniques de `Bouteille` ;
    #   3. passer chaque ligne dans `_aligner()`.
    # Ne pas inventer la correspondance d'en-têtes à l'avance : elle se lit sur
    # le vrai fichier (question ouverte de decisions.md).
    # ==================================================================
    raise NotImplementedError(
        f"Format de listing manuel non pris en charge : {suffixe or '(sans extension)'}. "
        f"Seul .json (fixtures) est lu en v0 ; la lecture du fichier réel de "
        f"l'expert reste à écrire dans {__file__}."
    )


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
