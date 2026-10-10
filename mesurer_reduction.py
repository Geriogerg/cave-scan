#!/usr/bin/env python
"""Mesure l'effet de la réduction des photos sur l'extraction (decisions.md 0130).

    python mesurer_reduction.py --photos data/essai --tailles 1600,2000,2500,3000
    python mesurer_reduction.py --photos data/essai --backend factice   (essai à blanc)

APPELS RÉELS AU MODÈLE : (1 + nombre de tailles) par photo. 12 photos et 4
tailles = 60 appels — hors de portée du palier gratuit de Gemini (20 par jour).
Le résultat s'affiche sous forme de tableau, à recopier dans decisions.md avec
la taille retenue ; puis passer REDUCTION_PAR_DEFAUT à True dans src/web/pages.py
(et TAILLE_REDUCTION à la taille retenue) si la mesure le justifie.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from src.config import environnement
from src.config.maison import charger_config
from src.io.photos import EXTENSIONS_IMAGE
from src.mesure.reduction import formater, mesurer

RACINE = Path(__file__).resolve().parent


def main(argv: Sequence[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")
    arguments = _analyseur().parse_args(argv)
    environnement.charger_env()

    config = charger_config(arguments.maison)
    photos = sorted(p for p in arguments.photos.iterdir() if p.suffix.lower() in EXTENSIONS_IMAGE)
    tailles = [int(t) for t in arguments.tailles.split(",") if t.strip()]
    if not photos:
        print(f"Aucune photo dans {arguments.photos}.", file=sys.stderr)
        return 2
    print(f"{len(photos)} photo(s) × {1 + len(tailles)} version(s) = {len(photos) * (1 + len(tailles))} appel(s) "
          f"au modèle (backend {arguments.backend}).\n")

    def fabrique():
        if arguments.backend == "factice":
            from src.extract.factice import ExtracteurFactice

            return ExtracteurFactice(config)
        if arguments.backend == "anthropic":
            from src.extract.vision_extract import VisionExtractor

            return VisionExtractor(config=config)
        from src.extract.gemini_extract import GeminiExtractor

        return GeminiExtractor(config=config)

    with tempfile.TemporaryDirectory(prefix="cave-scan-mesure-") as travail:
        resultat = mesurer(photos, tailles, fabrique, config, Path(travail), progression=print)
    print()
    print(formater(resultat))
    return 0


def _analyseur() -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(description="Mesurer l'effet de la réduction des photos sur l'extraction.")
    analyseur.add_argument("--photos", type=Path, required=True, help="Dossier de VRAIES photos d'étiquettes.")
    analyseur.add_argument("--tailles", default="1600,2000,2500,3000", help="Côtés longs à essayer, en pixels.")
    analyseur.add_argument("--backend", choices=("gemini", "anthropic", "factice"), default="gemini")
    analyseur.add_argument("--maison", type=Path, default=RACINE / "config" / "maisons" / "maison_test.json")
    return analyseur


if __name__ == "__main__":
    raise SystemExit(main())
