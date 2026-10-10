"""Les commandes de lancement, dans de vrais processus (decisions.md 0119).

Chaque test attend une CONDITION (le serveur répond, l'inventaire est extrait)
avec une limite de temps, jamais une durée fixe.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys

import httpx
import pytest

import serveur
from src.extract.fixture_extract import generer_photos_fictives
from tests.conftest import RACINE
from tests.test_worker import attendre


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def lancer(script: str, tmp_path, *options: str) -> tuple[subprocess.Popen, str]:
    port = port_libre()
    environnement = dict(os.environ, CAVE_SCAN_STOCKAGE=str(tmp_path / "stockage"), PYTHONIOENCODING="utf-8")
    for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        environnement.pop(variable, None)
    processus = subprocess.Popen(
        [sys.executable, str(RACINE / script), "--port", str(port), "--base", str(tmp_path / "base.db"), *options],
        cwd=RACINE, env=environnement, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return processus, f"http://127.0.0.1:{port}"


def repond(url: str) -> bool:
    try:
        return httpx.get(f"{url}/docs", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
def processus():
    lances = []
    yield lances
    for p in lances:
        p.kill()
        p.wait(30)


def test_le_serveur_n_ecoute_qu_en_local():
    assert serveur.HOTE == "127.0.0.1"
    assert "--host" not in serveur.analyseur().format_help()


def test_serveur_py_demarre_et_sert_la_documentation(tmp_path, processus):
    p, url = lancer("serveur.py", tmp_path)
    processus.append(p)
    attendre(lambda: repond(url), message="le serveur répond")
    assert httpx.get(f"{url}/inventaires").json() == []


def test_dev_py_api_et_worker_extraient_un_inventaire(tmp_path, processus):
    p, url = lancer("dev.py", tmp_path, "--backend", "factice", "--latence", "0.05", "--attente", "0.1")
    processus.append(p)
    attendre(lambda: repond(url), message="dev.py répond")

    photos = generer_photos_fictives(tmp_path / "photos", 3)
    cree = httpx.post(
        f"{url}/inventaires",
        data={"nom": "Démo", "maison": "Maison Test"},
        files=[("photos", (f.name, f.read_bytes(), "image/jpeg")) for f in sorted(photos.iterdir())],
        timeout=30,
    )
    assert cree.status_code == 201, cree.text
    inventaire_id = cree.json()["id"]
    assert httpx.post(f"{url}/inventaires/{inventaire_id}/lancer").json()["effectuee"] is True

    attendre(
        lambda: httpx.get(f"{url}/inventaires/{inventaire_id}").json()["progression"]["terminee"],
        message="le worker de dev.py a tout extrait",
    )
    assert httpx.get(f"{url}/inventaires/{inventaire_id}").json()["progression"]["par_statut"]["extraite"] == 3


# --- réseau local : seulement sur option explicite, avec avertissement (decisions.md 0132) ---------


def test_par_defaut_le_serveur_n_ecoute_qu_en_local(capsys):
    assert serveur.analyseur().parse_args([]).reseau_local is False
    assert serveur.annoncer(False, 8000) == "127.0.0.1"
    assert "RÉSEAU LOCAL" not in capsys.readouterr().err


def test_le_mode_reseau_local_avertit_et_donne_l_adresse_du_telephone(capsys, monkeypatch):
    monkeypatch.setattr(serveur, "adresse_sur_le_reseau", lambda: "192.168.1.42")
    assert serveur.annoncer(True, 8000) == "0.0.0.0"
    avertissement = capsys.readouterr().err
    assert "MODE RÉSEAU LOCAL" in avertissement and "jamais sur le réseau d'un client" in avertissement
    assert "http://192.168.1.42:8000/" in avertissement


@pytest.mark.parametrize("options, hote", [([], "127.0.0.1"), (["--reseau-local"], "0.0.0.0")])
def test_serveur_et_dev_ecoutent_la_ou_on_le_demande(options, hote, monkeypatch, tmp_path):
    import uvicorn

    import dev

    ecoutes = []
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port, log_level: ecoutes.append(host))
    assert serveur.main(["--base", str(tmp_path / "a.db"), *options]) == 0
    assert dev.main(["--base", str(tmp_path / "b.db"), "--backend", "factice", "--attente", "0.05", *options]) == 0
    assert ecoutes == [hote, hote]
