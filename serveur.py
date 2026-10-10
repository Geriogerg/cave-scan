#!/usr/bin/env python
"""Lance l'application (écrans + API JSON), en LOCAL par défaut (decisions.md 0118, 0119, 0132).

    python serveur.py                    puis http://127.0.0.1:8000/  (docs : /docs)
    python serveur.py --port 8001 --base out/demo.db
    python serveur.py --reseau-local     (développement : tester depuis un téléphone)

Port 8000 déjà pris par un autre programme : l'application prend le premier
port libre qui suit, et le dit. Un `--port` imposé et occupé : arrêt, expliqué
en français.

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
PORTS_ESSAYES = 20  # sans --port : 8000, puis 8001… jusqu'à 8019


class PortOccupe(RuntimeError):
    """Aucun port utilisable : le message dit quoi faire, en français."""


def main(argv: Sequence[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")
    arguments = analyseur().parse_args(argv)

    import uvicorn

    from src.api.app import creer_app
    from src.config import environnement

    environnement.charger_env()
    hote = hote_d_ecoute(arguments.reseau_local)
    try:
        port = choisir_port(hote, arguments.port)
    except PortOccupe as erreur:
        print(erreur, file=sys.stderr)
        return 2
    annoncer(arguments.reseau_local, port)
    uvicorn.run(creer_app(arguments.base), host=hote, port=port, log_level="info")
    return 0


def hote_d_ecoute(reseau_local: bool) -> str:
    return HOTE_RESEAU_LOCAL if reseau_local else HOTE


def choisir_port(hote: str, demande: int | None, premier: int | None = None, essais: int = PORTS_ESSAYES) -> int:
    """Le port sur lequel démarrer, vérifié AVANT de lancer quoi que ce soit.

    `demande` (option --port) : celui-là ou rien — un port imposé n'est jamais
    remplacé en silence. Sans demande : `premier`, sinon le premier libre qui
    suit, annoncé. Sans cette vérification, uvicorn s'arrêtait sur un message
    technique en anglais, après que dev.py avait déjà démarré le worker.
    """
    premier = PORT_DEFAUT if premier is None else premier
    if demande is not None:
        if not port_libre(hote, demande):
            raise PortOccupe(
                f"Le port {demande} est déjà utilisé par un autre programme. Choisissez-en un autre "
                f"(--port {demande + 1}), ou lancez sans --port : l'application prendra le premier "
                f"port libre à partir de {premier}."
            )
        return demande
    for port in range(premier, min(premier + essais, 65536)):
        if port_libre(hote, port):
            if port != premier:
                print(
                    f"Le port {premier} est déjà utilisé par un autre programme : l'application "
                    f"démarre sur le port {port}."
                )
            return port
    raise PortOccupe(
        f"Aucun port libre entre {premier} et {premier + essais - 1} : fermez le programme qui les "
        f"utilise, ou indiquez un port avec --port."
    )


def port_libre(hote: str, port: int) -> bool:
    """Peut-on écouter sur ce port ? On essaie, tout simplement, puis on rend la
    place. Sous Windows, un port réservé par le système répond « accès refusé » :
    il n'est pas libre non plus."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as essai:
        try:
            essai.bind((hote, port))
        except OSError:
            return False
    return True


def annoncer(reseau_local: bool, port: int) -> str:
    """Affiche où ouvrir l'application ; renvoie l'adresse d'écoute."""
    if not reseau_local:
        print(f"Application : http://{HOTE}:{port}/   ·   API : http://{HOTE}:{port}/docs   (Ctrl-C pour arrêter)")
        return HOTE
    print(avertissement_reseau_local(port), file=sys.stderr)
    return hote_d_ecoute(reseau_local)


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
    ajouter_option_port(analyseur)
    analyseur.add_argument("--base", type=Path, help="Base de données (défaut : CAVE_SCAN_DB, sinon data/cave_scan.db).")
    ajouter_option_reseau_local(analyseur)
    return analyseur


def ajouter_option_port(analyseur: argparse.ArgumentParser) -> None:
    analyseur.add_argument(
        "--port",
        type=int,
        help=f"Port d'écoute. Sans cette option : {PORT_DEFAUT}, ou le premier port libre qui suit.",
    )


def ajouter_option_reseau_local(analyseur: argparse.ArgumentParser) -> None:
    analyseur.add_argument(
        "--reseau-local",
        action="store_true",
        help="DÉVELOPPEMENT : écouter sur le réseau Wi-Fi pour tester depuis un téléphone. "
        "Sans connexion, tout appareil du réseau y a accès : chez vous seulement.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
