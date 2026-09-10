#!/usr/bin/env python
"""Orchestrateur de la v0 : photos -> Excel + tableau de scores.

    python run_v0.py --dry-run
    python run_v0.py --photos data/photos --manual data/listing_expert.json

Le livrable est le RAPPORT DE COMPARAISON imprimé en fin de course. L'Excel
n'est que la forme livrable du listing automatique ; il ne prouve rien à lui
seul (CLAUDE.md).

Ce module ne connaît que le Protocol `Extractor` : il ne sait pas s'il parle à
un VLM ou à des fixtures (decisions.md 0014).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from src.compare.compare_listings import comparer, formater_rapport
from src.export.excel_writer import charger_config, ecrire_excel
from src.extract.base import Extractor
from src.extract.fixture_extract import FixtureExtractor
from src.extract.schema import Bouteille
from src.io.manual_listing import load_manual
from src.io.photos import PhotosBouteille, grouper_photos
from src.normalize.normalize import normalize

RACINE = Path(__file__).resolve().parent
CONFIG_DEFAUT = RACINE / "config" / "maisons" / "exemple.yaml"
SORTIE_DEFAUT = RACINE / "out" / "listing_auto.xlsx"

FIXTURES = RACINE / "tests" / "fixtures"
FIXTURE_AUTO = FIXTURES / "bouteilles_auto.json"
FIXTURE_MANUEL = FIXTURES / "manuel.json"


def extraire(
    extracteur: Extractor, photos: Sequence[PhotosBouteille]
) -> list[Bouteille]:
    """Extrait puis normalise, bouteille par bouteille, dans l'ordre."""
    bouteilles: list[Bouteille] = []
    for index, vues in enumerate(photos, start=1):
        print(f"  [{index}/{len(photos)}] {vues.nom}", flush=True)
        bouteille = extracteur.extract(
            etiquette=vues.etiquette,
            contre_etiquette=vues.contre_etiquette,
            autres=vues.autres,
        )
        bouteilles.append(normalize(bouteille))
    return bouteilles


def _photos_factices(nombre: int) -> list[PhotosBouteille]:
    """Chemins fictifs du dry-run : `FixtureExtractor` les ignore, mais le
    pipeline garde exactement la même forme qu'avec de vraies photos."""
    return [
        PhotosBouteille(etiquette=Path(f"(fixture)/bouteille_{i:02d}/etiquette.jpg"))
        for i in range(1, nombre + 1)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        description="Pipeline v0 : extraction VLM -> Excel maison -> scores vs expert."
    )
    analyseur.add_argument(
        "--dry-run",
        action="store_true",
        help="Tourne hors ligne sur les fixtures : ni clé API, ni réseau, ni photos.",
    )
    analyseur.add_argument("--photos", type=Path, help="Dossier des photos.")
    analyseur.add_argument("--manual", type=Path, help="Listing manuel de l'expert.")
    analyseur.add_argument(
        "--maison",
        type=Path,
        default=CONFIG_DEFAUT,
        help=f"Config de format de la maison (défaut : {CONFIG_DEFAUT.name}).",
    )
    analyseur.add_argument(
        "--sortie", type=Path, default=SORTIE_DEFAUT, help="Chemin du .xlsx produit."
    )
    arguments = analyseur.parse_args(argv)

    # Le rapport contient des accents ; la console Windows est en cp1252 par défaut.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if arguments.dry_run:
        extracteur: Extractor = FixtureExtractor.depuis_json(FIXTURE_AUTO)
        photos = _photos_factices(len(extracteur))
        chemin_manuel = FIXTURE_MANUEL
        print(f"DRY-RUN — fixtures {FIXTURE_AUTO.name} / {FIXTURE_MANUEL.name}, hors ligne.\n")
    else:
        if not arguments.photos or not arguments.manual:
            analyseur.error("--photos et --manual sont requis hors --dry-run.")
        # Import tardif : le dry-run ne doit dépendre ni du SDK ni d'une clé API.
        from src.extract.vision_extract import VisionExtractor

        extracteur = VisionExtractor()
        photos = grouper_photos(arguments.photos)
        chemin_manuel = arguments.manual
        print(f"Modèle : {extracteur.modele} — {len(photos)} bouteille(s).\n")

    print("Extraction :")
    bouteilles = extraire(extracteur, photos)

    config = charger_config(arguments.maison)
    chemin_excel = ecrire_excel(bouteilles, config, arguments.sortie)
    print(f"\nListing automatique écrit : {chemin_excel}")

    manuel = load_manual(chemin_manuel)
    rapport = comparer(bouteilles, manuel)
    print()
    print(formater_rapport(rapport))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
