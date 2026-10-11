"""Test de navigation de bout en bout (guides des sessions 4 et 6 ; decisions.md
0135, 0167).

Un vrai navigateur (Chromium, écran de téléphone) contre un vrai `dev.py`
(application + worker, extracteur factice) : créer un inventaire, photographier
les bouteilles en mode appareil photo puis en mode galerie, vérifier, lancer,
attendre la fin, télécharger l'Excel.

C'est aussi le seul test du JavaScript d'envoi :
- chaque photo part avec SA bouteille, sa quantité (« × N ») ;
- les photos sont RÉDUITES dans le navigateur quand l'option est cochée ;
- les premiers envois échouent comme sur un réseau qui coupe : le script doit
  réessayer, sans rien perdre ;
- une photo prise pendant une coupure survit à un RECHARGEMENT de la page (elle
  est gardée dans le navigateur jusqu'à sa réception) ;
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


def photo(chemin, rang: int):
    """2600 px de large (au-dessus de la cible de 2 500 : le navigateur la
    réduira), comme sur un téléphone."""
    image = Image.new("RGB", (2600, 1950), ((rang * 41) % 256, (rang * 83) % 256, (rang * 29) % 256))
    image.save(chemin, "JPEG", quality=80)
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


def envoyees(page, nombre):
    page.wait_for_function(f"document.querySelectorAll('.envoi.ok').length === {nombre}", timeout=60_000)


def test_parcours_complet_au_format_telephone(application, telephone, tmp_path):
    dossier = tmp_path / "photos"
    dossier.mkdir()
    a, b, c, d, e, f = (photo(dossier / f"{nom}.jpg", rang) for rang, nom in enumerate("abcdef", start=1))
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
    inventaire_id = page.url.split("/inventaires/")[1].split("/")[0]
    page.get_by_label("Réduire les photos avant l'envoi").check()

    # 2. Mode appareil photo : bouteille 1 = deux photos, × 3 ; bouteille 2 = une photo.
    assert page.inner_text("#titre-en-cours") == "Bouteille 1"
    page.set_input_files("#camera", a)
    page.set_input_files("#camera", b)
    page.get_by_role("button", name="Une bouteille de plus").click()
    page.get_by_role("button", name="Une bouteille de plus").click()
    assert page.input_value("#quantite") == "3"
    assert page.inner_text("#compteur") == "2 / 4 photos"
    assert page.get_by_text("Prendre une photo").bounding_box()["height"] >= 44  # gros boutons, pour le pouce
    page.get_by_role("button", name="Bouteille suivante").click()
    assert page.inner_text("#titre-en-cours") == "Bouteille 2"
    page.set_input_files("#camera", c)
    envoyees(page, 3)
    assert coupures["restantes"] == 0  # les coupures ont bien eu lieu, et ont été rattrapées

    # 3. Coupure franche pendant la bouteille 3, puis la page est rechargée : la
    #    photo prise, gardée dans le navigateur, repart toute seule au retour.
    page.get_by_role("button", name="Bouteille suivante").click()
    coupures["restantes"] = 1000
    page.set_input_files("#camera", d)
    page.wait_for_selector(".envoi.reessai", timeout=30_000)
    page.reload()
    coupures["restantes"] = 0
    envoyees(page, 1)
    assert page.inner_text("#titre-en-cours") == "Bouteille 3"  # la bouteille en cours a survécu
    assert page.inner_text("#compteur") == "1 / 4 photo"

    # 4. Mode galerie : bouteille 4 = deux photos de la galerie, et un fichier refusé.
    page.get_by_role("tab", name="Galerie ou ordinateur").click()
    carte = page.locator(".carte-galerie").first
    assert "Bouteille 4" in carte.inner_text()
    carte.locator("input[type=file]").set_input_files([e, f, pas_une_image])
    envoyees(page, 3)
    page.wait_for_selector(".envoi.refusee", timeout=30_000)
    assert "n'est pas une image lisible" in page.inner_text(".envoi.refusee")

    vue = httpx.get(f"{application}/inventaires/{inventaire_id}/apercu").json()
    assert [[p["nom"] for p in bouteille["photos"]] for bouteille in vue["bouteilles"]] == [
        ["a.jpg", "b.jpg"], ["c.jpg"], ["d.jpg"], ["e.jpg", "f.jpg"]
    ]
    assert [bouteille["quantite"] for bouteille in vue["bouteilles"]] == [3, 1, 1, 1]
    pleine = httpx.get(f"{application}/inventaires/{inventaire_id}/photos/{vue['bouteilles'][0]['photos'][0]['id']}?taille=originale")
    assert max(Image.open(io.BytesIO(pleine.content)).size) == 2500  # réduite dans le navigateur

    # 5. Vérifier, lancer, suivre jusqu'à la fin, télécharger l'Excel.
    page.get_by_role("link", name="Vérifier et lancer").click()
    page.wait_for_url("**/verifier")
    assert page.locator(".carte-attente").count() == 4
    lancer = page.get_by_role("button", name="Lancer l'analyse")
    assert lancer.bounding_box()["height"] >= 44
    lancer.click()
    page.wait_for_url("**/suivi")
    page.get_by_text("Analyse terminée").wait_for(timeout=60_000)
    with page.expect_download() as telechargement:
        page.get_by_role("link", name="Télécharger l'Excel").click()
    fichier = telechargement.value
    assert fichier.suggested_filename == f"inventaire_{inventaire_id}.xlsx"
    fichier.save_as(tmp_path / fichier.suggested_filename)
    feuille = load_workbook(tmp_path / fichier.suggested_filename).active
    assert feuille.max_row - 1 == 4  # 4 bouteilles
    quantites = [feuille.cell(row=r, column=2).value for r in range(2, 6)]
    assert quantites == [3, 1, 1, 1]  # « × 3 » saisi à la capture
