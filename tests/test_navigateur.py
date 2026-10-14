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
    assert page.inner_text("#compteur") == "1 / 4 photos"

    # 4. Mode galerie : bouteille 4 = deux photos de la galerie, et un fichier refusé.
    page.get_by_role("tab", name="Galerie ou ordinateur").click()
    # La galerie montre d'abord les bouteilles déjà photographiées (T3-D12), puis la nouvelle.
    assert page.locator(".carte-galerie").count() == 4
    carte = page.locator(".carte-galerie").last
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
    # Le nom de la vente et la date, accents compris (T3-DS2).
    assert fichier.suggested_filename.startswith("Vente test navigateur — ") and fichier.suggested_filename.endswith(".xlsx")
    fichier.save_as(tmp_path / fichier.suggested_filename)
    feuille = load_workbook(tmp_path / fichier.suggested_filename).active
    assert feuille.max_row - 1 == 4  # 4 bouteilles
    quantites = [feuille.cell(row=r, column=2).value for r in range(2, 6)]
    assert quantites == [3, 1, 1, 1]  # « × 3 » saisi à la capture


def test_en_mode_galerie_la_premiere_carte_est_la_bouteille_1(application, telephone, tmp_path):
    """Rapport du testeur, T1-m4 : la bouteille vide de l'appareil photo ne prend
    pas de numéro ; les numéros du dépôt sont ceux de l'écran « Vérifier »."""
    dossier = tmp_path / "photos"
    dossier.mkdir()
    a, b = photo(dossier / "a.jpg", 1), photo(dossier / "b.jpg", 2)
    page = telephone.new_page()
    page.goto(f"{application}/app")
    page.get_by_role("link", name="Nouvel inventaire").click()
    page.get_by_label("Nom de la vente").fill("Vente galerie")
    page.get_by_role("button", name="Créer et ajouter les photos").click()
    page.wait_for_url("**/depot")
    page.get_by_role("tab", name="Galerie ou ordinateur").click()
    carte = page.locator(".carte-galerie").first
    assert "Bouteille 1" in carte.inner_text()
    carte.locator("input[type=file]").set_input_files([a])
    envoyees(page, 1)
    page.get_by_role("button", name="Ajouter une bouteille").click()
    seconde = page.locator(".carte-galerie").nth(1)
    assert "Bouteille 2" in seconde.inner_text()
    seconde.locator("input[type=file]").set_input_files([b])
    envoyees(page, 2)
    page.get_by_role("link", name="Vérifier et lancer").click()
    page.wait_for_url("**/verifier")
    titres = page.locator(".carte-attente .attente-titre strong").all_inner_texts()
    assert titres == ["Bouteille 1", "Bouteille 2"]


def test_configuration_la_colonne_modifiee_reste_ouverte(application, telephone):
    """Rapport du testeur, T2-B2 / T2-D2 : après « Ajouter une valeur » ou ↑, la
    colonne en cours d'édition reste ouverte (et la colonne déplacée aussi)."""
    page = telephone.new_page()
    page.goto(f"{application}/app/configuration/maison_test")
    bouton = page.locator('button[value^="ajouter_valeur-"]').first
    index = int(bouton.get_attribute("value").split("-")[1])
    colonne = page.locator(f"#colonne-{index}")
    colonne.locator("details.colonne-detail > summary").click()
    colonne.locator(f'button[value="ajouter_valeur-{index}"]').click()
    page.wait_for_function(f"document.querySelector('#colonne-{index} details.colonne-detail').open === true", timeout=10_000)
    lignes = page.locator(f"#colonne-{index} .valeurs-config tbody tr")
    assert lignes.last.is_visible()

    page.locator(f'#colonne-{index} button[value="monter-{index}"]').click()
    page.wait_for_function(f"document.querySelector('#colonne-{index - 1} details.colonne-detail').open === true", timeout=10_000)


def test_reprendre_une_bouteille_depuis_un_autre_appareil_garde_sa_quantite(application, telephone, tmp_path):
    """Rapport du testeur, T3-D1 / T3-D12 : un autre appareil voit les bouteilles
    déjà reçues (en galerie aussi), avec leur quantité ; y ajouter une photo ne
    la remet jamais à 1."""
    dossier = tmp_path / "photos"
    dossier.mkdir()
    a, b = photo(dossier / "a.jpg", 1), photo(dossier / "b.jpg", 2)
    page = telephone.new_page()
    page.goto(f"{application}/app")
    page.get_by_role("link", name="Nouvel inventaire").click()
    page.get_by_label("Nom de la vente").fill("Vente deux appareils")
    page.get_by_role("button", name="Créer et ajouter les photos").click()
    page.wait_for_url("**/depot")
    inventaire_id = page.url.split("/inventaires/")[1].split("/")[0]
    page.set_input_files("#camera", a)
    envoyees(page, 1)
    page.fill("#quantite", "6")
    page.locator("#quantite").dispatch_event("change")
    attendre(lambda: httpx.get(f"{application}/inventaires/{inventaire_id}/apercu").json()["bouteilles"][0]["quantite"] == 6,
             message="quantité 6 reçue")

    ordinateur = telephone.browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        autre = ordinateur.new_page()
        autre.goto(f"{application}/app/inventaires/{inventaire_id}/depot")
        autre.get_by_role("tab", name="Galerie ou ordinateur").click()
        carte = autre.locator(".carte-galerie").first
        assert "Bouteille 1" in carte.inner_text()
        assert carte.locator("input[inputmode=numeric]").input_value() == "6"
        carte.locator("input[type=file]").set_input_files([b])
        autre.wait_for_function("document.querySelectorAll('.envoi.ok').length === 1", timeout=60_000)
        vue = httpx.get(f"{application}/inventaires/{inventaire_id}/apercu").json()
        assert [(len(x["photos"]), x["quantite"]) for x in vue["bouteilles"]] == [(2, 6)]
    finally:
        ordinateur.close()


def test_consignes_case_de_confirmation_cachee_jusqu_au_deverrouillage(application, telephone):
    """T3-D6 : la case « Je confirme… » n'apparaît qu'après le « êtes-vous sûr ? »."""
    page = telephone.new_page()
    page.goto(f"{application}/app/configuration/maison_test")
    page.locator("details.consignes > summary").click()
    assert page.locator("#confirmer-consignes").is_hidden()
    assert page.eval_on_selector("#consignes", "e => e.readOnly")
    page.once("dialog", lambda dialogue: dialogue.accept())
    page.click("#deverrouiller-consignes")
    assert page.locator("#confirmer-consignes").is_visible()
    assert not page.eval_on_selector("#consignes", "e => e.readOnly")


def test_en_galerie_le_refus_d_une_photo_est_dans_la_carte(application, telephone, tmp_path):
    """T3-D5 / T4-B6 : à l'ordinateur (galerie), la raison d'un refus est dans la
    carte de la bouteille, pas seulement en bas de page."""
    dossier = tmp_path / "photos"
    dossier.mkdir()
    faux = dossier / "faux.jpg"
    faux.write_bytes(b"pas une image")
    ordinateur = telephone.browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = ordinateur.new_page()
        page.goto(f"{application}/app")
        page.get_by_role("link", name="Nouvel inventaire").click()
        page.get_by_label("Nom de la vente").fill("Vente refus galerie")
        page.get_by_role("button", name="Créer et ajouter les photos").click()
        page.wait_for_url("**/depot")
        page.get_by_role("tab", name="Galerie ou ordinateur").click()
        carte = page.locator(".carte-galerie").first
        carte.locator("input[type=file]").set_input_files([faux])
        page.wait_for_selector(".carte-galerie .refus-bouteille", timeout=30_000)
        assert "faux.jpg" in page.locator(".carte-galerie .refus-bouteille").inner_text()
    finally:
        ordinateur.close()


def test_un_double_appui_sur_creer_ne_cree_qu_un_inventaire(application, telephone):
    """T4-B7 : au doigt, deux appuis sur « Créer et ajouter les photos » = un inventaire."""
    page = telephone.new_page()
    page.goto(f"{application}/app/nouveau")
    page.get_by_label("Nom de la vente").fill("Vente double appui")
    # Deux appuis à 80 ms, comme au doigt, avant que la page ne change.
    page.evaluate("() => { const b = document.querySelector('button[form=formulaire-nouveau]'); b.click(); setTimeout(() => b.click(), 80); }")
    page.wait_for_timeout(1500)
    page.wait_for_url("**/depot")
    noms = [i["nom"] for i in httpx.get(f"{application}/inventaires").json()]
    assert noms.count("Vente double appui") == 1


def test_une_coupure_reseau_sur_verifier_est_signalee(application, telephone, tmp_path):
    """T4-B5 : une action de « Vérifier » qui ne part pas (réseau coupé) le dit,
    au lieu d'un écran qui ne bouge pas."""
    page = telephone.new_page()
    page.goto(f"{application}/app/nouveau")
    page.get_by_label("Nom de la vente").fill("Vente coupure")
    page.get_by_role("button", name="Créer et ajouter les photos").click()
    page.wait_for_url("**/depot")
    page.get_by_role("tab", name="Galerie ou ordinateur").click()
    page.locator(".carte-galerie").first.locator("input[type=file]").set_input_files([photo(tmp_path / "1.jpg", 1)])
    envoyees(page, 1)
    page.goto(page.url.replace("/depot", "/verifier"))
    page.route("**/verifier/quantite/*", lambda route: route.abort("internetdisconnected"))
    quantite = page.get_by_label("Quantité de la bouteille 1")
    quantite.fill("2")
    quantite.press("Enter")
    page.wait_for_selector("#erreur-serveur", timeout=10_000)
    assert "Connexion interrompue" in page.inner_text("#erreur-serveur")
    # T5-D2 : dans la carte aussi, et la saisie reste dans le champ.
    page.wait_for_selector(".carte-attente .non-enregistree", timeout=5_000)
    assert quantite.input_value() == "2"


def test_au_bureau_des_photos_glissees_sur_une_carte_rejoignent_sa_bouteille(application, telephone):
    """T4-DS1 : à l'ordinateur, glisser des photos sur une carte de la galerie les
    envoie avec cette bouteille ; le curseur est prêt dans « Nom de la vente » (T4-DS2)."""
    ordinateur = telephone.browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = ordinateur.new_page()
        page.goto(f"{application}/app/nouveau")
        assert page.evaluate("document.activeElement.name") == "nom"
        page.keyboard.type("Vente glissée")
        page.get_by_role("button", name="Créer et ajouter les photos").click()
        page.wait_for_url("**/depot")
        page.get_by_role("tab", name="Galerie ou ordinateur").click()
        page.evaluate("""async () => {
            const toile = document.createElement("canvas");
            toile.width = 64; toile.height = 48;
            const transfert = new DataTransfer();
            for (const [nom, couleur] of [["a.jpg", "#b03030"], ["b.jpg", "#3050b0"]]) {
                const dessin = toile.getContext("2d");
                dessin.fillStyle = couleur;
                dessin.fillRect(0, 0, 64, 48);
                const image = await new Promise((ok) => toile.toBlob(ok, "image/jpeg"));
                transfert.items.add(new File([image], nom, { type: "image/jpeg" }));
            }
            const carte = document.querySelector(".carte-galerie");
            carte.dispatchEvent(new DragEvent("dragover", { dataTransfer: transfert, bubbles: true, cancelable: true }));
            carte.dispatchEvent(new DragEvent("drop", { dataTransfer: transfert, bubbles: true, cancelable: true }));
        }""")
        envoyees(page, 2)
        page.evaluate("""() => document.body.dispatchEvent(new DragEvent("drop", { dataTransfer: new DataTransfer(), bubbles: true, cancelable: true }))""")
        assert "Déposez les photos sur la carte" in page.inner_text("#resume-texte")  # T5-DS1
        page.get_by_role("tab", name="Appareil photo").click()
        assert "Bouteille 1 · 2 photos" in page.inner_text("#precedentes")  # T5-D3
        page.get_by_role("tab", name="Galerie ou ordinateur").click()
        inventaire_id = page.url.split("/inventaires/")[1].split("/")[0]
        apercu = httpx.get(f"{application}/inventaires/{inventaire_id}/apercu", headers={"Accept": "application/json"}).json()
        assert [len(b["photos"]) for b in apercu["bouteilles"]] == [2]
    finally:
        ordinateur.close()


def test_galerie_une_carte_vide_les_doublons_dans_la_carte_et_un_seul_onglet(application, telephone, tmp_path):
    """T5-B14 : la barre disparaît une fois tout envoyé ; T5-B7 : « déjà dans la
    bouteille 1 » dans la carte ; T5-B6 : « Ajouter une bouteille » deux fois = une
    seule carte vide ; T5-B11 : le même dépôt ouvert dans un second onglet se signale."""
    ordinateur = telephone.browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = ordinateur.new_page()
        page.goto(f"{application}/app/nouveau")
        page.get_by_label("Nom de la vente").fill("Vente galerie")
        page.get_by_role("button", name="Créer et ajouter les photos").click()
        page.wait_for_url("**/depot")
        page.get_by_role("tab", name="Galerie ou ordinateur").click()
        premiere = photo(tmp_path / "1.jpg", 1)
        page.locator(".carte-galerie").first.locator("input[type=file]").set_input_files([premiere])
        envoyees(page, 1)
        page.wait_for_function("document.getElementById('barre').hidden", timeout=5_000)
        assert "1 envoyée" in page.inner_text("#resume-texte")

        page.locator(".carte-galerie").first.locator("input[type=file]").set_input_files([premiere])
        page.wait_for_selector(".carte-galerie .refus-bouteille", timeout=5_000)
        assert "déjà dans la bouteille 1" in page.locator(".carte-galerie").first.inner_text()

        ajouter = page.get_by_role("button", name="Ajouter une bouteille")
        ajouter.click()
        ajouter.click()
        vides = page.evaluate("""() => [...document.querySelectorAll('.carte-galerie')]
            .filter((carte) => carte.querySelectorAll('.vignette-depot').length === 0).length""")
        assert vides == 1

        autre = ordinateur.new_page()
        autre.goto(page.url)
        page.wait_for_selector("#autre-onglet", state="visible", timeout=5_000)
        autre.wait_for_selector("#autre-onglet", state="visible", timeout=5_000)
    finally:
        ordinateur.close()


def test_configuration_la_colonne_ajoutee_est_prete_a_nommer(application, telephone):
    """T5-D5 : après « Ajouter une colonne », son nom a le focus et se voit."""
    page = telephone.new_page()
    page.goto(f"{application}/app/configuration/maison_test")
    page.get_by_role("button", name="Ajouter une colonne").click()
    page.wait_for_function("/^c[0-9]+_nom$/.test(document.activeElement.name || '')", timeout=10_000)
    assert page.evaluate("document.activeElement.value") == ""


def test_depot_quantite_refusee_gardee_et_suivante_grisee_sans_photo(application, telephone):
    """T6-D4 : au téléphone, une quantité refusée reste dans son champ, la raison
    sous la rangée ; T6-B5 : « Bouteille suivante » grisée tant qu'il n'y a pas
    de photo."""
    page = telephone.new_page()
    page.goto(f"{application}/app/nouveau")
    page.get_by_label("Nom de la vente").fill("Vente quantité")
    page.get_by_role("button", name="Créer et ajouter les photos").click()
    page.wait_for_url("**/depot")
    page.wait_for_function("document.getElementById('suivante').getAttribute('aria-disabled') === 'true'", timeout=5_000)
    champ = page.locator(".quantite-depot input").first
    champ.fill("0")
    champ.press("Tab")
    page.wait_for_selector(".refus-quantite", timeout=5_000)
    assert champ.input_value() == "0"
    assert page.locator(".quantite-depot .refus-quantite").count() == 0  # sous la rangée, pas dedans


def test_configuration_la_valeur_ajoutee_est_prete_a_saisir(application, telephone):
    """T6-B9 : après « Ajouter une valeur », le curseur est dans son libellé."""
    page = telephone.new_page()
    page.goto(f"{application}/app/configuration/maison_test")
    bouton = page.locator('button[value^="ajouter_valeur-"]').first
    index = bouton.get_attribute("value").split("-")[1]
    page.locator(f"#colonne-{index} details.colonne-detail > summary").click()
    page.locator(f'#colonne-{index} button[value="ajouter_valeur-{index}"]').click()
    page.wait_for_function("/_libelle$/.test(document.activeElement.name || '')", timeout=10_000)

