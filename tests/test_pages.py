"""Les écrans web (sessions 4 et 6) : chaque page s'affiche, le parcours complet
fonctionne avec l'extracteur factice, et les garde-fous restent côté serveur.

Le navigateur est simulé par le client de test : les envois de photos passent
par la même route que le script d'envoi (POST /inventaires/{id}/photos, une
photo à la fois pour SA bouteille), les actions HTMX par leurs routes, avec
l'en-tête HX-Request.
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


def creer(api, nom="Vente de printemps") -> int:
    reponse = api.post("/app/nouveau", data={"nom": nom, "maison": "Maison Test"}, follow_redirects=False)
    assert reponse.status_code == 303, reponse.text
    return int(re.search(r"/app/inventaires/(\d+)/depot", reponse.headers["location"]).group(1))


def deposer(api, inventaire_id, bouteilles=3, photos=2, premier=1):
    """`bouteilles` bouteilles de `photos` photos, comme l'appareil photo les envoie."""
    couleur = premier * 10
    for numero in range(premier, premier + bouteilles):
        for _ in range(photos):
            couleur += 1
            reponse = envoyer(api, inventaire_id, jpeg(couleur), f"IMG_{couleur:04d}.jpg", f"b{numero}", numero)
            assert reponse.status_code == 200, reponse.json()


def attente(api, inventaire_id):
    return api.get(f"/inventaires/{inventaire_id}/apercu").json()["bouteilles"]


def test_chaque_page_s_affiche(api):
    assert api.get("/", follow_redirects=False).headers["location"] == "/app"
    accueil = api.get("/app")
    assert accueil.status_code == 200 and "Nouvel inventaire" in accueil.text and "Aucun inventaire" in accueil.text
    nouveau = api.get("/app/nouveau")
    # Une instance = une maison (decisions.md 0171) : aucun choix, aucune mention.
    assert nouveau.status_code == 200 and "Nom de la vente" in nouveau.text and "Maison" not in nouveau.text
    assert "sans_contre" not in nouveau.text  # l'option « étiquettes seules » a disparu (0166)

    inventaire_id = creer(api)
    depot = api.get(f"/app/inventaires/{inventaire_id}/depot")
    assert depot.status_code == 200
    for texte in ("Appareil photo", "Galerie ou ordinateur", "Prendre une photo", 'capture="environment"',
                  "Bouteille suivante", "Ajouter une bouteille", 'data-max="4"', "/static/depot.js"):
        assert texte in depot.text, texte
    assert 'id="reduire"' in depot.text and 'id="reduire" checked' not in depot.text  # réduction désactivée (0130)
    verifier = api.get(f"/app/inventaires/{inventaire_id}/verifier")
    assert verifier.status_code == 200 and "Aucune photo pour" in verifier.text and 'id="lancer" disabled' in verifier.text
    assert "Vente de printemps" in api.get("/app").text
    assert api.get(f"/app/inventaires/{inventaire_id}", follow_redirects=False).headers["location"].endswith("/depot")


def test_les_pages_n_appellent_aucun_script_exterieur(api):
    """Ni framework ni CDN : HTMX et le script d'envoi sont servis par l'application."""
    for adresse in ("/app", "/app/nouveau"):
        scripts = re.findall(r'<script[^>]*src="([^"]+)"', api.get(adresse).text)
        assert scripts and all(src.startswith("/static/") for src in scripts)
    assert api.get("/static/htmx.min.js").headers["content-type"].startswith("text/javascript")
    assert api.get("/static/depot.js").status_code == 200


def test_parcours_depot_verification_lancement_suivi_export(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id)

    page = api.get(f"/app/inventaires/{inventaire_id}/verifier").text
    assert page.count("<strong>Bouteille ") == 3 and "Lancer l'analyse" in page
    assert 'id="lancer" disabled' not in page

    seconde = attente(api, inventaire_id)[0]["photos"][1]["id"]
    coupee = api.post(f"/app/inventaires/{inventaire_id}/verifier/couper/{seconde}", headers=HX)
    assert coupee.status_code == 200 and coupee.text.count("<strong>Bouteille ") == 4
    groupe = attente(api, inventaire_id)[1]["groupe_id"]
    rattachee = api.post(f"/app/inventaires/{inventaire_id}/verifier/rattacher/{groupe}", headers=HX)
    assert rattachee.text.count("<strong>Bouteille ") == 3

    lance = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX)
    assert lance.status_code == 204 and lance.headers["HX-Redirect"] == f"/app/inventaires/{inventaire_id}/suivi"

    suivi = api.get(f"/app/inventaires/{inventaire_id}/suivi")
    # La relecture (session 5) s'ouvre dès la première bouteille analysée.
    assert suivi.status_code == 200 and "dès la première bouteille analysée" in suivi.text
    assert 'hx-trigger="every 3s"' in suivi.text  # se met à jour toute seule
    assert f"/app/inventaires/{inventaire_id}/depot" in suivi.text  # « Ajouter des bouteilles »

    extraire_en_arriere_plan_deja_lance(api, inventaire_id, ExtracteurFactice(charger_config(CONFIG_TEST)))
    fin = api.get(f"/app/inventaires/{inventaire_id}/progression").text
    assert "Analyse terminée" in fin and f"/app/inventaires/{inventaire_id}/excel" in fin
    assert "Relire les bouteilles" in fin and f"/app/inventaires/{inventaire_id}/relecture" in fin
    assert 'hx-trigger="every 3s"' not in fin  # plus de rafraîchissement une fois terminée
    export = api.get(f"/inventaires/{inventaire_id}/export")
    assert export.status_code == 200
    assert "Analyse terminée" in api.get("/app").text


def test_lancement_refuse_sans_bouteille_en_attente(api):
    inventaire_id = creer(api)
    # Le bouton est désactivé, mais le SERVEUR refuse aussi : jamais un garde-fou
    # tenu seulement par le navigateur.
    refus = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX)
    assert refus.status_code == 200 and "Aucune bouteille en attente" in refus.text
    assert api.get(f"/inventaires/{inventaire_id}").json()["statut"] == "brouillon"


def test_retirer_une_photo_supprimer_une_bouteille_changer_la_quantite(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=2)
    premiere = attente(api, inventaire_id)[0]
    apres = api.post(f"/app/inventaires/{inventaire_id}/verifier/retirer-photo/{premiere['photos'][0]['id']}", headers=HX)
    assert apres.status_code == 200 and "2 bouteille(s) en attente · 3 photo(s)" in apres.text

    quantite = api.post(f"/app/inventaires/{inventaire_id}/verifier/quantite/{premiere['groupe_id']}", data={"quantite": "6"}, headers=HX)
    assert 'value="6"' in quantite.text
    refus = api.post(f"/app/inventaires/{inventaire_id}/verifier/quantite/{premiere['groupe_id']}", data={"quantite": "zéro"}, headers=HX)
    assert "Quantité invalide" in refus.text

    supprimee = api.post(f"/app/inventaires/{inventaire_id}/verifier/supprimer/{premiere['groupe_id']}", headers=HX)
    assert "1 bouteille(s) en attente" in supprimee.text


def test_la_quantite_tapee_part_avec_le_lancement(api):
    """Rapport du testeur, T1-B1 : une quantité tapée sans quitter son champ ne
    doit jamais être perdue au lancement."""
    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=2, photos=1)
    groupes = [b["groupe_id"] for b in attente(api, inventaire_id)]
    page = api.get(f"/app/inventaires/{inventaire_id}/verifier").text
    assert 'hx-include=".quantite-attente"' in page and 'hx-trigger="change, submit"' in page
    refus = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX,
                     data={"groupe": [str(g) for g in groupes], "quantite": ["6", "zéro"]})
    assert "Quantité invalide" in refus.text and "Rien n&#39;a été lancé" in refus.text
    assert api.get(f"/inventaires/{inventaire_id}").json()["statut"] == "brouillon"
    lance = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX,
                     data={"groupe": [str(g) for g in groupes], "quantite": ["6", "1"]})
    assert lance.status_code == 204
    quantites = [b["quantite"] for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]]
    assert quantites == [6, 1]


def test_ajouter_des_bouteilles_apres_le_lancement(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=2, photos=1)
    api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX)

    depot = api.get(f"/app/inventaires/{inventaire_id}/depot")
    assert depot.status_code == 200 and "Ajouter des bouteilles" in depot.text and 'data-prochain="3"' in depot.text
    assert envoyer(api, inventaire_id, jpeg(77), "tard.jpg", "b1", 1).json()["code"] == "depot_ferme"  # déjà formée
    deposer(api, inventaire_id, bouteilles=1, photos=1, premier=3)
    suivi = api.get(f"/app/inventaires/{inventaire_id}/suivi").text
    assert "1 bouteille(s) ajoutée(s)" in suivi and "pas encore lancée(s)" in suivi
    lance = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX)
    assert lance.status_code == 204
    assert api.get(f"/inventaires/{inventaire_id}").json()["progression"]["total"] == 3


def test_nouvel_inventaire_sans_nom_reaffiche_le_formulaire_avec_la_raison(api):
    reponse = api.post("/app/nouveau", data={"nom": "  ", "maison": "Maison Test"})
    assert reponse.status_code == 422 and "Donnez un nom à la vente" in reponse.text and "<form" in reponse.text


def test_relancer_les_erreurs_depuis_le_suivi(api):
    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=1)
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
    deposer(api, inventaire_id, bouteilles=1)
    for adresse in (f"/app/inventaires/{inventaire_id}/verifier", f"/app/inventaires/{inventaire_id}/depot", "/app"):
        texte = api.get(adresse).text
        assert "15:56" not in texte and "exif" not in texte.lower() and "gps" not in texte.lower()
    vignette = re.search(r'src="(/inventaires/\d+/photos/\d+\?taille=miniature)"', api.get(f"/app/inventaires/{inventaire_id}/verifier").text)
    assert vignette and api.get(vignette.group(1)).headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("adresse", ["/app", "/app/nouveau"])
def test_mise_en_page_telephone(api, adresse):
    texte = api.get(adresse).text
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in texte
    assert 'class="barre-actions"' in texte  # actions principales en bas de l'écran


def test_un_refus_de_quantite_s_affiche_dans_sa_carte(api):
    """T4-D5 : sur « Vérifier », le refus est sous le champ de la bouteille concernée."""
    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=2, photos=1)
    seconde = attente(api, inventaire_id)[1]["groupe_id"]
    refus = api.post(f"/app/inventaires/{inventaire_id}/verifier/quantite/{seconde}", data={"quantite": "0"}, headers=HX).text
    carte = refus.split(f'id="groupe-{seconde}"')[1]
    assert 'id="refus-quantite"' in carte and "Quantité invalide" in carte
    assert 'class="message alerte"' not in refus.split('<ol class="liste-attente">')[0]
