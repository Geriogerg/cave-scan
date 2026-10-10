#!/usr/bin/env python
"""Lance l'application (écrans + API JSON), en LOCAL par défaut (decisions.md 0118, 0119, 0132).

    python serveur.py                    puis http://127.0.0.1:8000/  (docs : /docs)
    python serveur.py --port 8001 --base out/demo.db
    python serveur.py --reseau-local     (développement : tester depuis un téléphone)

Sans option, le serveur n'écoute que sur 127.0.0.1. `--reseau-local` l'ouvre au
réseau Wi-Fi pour tester depuis un téléphone, avec un avertissement : tant que la
connexion n'existe pas (session 7), toute personne sur ce réseau y a accès.
L'extraction est faite par le worker (`python worker.py`), ou les deux à la
fois : `python dev.py`.
"""

from __future__ import annotations

import argparse
import socket
import sys
from collections.abc import Sequence
from pathlib import Path

HOTE = "127.0.0.1"  # par défaut : local seulement (CLAUDE.md)
HOTE_RESEAU_LOCAL = "0.0.0.0"  # seulement avec l'option de développement explicite
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
    hote = annoncer(arguments.reseau_local, arguments.port)
    uvicorn.run(creer_app(arguments.base), host=hote, port=arguments.port, log_level="info")
    return 0


def annoncer(reseau_local: bool, port: int) -> str:
    """Affiche où ouvrir l'application ; renvoie l'adresse d'écoute."""
    if not reseau_local:
        print(f"Application : http://{HOTE}:{port}/   ·   API : http://{HOTE}:{port}/docs   (Ctrl-C pour arrêter)")
        return HOTE
    print(avertissement_reseau_local(port), file=sys.stderr)
    return HOTE_RESEAU_LOCAL


def avertissement_reseau_local(port: int) -> str:
    adresse = adresse_sur_le_reseau()
    lien = f"http://{adresse}:{port}/" if adresse else f"http://<adresse de cet ordinateur>:{port}/"
    return (
        "\n"
        "⚠  MODE RÉSEAU LOCAL (développement)\n"
        "⚠  L'application est ouverte à TOUT appareil connecté à ce réseau Wi-Fi, sans\n"
        "⚠  mot de passe (la connexion n'existe pas encore). À utiliser chez vous,\n"
        "⚠  jamais sur le réseau d'un client.\n"
        f"\n   Sur le téléphone (même Wi-Fi) : {lien}\n"
        "   Windows peut demander d'autoriser Python dans le pare-feu : « Réseaux privés ».\n"
    )


def adresse_sur_le_reseau() -> str | None:
    """L'adresse de cet ordinateur sur le réseau local, ou None. Aucun paquet
    n'est envoyé : la socket UDP ne fait que choisir l'interface de sortie."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sonde:
            sonde.connect(("192.0.2.1", 9))  # adresse de documentation, jamais contactée
            adresse = sonde.getsockname()[0]
    except OSError:
        return None
    return None if adresse.startswith("127.") else adresse


def analyseur() -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(description="cave-scan : écrans et API JSON (local par défaut).")
    analyseur.add_argument("--port", type=int, default=PORT_DEFAUT)
    analyseur.add_argument("--base", type=Path, help="Base de données (défaut : CAVE_SCAN_DB, sinon data/cave_scan.db).")
    ajouter_option_reseau_local(analyseur)
    return analyseur


def ajouter_option_reseau_local(analyseur: argparse.ArgumentParser) -> None:
    analyseur.add_argument(
        "--reseau-local",
        action="store_true",
        help="DÉVELOPPEMENT : écouter sur le réseau Wi-Fi pour tester depuis un téléphone. "
        "Sans connexion, tout appareil du réseau y a accès : chez vous seulement.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
