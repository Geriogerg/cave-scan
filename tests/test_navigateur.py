"""Test de navigation de bout en bout (guide de session 4, §5 ; decisions.md 0135).

Un vrai navigateur (Chromium, écran de téléphone) contre un vrai `dev.py`
(application + worker, extracteur factice) : créer un inventaire, envoyer 6
photos, inverser une paire, lancer, attendre la fin, télécharger l'Excel.

C'est aussi le seul test du JavaScript d'envoi :
- les photos sont RÉDUITES dans le navigateur, ce qui efface leur EXIF, et
  leurs noms sont dans l'ordre INVERSE de leurs dates : seul un script qui lit
  la date AVANT la réduction donne le bon ordre ;
- les premiers envois échouent comme sur un réseau qui coupe : le script doit
  réessayer, sans rien perdre ;
- un fichier qui n'est pas une image est refusé, avec sa raison affichée.

Aucune pause fixe : chaque attente porte sur une condition, avec une limite.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys

import httpx
import pytest
from openpyxl import load_workbook
from PIL import Image

from tests.conftest import RACINE
from tests.test_lancement import port_libre
from tests.test_worker import attendre

sync_api = pytest.importorskip("playwright.sync_api")


def photo_datee(chemin, rang: int):
    """2600 px de large (au-dessus de la cible de 2 500 : le navigateur la
    réduira), date de prise de vue dans l'EXIF, comme sur un téléphone."""
    image = Image.new("RGB", (2600, 1950), ((rang * 41) % 256, (rang * 83) % 256, (rang * 29) % 256))
    exif = Image.Exif()
    exif[0x8769] = {0x9003: f"2026:09:17 15:56:{rang:02d}"}  # DateTimeOriginal
    image.save(chemin, "JPEG", exif=exif.tobytes(), quality=80)
    return chemin


@pytest.fixture
def application(tmp_path):
    port = port_libre()
    environnement = dict(os.environ, CAVE_SCAN_STOCKAGE=str(tmp_path / "stockage"), PYTHONIOENCODING="utf-8")
    for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        environnement.pop(variable, None)
    processus = subprocess.Popen(
        [sys.executable, str(RACINE / "dev.py"), "--port", str(port), "--base", str(tmp_path / "base.db"),
         "--backend", "factice", "--latence", "0.05", "--attente", "0.1"],
        cwd=RACINE, env=environnement, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"

    def repond():
        try:
            return httpx.get(f"{url}/app", timeout=1).status_code == 200
        except httpx.HTTPError:
            return False

    try:
        attendre(repond, message="dev.py répond")
        yield url
    finally:
        processus.kill()
        processus.wait(30)


@pytest.fixture
def telephone():
    with sync_api.sync_playwright() as p:
        try:
            navigateur = p.chromium.launch()
        except Exception as erreur:  # pragma: no cover — Chromium non installé
            pytest.skip(f"Chromium indisponible ({erreur}) : python -m playwright install chromium")
        contexte = navigateur.new_context(**p.devices["Pixel 7"], accept_downloads=True)
        yield contexte
        contexte.close()
        navigateur.close()


def test_parcours_complet_au_format_telephone(application, telephone, tmp_path):
    dossier = tmp_path / "galerie"
    dossier.mkdir()
    # Noms dans l'ordre INVERSE des dates : « f » est la plus ancienne.
    photos = [photo_datee(dossier / f"{'fedcba'[rang - 1]}_photo.jpg", rang) for rang in range(1, 7)]
    pas_une_image = dossier / "note.jpg"
    pas_une_image.write_bytes(b"ceci n'est pas une photo")

    page = telephone.new_page()
    page.on("dialog", lambda dialogue: dialogue.accept())  # confirmations (« Lancer l'analyse ? »)

    # Réseau qui coupe : les deux premiers envois de photo échouent.
    coupures = {"restantes": 2}

    def reseau_instable(route):
        if route.request.method == "POST" and coupures["restantes"] > 0:
            coupures["restantes"] -= 1
            route.abort("internetdisconnected")
        else:
            route.continue_()

    page.route("**/inventaires/*/photos", reseau_instable)

    # 1. Accueil -> nouvel inventaire.
    page.goto(f"{application}/app")
    page.get_by_role("link", name="Nouvel inventaire").click()
    page.get_by_label("Nom de la vente").fill("Vente test navigateur")
    page.get_by_role("button", name="Créer et ajouter les photos").click()
    page.wait_for_url("**/depot")

    # 2. Dépôt : réduction cochée, 6 photos + un fichier qui n'est pas une image.
    page.get_by_label("Réduire les photos avant l'envoi").check()
    page.set_input_files("#galerie", [*photos, pas_une_image])
    page.wait_for_function("document.querySelectorAll('.envoi.ok').length === 6", timeout=60_000)
    page.wait_for_selector(".envoi.refusee", timeout=30_000)
    assert "n'est pas une image lisible" in page.inner_text(".envoi.refusee")
    assert coupures["restantes"] == 0  # les coupures ont bien eu lieu, et ont été rattrapées

    inventaire_id = page.url.split("/inventaires/")[1].split("/")[0]
    apercu = httpx.get(f"{application}/inventaires/{inventaire_id}/apercu").json()
    noms = [p[cote]["nom"] for p in apercu["paires"] for cote in ("etiquette", "contre_etiquette")]
    # L'ordre des DATES (lues avant réduction), pas celui des noms.
    assert noms == ["f_photo.jpg", "e_photo.jpg", "d_photo.jpg", "c_photo.jpg", "b_photo.jpg", "a_photo.jpg"]
    assert apercu["tri"] == "date de prise de vue"
    pleine = httpx.get(f"{application}/inventaires/{inventaire_id}/photos/{apercu['paires'][0]['etiquette']['id']}?taille=originale")
    assert max(Image.open(io.BytesIO(pleine.content)).size) == 2500  # réduite dans le navigateur

    # 3. Vérifier l'ordre, inverser la paire n°2.
    page.get_by_role("link", name="Vérifier l'ordre").click()
    page.wait_for_url("**/ordre")
    assert page.locator(".paire").count() == 3
    lancer = page.get_by_role("button", name="Lancer l'analyse")
    assert lancer.bounding_box()["height"] >= 44  # gros boutons, pour le pouce
    page.locator(".paire").nth(1).get_by_role("button", name="Inverser").click()
    attendre(
        lambda: httpx.get(f"{application}/inventaires/{inventaire_id}/apercu").json()["paires"][1]["etiquette"]["nom"]
        == "c_photo.jpg",
        message="paire inversée",
    )

    # 4. Lancer, suivre jusqu'à la fin, télécharger l'Excel.
    page.get_by_role("button", name="Lancer l'analyse").click()
    page.wait_for_url("**/suivi")
    page.get_by_text("Analyse terminée").wait_for(timeout=60_000)
    with page.expect_download() as telechargement:
        page.get_by_role("link", name="Télécharger l'Excel").click()
    fichier = telechargement.value
    assert fichier.suggested_filename == f"inventaire_{inventaire_id}.xlsx"
    fichier.save_as(tmp_path / fichier.suggested_filename)
    feuille = load_workbook(tmp_path / fichier.suggested_filename).active
    assert feuille.max_row - 1 == 3  # 3 bouteilles
