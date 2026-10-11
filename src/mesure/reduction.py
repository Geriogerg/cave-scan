"""Mesurer l'effet de la réduction des photos sur l'extraction (decisions.md 0130).

La réduction dans le navigateur divise le poids des photos par 4 à 6 — mais un
millésime en petits caractères peut devenir illisible. Elle n'est activée par
défaut qu'après cette mesure : pour chaque photo, on extrait l'ORIGINAL puis des
versions réduites (côté long N px, JPEG qualité 0,9, comme le navigateur), et
on compare champ par champ ce que le modèle lit.

Sans listing de l'expert, la référence est la lecture de l'original : on mesure
ce que la réduction FAIT PERDRE (une valeur lue sur l'original devenue
illisible ou différente), pas la justesse absolue.
"""

from __future__ import annotations

import io
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

from src.compare.compare_listings import plier
from src.config.maison import ConfigMaison
from src.extract.base import Extractor, interpreter
from src.extract.schema import est_abstention
from src.services.relecture import champs_corrigeables, valeur_courante

QUALITE_NAVIGATEUR = 90  # toBlob('image/jpeg', 0.9) dans depot.js


def reduire(source: Path, cote_max: int) -> bytes:
    """Ce que fait le navigateur : rotation appliquée, côté long ramené à
    `cote_max` (jamais agrandi), JPEG qualité 0,9, sans métadonnées."""
    with Image.open(source) as originale:
        image = ImageOps.exif_transpose(originale).convert("RGB")
    image.thumbnail((cote_max, cote_max), Image.Resampling.LANCZOS)
    sortie = io.BytesIO()
    image.save(sortie, "JPEG", quality=QUALITE_NAVIGATEUR)
    return sortie.getvalue()


@dataclass
class ResultatTaille:
    taille: str  # « original » ou « 2500 px »
    octets: int = 0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    erreurs: int = 0
    identiques: Counter = field(default_factory=Counter)  # champ -> nb de photos où la lecture est la même
    perdues: Counter = field(default_factory=Counter)  # champ -> lu sur l'original, illisible ici
    differentes: Counter = field(default_factory=Counter)  # champ -> lu ici AUTREMENT que sur l'original


@dataclass
class Mesure:
    photos: int
    champs: list[str]
    resultats: list[ResultatTaille]


def mesurer(
    photos: Sequence[Path],
    tailles: Sequence[int],
    fabrique: Callable[[], Extractor],
    config: ConfigMaison,
    dossier_travail: Path,
    progression: Callable[[str], None] = lambda _message: None,
) -> Mesure:
    """Extrait chaque photo en original puis à chaque taille ; compare à l'original."""
    champs = [c for c in champs_corrigeables(config) if c not in ("quantite", "estimation", "notes")]
    original = ResultatTaille("original")
    par_taille = {taille: ResultatTaille(f"{taille} px") for taille in tailles}
    extracteur = fabrique()

    for rang, photo in enumerate(photos, start=1):
        progression(f"[{rang}/{len(photos)}] {photo.name}")
        reference = _lire(extracteur, photo, config, original)
        for taille in tailles:
            dossier = dossier_travail / f"{taille}"
            dossier.mkdir(parents=True, exist_ok=True)
            reduite = dossier / f"{photo.stem}.jpg"
            reduite.write_bytes(reduire(photo, taille))
            lue = _lire(extracteur, reduite, config, par_taille[taille])
            if reference is None or lue is None:
                continue
            for champ in champs:
                avant, apres = valeur_courante(reference, champ), valeur_courante(lue, champ)
                if plier(avant) == plier(apres):
                    par_taille[taille].identiques[champ] += 1
                elif not est_abstention(avant) and est_abstention(apres):
                    par_taille[taille].perdues[champ] += 1
                else:
                    par_taille[taille].differentes[champ] += 1
    return Mesure(photos=len(photos), champs=champs, resultats=[original, *par_taille.values()])


def _lire(extracteur: Extractor, photo: Path, config: ConfigMaison, resultat: ResultatTaille):
    resultat.octets += photo.stat().st_size
    sortie = extracteur.extraire_brut([photo])
    resultat.tokens_entree += sortie.tokens_entree or 0
    resultat.tokens_sortie += sortie.tokens_sortie or 0
    if sortie.erreur is not None:
        resultat.erreurs += 1
        return None
    try:
        return interpreter(sortie.brut, config)
    except Exception:
        resultat.erreurs += 1
        return None


def formater(mesure: Mesure) -> str:
    """Le tableau à recopier dans decisions.md."""
    n = mesure.photos
    lignes = [
        f"Réduction des photos — {n} photo(s), référence : la lecture de l'original",
        "",
        f"{'version':<12}{'poids moyen':>12}{'tokens entrée':>15}{'identiques':>12}{'perdues':>9}{'différentes':>13}{'erreurs':>9}",
    ]
    total_champs = n * len(mesure.champs)
    for r in mesure.resultats:
        poids = f"{r.octets / max(n, 1) / 1024:.0f} Ko"
        tokens = f"{r.tokens_entree / max(n, 1):.0f}"
        if r.taille == "original":
            lignes.append(f"{r.taille:<12}{poids:>12}{tokens:>15}{'—':>12}{'—':>9}{'—':>13}{r.erreurs:>9}")
            continue
        identiques = sum(r.identiques.values())
        lignes.append(
            f"{r.taille:<12}{poids:>12}{tokens:>15}{identiques / max(total_champs, 1):>11.0%}"
            f"{sum(r.perdues.values()):>9}{sum(r.differentes.values()):>13}{r.erreurs:>9}"
        )
    lignes.append("")
    for r in mesure.resultats[1:]:
        if r.perdues or r.differentes:
            detail = ", ".join(f"{c} ({r.perdues[c]} perdu(s), {r.differentes[c]} différent(s))"
                               for c in mesure.champs if r.perdues[c] or r.differentes[c])
            lignes.append(f"{r.taille} — écarts : {detail}")
    lignes.append(
        "Règle (guide de session 4) : retenir la plus petite taille sans lecture perdue sur "
        "millesime ; si le score baisse, augmenter la taille cible."
    )
    return "\n".join(lignes)
