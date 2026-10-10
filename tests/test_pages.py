"""Les écrans web (session 4) : chaque page s'affiche, le parcours complet
fonctionne avec l'extracteur factice, et les garde-fous restent côté serveur.

Le navigateur est simulé par le client de test : les envois de photos passent
par la même route que le script d'envoi (POST /inventaires/{id}/photos), les
actions HTMX par leurs routes, avec l'en-tête HX-Request.
"""

from __future__ import annotations

import re

import pytest

from src.config.maison import charger_config
from src.extract.factice import ExtracteurFactice
from tests.conftest import CONFIG_TEST
from tests.test_api import api  # noqa: F401 — fixture partagée
from tests.test_api_depot import envoyer, extraire_en_arriere_plan_deja_lance
from tests.test_depot import jpeg

HX = {"HX-Request": "true"}


def creer(api, nom="Vente de printemps", sans_contre=False) -> int:
    donnees = {"nom": nom, "maison": "Maison Test"}
    if sans_contre:
        donnees["sans_contre"] = "true"
    reponse = api.post("/app/nouveau", data=donnees, follow_redirects=False)
    assert reponse.status_code == 303, reponse.text
    return int(re.search(r"/app/inventaires/(\d+)/depot", reponse.headers["location"]).group(1))


def deposer(api, inventaire_id, nombre=6):
    for rang in range(1, nombre + 1):
        reponse = envoyer(api, inventaire_id, jpeg(rang), f"IMG_{rang:04d}.jpg", f"2026-09-17T15:56:{rang:02d}")
        assert reponse.status_code == 200, reponse.json()


def test_chaque_page_s_affiche(api):
    assert api.get("/", follow_redirects=False).headers["location"] == "/app"
    accueil = api.get("/app")
    assert accueil.status_code == 200 and "Nouvel inventaire" in accueil.text and "Aucun inventaire" in accueil.text
    nouveau = api.get("/app/nouveau")
    assert nouveau.status_code == 200 and "Maison Test" in nouveau.text

    inventaire_id = creer(api)
    depot = api.get(f"/app/inventaires/{inventaire_id}/depot")
    assert depot.status_code == 200
    for texte in ("Choisir dans la galerie", "Prendre une photo", 'capture="environment"', "multiple", "/static/depot.js"):
        assert texte in depot.text
    assert 'id="reduire"' in depot.text and 'id="reduire" checked' not in depot.text  # réduction désactivée (0130)
    ordre = api.get(f"/app/inventaires/{inventaire_id}/ordre")
    assert ordre.status_code == 200 and "Aucune photo pour" in ordre.text
    assert "Vente de printemps" in api.get("/app").text
    assert api.get(f"/app/inventaires/{inventaire_id}", follow_redirects=False).headers["location"].endswith("/depot")


def test_les_pages_n_appellent_aucun_script_exterieur(api):
    """Ni framework ni CDN : HTMX et le script d'envoi sont servis par l'application."""
    for adresse in ("/app", "/app/nouveau"):
        scripts = re.findall(r'<script[^>]*src="([^"]+)"', api.get(adresse).text)
        assert scripts and all(src.startswith("/static/") for src in scripts)
    assert api.get("/static/htmx.min.js").headers["content-type"].startswith("text/javascript")
    assert api.get("/static/depot.js").status_code == 200


def test_parcours_brouillon_depot_ordre_lancement_suivi_export(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id)

    ordre = api.get(f"/app/inventaires/{inventaire_id}/ordre").text
    assert ordre.count("Bouteille ") == 3 and "Lancer l'analyse" in ordre
    assert 'id="lancer" disabled' not in ordre

    inverse = api.post(f"/app/inventaires/{inventaire_id}/ordre/inverser/2", headers=HX)
    assert inverse.status_code == 200
    vignettes = re.findall(r"photo (\d+)", inverse.text)
    assert "ordre corrigé à la main" in inverse.text and vignettes

    lance = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX)
    assert lance.status_code == 204 and lance.headers["HX-Redirect"] == f"/app/inventaires/{inventaire_id}/suivi"

    suivi = api.get(f"/app/inventaires/{inventaire_id}/suivi")
    assert suivi.status_code == 200 and "Relecture — bientôt disponible" in suivi.text
    assert 'hx-trigger="every 3s"' in suivi.text  # se met à jour toute seule

    extraire_en_arriere_plan_deja_lance(api, inventaire_id, ExtracteurFactice(charger_config(CONFIG_TEST)))
    fin = api.get(f"/app/inventaires/{inventaire_id}/progression").text
    assert "Analyse terminée" in fin and f"/inventaires/{inventaire_id}/export" in fin
    assert 'hx-trigger="every 3s"' not in fin  # plus de rafraîchissement une fois terminée
    export = api.get(f"/inventaires/{inventaire_id}/export")
    assert export.status_code == 200
    assert "Analyse terminée" in api.get("/app").text


def test_lancement_refuse_si_impair_avec_le_message_prevu(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id, nombre=5)
    ordre = api.get(f"/app/inventaires/{inventaire_id}/ordre").text
    assert "Nombre impair de photos (5)" in ordre and 'id="lancer" disabled' in ordre
    assert "Contre-étiquette manquante" in ordre

    # Le bouton est désactivé, mais le SERVEUR refuse aussi : jamais un garde-fou
    # tenu seulement par le navigateur.
    refus = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX)
    assert refus.status_code == 200 and "Nombre impair de photos (5)" in refus.text
    assert "Supprimez la photo en trop" in refus.text
    assert api.get(f"/inventaires/{inventaire_id}").json()["statut"] == "brouillon"


def test_supprimer_et_deplacer_depuis_la_page(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id, nombre=4)
    photos = api.get(f"/inventaires/{inventaire_id}/apercu").json()["paires"]
    premiere, derniere = photos[0]["etiquette"]["id"], photos[1]["contre_etiquette"]["id"]

    api.post(f"/app/inventaires/{inventaire_id}/ordre/deplacer/{derniere}", data={"position": 1}, headers=HX)
    assert api.get(f"/inventaires/{inventaire_id}/apercu").json()["paires"][0]["etiquette"]["id"] == derniere
    apres = api.post(f"/app/inventaires/{inventaire_id}/ordre/supprimer/{premiere}", headers=HX)
    assert "Nombre impair de photos (3)" in apres.text
    retrie = api.post(f"/app/inventaires/{inventaire_id}/ordre/retrier", headers=HX)
    assert "classées par date de prise de vue" in retrie.text


def test_apres_le_lancement_les_photos_ne_bougent_plus(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id, nombre=2)
    api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX)
    assert api.get(f"/app/inventaires/{inventaire_id}/depot", follow_redirects=False).headers["location"].endswith("/suivi")
    refus = api.post(f"/app/inventaires/{inventaire_id}/ordre/inverser/1", headers=HX)
    assert "ne peuvent plus être modifiées" in refus.text
    assert envoyer(api, inventaire_id, jpeg(77), "tard.jpg").json()["code"] == "depot_ferme"


def test_nouvel_inventaire_sans_nom_reaffiche_le_formulaire_avec_la_raison(api):
    reponse = api.post("/app/nouveau", data={"nom": "  ", "maison": "Maison Test"})
    assert reponse.status_code == 422 and "Donner un nom" in reponse.text and "<form" in reponse.text


def test_etiquettes_seules_depuis_les_pages(api):
    inventaire_id = creer(api, sans_contre=True)
    deposer(api, inventaire_id, nombre=3)
    ordre = api.get(f"/app/inventaires/{inventaire_id}/ordre").text
    assert ordre.count("Bouteille ") == 3 and "Inverser" not in ordre and 'id="lancer" disabled' not in ordre


def test_relancer_les_erreurs_depuis_le_suivi(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id, nombre=2)
    api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX)
    reponse = api.post(f"/app/inventaires/{inventaire_id}/relancer-erreurs", headers=HX)
    assert reponse.status_code == 200 and 'id="progression"' in reponse.text


def test_une_page_introuvable_s_affiche_en_francais(api):
    reponse = api.get("/app/inventaires/999/suivi")
    assert reponse.status_code == 404
    assert "text/html" in reponse.headers["content-type"] and "Aucun inventaire n°999" in reponse.text
    assert api.get("/inventaires/999").json()["code"] == "introuvable"  # l'API, elle, reste en JSON


def test_aucune_date_ni_exif_dans_les_pages(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id, nombre=2)
    for adresse in (f"/app/inventaires/{inventaire_id}/ordre", f"/app/inventaires/{inventaire_id}/depot", "/app"):
        texte = api.get(adresse).text
        assert "15:56" not in texte and "exif" not in texte.lower() and "gps" not in texte.lower()
    vignette = re.search(r'src="(/inventaires/\d+/photos/\d+\?taille=miniature)"', api.get(f"/app/inventaires/{inventaire_id}/ordre").text)
    assert vignette and api.get(vignette.group(1)).headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("adresse", ["/app", "/app/nouveau"])
def test_mise_en_page_telephone(api, adresse):
    texte = api.get(adresse).text
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in texte
    assert 'class="barre-actions"' in texte  # actions principales en bas de l'écran
