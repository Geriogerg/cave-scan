#!/usr/bin/env python
"""Lance le worker d'extraction (decisions.md 0115, 0119).

    python worker.py                          (Gemini, 4 extractions simultanées)
    python worker.py --simultanees 2 --backend anthropic
    python worker.py --backend factice --latence 2   (sans réseau ni quota : pour développer)

Il traite les bouteilles des inventaires LANCÉS (par l'API, ou par
`run_v0.py --inventaire`). L'arrêter (Ctrl-C) laisse terminer les extractions
commencées ; le tuer ne perd rien : un worker relancé reprend les bouteilles
abandonnées une fois leur délai d'abandon passé.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from src.config import environnement
from src.config.maison import ConfigMaison
from src.donnees.base import creer_moteur, dossier_stockage, migrer, url_de_base
from src.extract.base import Extractor
from src.services.debit import LimiteDebitPartagee
from src.worker import SIMULTANEES_DEFAUT, ReglagesWorker, Worker


def main(argv: Sequence[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")
    arguments = _analyseur().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    environnement.charger_env()

    url = url_de_base(arguments.base)
    migrer(url)
    moteur = creer_moteur(url)
    try:
        fabrique = _fabrique(arguments, moteur)
        fabrique(None)  # une clé absente se signale au démarrage, pas à chaque bouteille
    except ValueError as erreur:
        print(f"Impossible de créer l'extracteur : {erreur}\n-> Clé dans .env, voir .env.example.", file=sys.stderr)
        return 2

    reglages = ReglagesWorker(
        simultanees=arguments.simultanees,
        delai_abandon=timedelta(seconds=arguments.delai_abandon),
        periode_vie_s=arguments.periode_vie,
        attente_s=arguments.attente,
    )
    try:
        Worker(moteur, dossier_stockage(), fabrique, reglages).tourner(jusqu_a_vide=arguments.jusqu_a_vide)
    finally:
        moteur.dispose()
    return 0


def _fabrique(arguments: argparse.Namespace, moteur):
    """L'extracteur d'une bouteille, avec la config figée de son inventaire et la
    limite de débit partagée en base."""

    def fabriquer(config: ConfigMaison | None) -> Extractor:
        if arguments.backend == "factice":
            from src.extract.factice import ExtracteurFactice

            extracteur = ExtracteurFactice(config, arguments.latence, arguments.variation, arguments.journal_appels)
            espacement = arguments.espacement or 0.0
        elif arguments.backend == "anthropic":
            from src.extract.vision_extract import VisionExtractor

            extracteur = VisionExtractor(config=config)
            espacement = arguments.espacement or 0.0
        else:
            from src.extract.gemini_extract import PAUSE_ENTRE_APPELS_S, GeminiExtractor

            extracteur = GeminiExtractor(config=config)
            espacement = PAUSE_ENTRE_APPELS_S if arguments.espacement is None else arguments.espacement
        extracteur.limiteur = LimiteDebitPartagee(moteur, extracteur.modele, espacement)
        return extracteur

    return fabriquer


def _analyseur() -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(description="Worker d'extraction en arrière-plan.")
    analyseur.add_argument("--simultanees", type=int, default=SIMULTANEES_DEFAUT, help="Extractions en parallèle (défaut 4).")
    analyseur.add_argument("--backend", choices=("gemini", "anthropic", "factice"), default="gemini")
    analyseur.add_argument(
        "--espacement",
        type=float,
        help="Secondes minimum entre deux appels au modèle, tous workers confondus "
        "(défaut : 4,5 pour le palier gratuit Gemini, 0 sinon).",
    )
    analyseur.add_argument("--base", type=Path, help="Base de données (défaut : CAVE_SCAN_DB, sinon data/cave_scan.db).")
    analyseur.add_argument("--jusqu-a-vide", action="store_true", help="S'arrêter quand il n'y a plus rien à extraire.")
    analyseur.add_argument("--delai-abandon", type=float, default=120.0, help="Secondes sans signe de vie avant de reprendre une bouteille.")
    analyseur.add_argument("--periode-vie", type=float, default=15.0, help="Secondes entre deux signes de vie.")
    analyseur.add_argument("--attente", type=float, default=2.0, help="Secondes entre deux regards sur une file vide.")
    factice = analyseur.add_argument_group("backend factice (développement, tests)")
    factice.add_argument("--latence", type=float, default=1.0, help="Durée simulée d'un appel.")
    factice.add_argument("--variation", type=float, default=0.0, help="Variation aléatoire ajoutée à la latence.")
    factice.add_argument("--journal-appels", type=Path, help="Journalise chaque appel (début, fin, processus).")
    return analyseur


if __name__ == "__main__":
    raise SystemExit(main())
