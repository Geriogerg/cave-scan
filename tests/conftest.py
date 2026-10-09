"""Rend le paquet `src` importable, et isole les tests de la base de l'utilisateur.

On insère la RACINE du projet, jamais `src/` lui-même : `src/io` masquerait le
module `io` de la stdlib.

Base et stockage : CHAQUE test tourne avec `CAVE_SCAN_DB` et `CAVE_SCAN_STOCKAGE`
pointés vers un dossier temporaire — aucun test ne peut toucher la vraie base ni
les vraies photos stockées (decisions.md 0085).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def base_et_stockage_isoles(tmp_path, monkeypatch):
    """Garde-fou : même un test qui oublie de préciser sa base n'atteint jamais
    `data/cave_scan.db`."""
    monkeypatch.setenv("CAVE_SCAN_DB", str(tmp_path / "isolee" / "cave_scan.db"))
    monkeypatch.setenv("CAVE_SCAN_STOCKAGE", str(tmp_path / "isolee" / "stockage"))


@pytest.fixture(scope="session")
def base_modele(tmp_path_factory):
    """Une base migrée UNE fois par les vraies migrations, recopiée par chaque test.

    Migrer à chaque test serait lent ; créer les tables avec `create_all`
    testerait un autre schéma que celui des migrations.
    """
    from src.donnees.base import migrer, url_de_base

    chemin = tmp_path_factory.mktemp("modele") / "modele.db"
    migrer(url_de_base(chemin))
    return chemin


@pytest.fixture
def session(base_modele, tmp_path):
    """Session sur une copie fraîche de la base modèle."""
    from sqlalchemy.orm import sessionmaker

    from src.donnees.base import creer_moteur, url_de_base

    chemin = tmp_path / "base.db"
    shutil.copy(base_modele, chemin)
    moteur = creer_moteur(url_de_base(chemin))
    fabrique = sessionmaker(moteur, expire_on_commit=False)
    with fabrique() as ouverte:
        yield ouverte
    moteur.dispose()  # Windows : libère le fichier avant le nettoyage du dossier


@pytest.fixture
def stockage(tmp_path):
    dossier = tmp_path / "stockage"
    dossier.mkdir()
    return dossier
