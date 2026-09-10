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
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from src.compare.compare_listings import (
    comparer,
    formater_rapport,
    formater_signaux,
    relever_signaux,
)
from src.export.excel_writer import charger_config, ecrire_excel
from src.extract.base import Extractor
from src.extract.fixture_extract import FixtureExtractor
from src.extract.schema import Bouteille, from_tool_input
from src.io.manual_listing import colonnes_toujours_vides, load_manual
from src.io.photos import PhotosBouteille, grouper_photos
from src.normalize.normalize import normalize

RACINE = Path(__file__).resolve().parent
CONFIG_DEFAUT = RACINE / "config" / "maisons" / "exemple.yaml"
SORTIE_DEFAUT = RACINE / "out" / "listing_auto.xlsx"

FIXTURES = RACINE / "tests" / "fixtures"
FIXTURE_AUTO = FIXTURES / "bouteilles_auto.json"
FIXTURE_MANUEL = FIXTURES / "manuel.json"


def charger_journal(journal: Path) -> list[Bouteille]:
    """Relit les bouteilles déjà extraites lors d'un run interrompu."""
    if not journal.exists():
        return []
    return [
        from_tool_input(json.loads(ligne))
        for ligne in journal.read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]


def extraire(
    extracteur: Extractor,
    photos: Sequence[PhotosBouteille],
    journal: Path | None = None,
    reprendre: bool = False,
) -> list[Bouteille]:
    """Extrait puis normalise, bouteille par bouteille, dans l'ordre.

    Chaque bouteille est écrite dans le journal DÈS qu'elle est extraite
    (decisions.md 0036) : une campagne de 200 bouteilles interrompue à la 180e
    ne doit pas perdre 180 appels API déjà payés. `reprendre` repart de là où
    le journal s'arrête.
    """
    bouteilles: list[Bouteille] = []

    if journal is not None:
        journal.parent.mkdir(parents=True, exist_ok=True)
        if reprendre:
            bouteilles = charger_journal(journal)
            if bouteilles:
                print(f"  reprise : {len(bouteilles)} bouteille(s) déjà au journal")
        else:
            journal.write_text("", encoding="utf-8")

    for index, vues in enumerate(photos[len(bouteilles) :], start=len(bouteilles) + 1):
        print(f"  [{index}/{len(photos)}] {vues.nom}", flush=True)
        bouteille = normalize(
            extracteur.extract(
                etiquette=vues.etiquette,
                contre_etiquette=vues.contre_etiquette,
                autres=vues.autres,
            )
        )
        bouteilles.append(bouteille)
        if journal is not None:
            with journal.open("a", encoding="utf-8") as flux:
                flux.write(json.dumps(bouteille.as_dict(), ensure_ascii=False) + "\n")

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
    analyseur.add_argument(
        "--manual",
        type=Path,
        help="Listing manuel de l'expert. SANS lui : extraction et Excel "
        "seulement, aucun score — c'est le mode d'attente avant que le fichier "
        "de l'expert existe.",
    )
    analyseur.add_argument(
        "--limite",
        type=int,
        help="N'extrait que les N premières bouteilles. À utiliser pour le "
        "premier run payant : on vérifie sur 3 bouteilles avant d'en lancer 200.",
    )
    analyseur.add_argument(
        "--maison",
        type=Path,
        default=CONFIG_DEFAUT,
        help=f"Config de format de la maison (défaut : {CONFIG_DEFAUT.name}).",
    )
    analyseur.add_argument(
        "--sortie", type=Path, default=SORTIE_DEFAUT, help="Chemin du .xlsx produit."
    )
    analyseur.add_argument(
        "--journal",
        type=Path,
        help="Journal d'extraction .jsonl (défaut : à côté du .xlsx). "
        "Écrit au fil de l'eau pour ne rien perdre si le run s'interrompt.",
    )
    analyseur.add_argument(
        "--reprendre",
        action="store_true",
        help="Repart du journal existant au lieu de tout ré-extraire.",
    )
    arguments = analyseur.parse_args(argv)
    journal = arguments.journal or arguments.sortie.with_suffix(".jsonl")

    # Le rapport contient des accents ; la console Windows est en cp1252 par défaut.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if arguments.dry_run:
        extracteur: Extractor = FixtureExtractor.depuis_json(FIXTURE_AUTO)
        photos = _photos_factices(len(extracteur))
        chemin_manuel = FIXTURE_MANUEL
        print(f"DRY-RUN — fixtures {FIXTURE_AUTO.name} / {FIXTURE_MANUEL.name}, hors ligne.\n")
    else:
        if not arguments.photos:
            analyseur.error("--photos est requis hors --dry-run.")
        # Import tardif : le dry-run ne doit dépendre ni du SDK ni d'une clé API.
        from src.extract.vision_extract import VisionExtractor

        extracteur = VisionExtractor()
        photos = grouper_photos(arguments.photos)
        if arguments.limite:
            photos = photos[: arguments.limite]
        chemin_manuel = arguments.manual
        print(f"Modèle : {extracteur.modele} — {len(photos)} bouteille(s).\n")

    print("Extraction :")
    bouteilles = extraire(extracteur, photos, journal, arguments.reprendre)

    config = charger_config(arguments.maison)
    chemin_excel = ecrire_excel(bouteilles, config, arguments.sortie)
    print(f"\nListing automatique écrit : {chemin_excel}")
    print(f"Journal d'extraction       : {journal}")

    if chemin_manuel is None:
        print(
            "\nAucun listing manuel fourni : PAS DE SCORE.\n"
            "Le livrable de la v0 est la comparaison à l'expert ; sans son "
            "fichier,\nce run montre seulement ce que le modèle produit.\n"
        )
        print(formater_signaux(relever_signaux(bouteilles)))
        return 0

    manuel = load_manual(chemin_manuel)

    vides = colonnes_toujours_vides(manuel)
    if vides:
        print(
            f"\n⚠  Colonnes jamais renseignées par l'expert : {', '.join(vides)}.\n"
            f"   Soit il ne les remplit pas, soit l'en-tête du fichier ne "
            f"correspond pas au champ canonique — dans ce second cas le score "
            f"de ces champs ne veut rien dire."
        )

    rapport = comparer(bouteilles, manuel)
    print()
    print(formater_rapport(rapport))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
