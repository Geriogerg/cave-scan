#!/usr/bin/env python
"""Lance l'API JSON, en LOCAL uniquement (decisions.md 0118, 0119).

    python serveur.py                    puis http://127.0.0.1:8000/docs
    python serveur.py --port 8001 --base out/demo.db

Le serveur n'écoute que sur 127.0.0.1 tant que la connexion n'existe pas
(session 7) : aucune option ne permet de l'ouvrir au réseau. L'extraction est
faite par le worker (`python worker.py`), ou les deux à la fois : `python dev.py`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

HOTE = "127.0.0.1"  # local seulement : pas d'option pour changer ça (CLAUDE.md)
PORT_DEFAUT = 8000


def main(argv: Sequence[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")
    arguments = analyseur().parse_args(argv)

    import uvicorn

    from src.api.app import creer_app
    from src.config import environnement

    environnement.charger_env()
    print(f"API : http://{HOTE}:{arguments.port}/docs  (Ctrl-C pour arrêter)")
    uvicorn.run(creer_app(arguments.base), host=HOTE, port=arguments.port, log_level="info")
    return 0


def analyseur() -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(description="API JSON de cave-scan (local uniquement).")
    analyseur.add_argument("--port", type=int, default=PORT_DEFAUT)
    analyseur.add_argument("--base", type=Path, help="Base de données (défaut : CAVE_SCAN_DB, sinon data/cave_scan.db).")
    return analyseur


if __name__ == "__main__":
    raise SystemExit(main())
