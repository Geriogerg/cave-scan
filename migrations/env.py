"""Environnement Alembic : relie les migrations au modèle de données.

Mode « batch » (`render_as_batch`) : SQLite ne sait pas modifier une colonne en
place ; Alembic recopie alors la table. Sans lui, la première évolution du
schéma pendant le pilote échouerait (decisions.md 0075).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from src.donnees.base import url_de_base
from src.donnees.modeles import Base

configuration = context.config

# Logs configurés seulement quand Alembic est lancé en ligne de commande : appelé
# depuis le code (ou les tests), il ne doit pas reconfigurer la journalisation.
if configuration.config_file_name and not configuration.attributes.get("depuis_le_code"):
    fileConfig(configuration.config_file_name)

URL = configuration.get_main_option("sqlalchemy.url") or url_de_base()
METADONNEES = Base.metadata


def migrer_hors_ligne() -> None:
    """Génère le SQL sans se connecter (`alembic upgrade head --sql`)."""
    context.configure(
        url=URL,
        target_metadata=METADONNEES,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def migrer_en_ligne() -> None:
    # Moteur simple, clés étrangères NON forcées pendant la migration : le mode
    # batch recopie les tables, ce que des clés étrangères actives feraient
    # échouer sous SQLite. Aucune connexion gardée ouverte (NullPool).
    moteur = create_engine(URL, poolclass=pool.NullPool)
    with moteur.connect() as connexion:
        context.configure(
            connection=connexion,
            target_metadata=METADONNEES,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    moteur.dispose()


if context.is_offline_mode():
    migrer_hors_ligne()
else:
    migrer_en_ligne()
