#!/usr/bin/env python
"""Pour le développement : l'application ET le worker, d'une seule commande (decisions.md 0119).

    python dev.py                               (Gemini)
    python dev.py --backend factice --latence 2 (sans réseau ni quota)
    python dev.py --backend factice --reseau-local   (depuis un téléphone, même Wi-Fi)

Le worker tourne dans un thread de ce même processus : arrêter `dev.py`,
même brutalement, arrête les deux — jamais de worker orphelin. En
production, lancer `serveur.py` et `worker.py` séparément.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Sequence
from datetime import timedelta

import worker as commande_worker
from serveur import PortOccupe, ajouter_option_port, ajouter_option_reseau_local, annoncer, choisir_port, hote_d_ecoute


def main(argv: Sequence[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")
    analyseur = commande_worker._analyseur()
    analyseur.description = "API + worker dans un seul processus, pour le développement."
    ajouter_option_port(analyseur)
    ajouter_option_reseau_local(analyseur)
    arguments = analyseur.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import uvicorn

    from src.api.app import creer_app
    from src.config import environnement
    from src.donnees.base import creer_moteur, dossier_stockage, migrer, url_de_base
    from src.worker import ReglagesWorker, Worker

    environnement.charger_env()
    # Le port d'abord : s'il est pris, rien ne démarre — surtout pas le worker,
    # qui appellerait le modèle pour une application qui ne s'ouvrira pas.
    hote = hote_d_ecoute(arguments.reseau_local)
    try:
        port = choisir_port(hote, arguments.port)
    except PortOccupe as erreur:
        print(erreur, file=sys.stderr)
        return 2
    url = url_de_base(arguments.base)
    migrer(url)
    moteur = creer_moteur(url)
    try:
        fabrique = commande_worker._fabrique(arguments, moteur)
        fabrique(None)
    except ValueError as erreur:
        print(f"Impossible de créer l'extracteur : {erreur}\n-> Clé dans .env, ou --backend factice.", file=sys.stderr)
        return 2

    arret = threading.Event()
    reglages = ReglagesWorker(
        simultanees=arguments.simultanees,
        delai_abandon=timedelta(seconds=arguments.delai_abandon),
        periode_vie_s=arguments.periode_vie,
        attente_s=arguments.attente,
    )
    travail = threading.Thread(
        target=Worker(moteur, dossier_stockage(), fabrique, reglages).tourner, args=(arret,), daemon=True
    )
    travail.start()
    annoncer(arguments.reseau_local, port)
    print(f"Worker : backend {arguments.backend}, {arguments.simultanees} extraction(s) simultanée(s).")
    try:
        uvicorn.run(creer_app(url), host=hote, port=port, log_level="info")
    finally:
        arret.set()  # les extractions commencées se terminent
        travail.join()
        moteur.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
