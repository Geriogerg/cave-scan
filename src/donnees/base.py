"""Ouverture de la base et mise à jour de son schéma (decisions.md 0075).

Le schéma n'est jamais créé ni recréé à la main : `ouvrir_base()` applique les
migrations Alembic jusqu'à la dernière, puis ouvre une session. Une base
existante est mise à niveau sans rien perdre ; une base absente est créée de
zéro par la migration initiale.

Où vivent la base et les photos stockées : variables d'environnement
`CAVE_SCAN_DB` (chemin d'un fichier SQLite, ou URL complète pour PostgreSQL) et
`CAVE_SCAN_STOCKAGE`, par défaut sous `data/` — jamais versionné.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as ConfigAlembic
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

RACINE = Path(__file__).resolve().parents[2]

VARIABLE_BASE = "CAVE_SCAN_DB"
VARIABLE_STOCKAGE = "CAVE_SCAN_STOCKAGE"
BASE_DEFAUT = RACINE / "data" / "cave_scan.db"
STOCKAGE_DEFAUT = RACINE / "data" / "stockage"
ATTENTE_VERROU_MS = 30_000  # SQLite occupé par un autre écrivain : attendre, pas échouer


def url_de_base(valeur: str | Path | None = None) -> str:
    """URL SQLAlchemy de la base : argument, sinon `CAVE_SCAN_DB`, sinon le défaut.

    Un chemin de fichier devient une base SQLite ; une URL complète
    (`postgresql://…`) est prise telle quelle — c'est le passage à PostgreSQL
    prévu par le guide, sans réécrire le code.
    """
    texte = str(valeur or os.environ.get(VARIABLE_BASE) or BASE_DEFAUT)
    if "://" in texte:
        return texte
    chemin = Path(texte).expanduser().resolve()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{chemin.as_posix()}"


def dossier_stockage(valeur: str | Path | None = None) -> Path:
    """Dossier du stockage des photos : argument, sinon `CAVE_SCAN_STOCKAGE`, sinon le défaut."""
    return Path(valeur or os.environ.get(VARIABLE_STOCKAGE) or STOCKAGE_DEFAUT).expanduser().resolve()


def migrer(url: str) -> None:
    """Amène la base au dernier schéma — par les migrations, jamais par `create_all`."""
    configuration = ConfigAlembic(str(RACINE / "alembic.ini"))
    configuration.set_main_option("script_location", str(RACINE / "migrations"))
    # ConfigParser interprète « % » : un chemin qui en contient doit être protégé.
    configuration.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    configuration.attributes["depuis_le_code"] = True  # pas de reconfiguration des logs
    command.upgrade(configuration, "head")


def creer_moteur(url: str) -> Engine:
    """Moteur SQLAlchemy ; sous SQLite, avec les clés étrangères VÉRIFIÉES.

    SQLite ne les vérifie pas par défaut : une bouteille pourrait pointer vers un
    inventaire inexistant sans que rien ne le signale.
    """
    moteur = create_engine(url)
    if moteur.dialect.name == "sqlite":

        @event.listens_for(moteur, "connect")
        def _configurer_sqlite(connexion: Any, _enregistrement: Any) -> None:
            curseur = connexion.cursor()
            curseur.execute("PRAGMA foreign_keys=ON")
            # Accès concurrents (worker + API, decisions.md 0113) : en WAL, les
            # lecteurs ne bloquent plus l'écrivain ; un écrivain qui trouve la
            # base occupée attend au lieu d'échouer.
            curseur.execute("PRAGMA journal_mode=WAL")
            curseur.execute(f"PRAGMA busy_timeout={ATTENTE_VERROU_MS}")
            curseur.close()

    return moteur


def ouvrir_base(valeur: str | Path | None = None) -> sessionmaker[Session]:
    """Migre la base puis renvoie une fabrique de sessions."""
    url = url_de_base(valeur)
    migrer(url)
    return sessionmaker(creer_moteur(url), expire_on_commit=False)


@contextmanager
def session_de_base(valeur: str | Path | None = None) -> Iterator[Session]:
    """Une session sur la base migrée, et la base FERMÉE en sortant.

    Fermer compte : sous Windows, un fichier SQLite encore ouvert ne peut être
    ni déplacé ni supprimé (le dossier temporaire du dry-run, par exemple).
    """
    url = url_de_base(valeur)
    migrer(url)
    moteur = creer_moteur(url)
    try:
        with Session(moteur, expire_on_commit=False) as session:
            yield session
    finally:
        moteur.dispose()
