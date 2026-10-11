"""Dépôt des photos par l'API JSON (sessions 4 et 6) : une photo par requête,
rattachée à SA bouteille, idempotent, bouteilles en attente corrigeables,
lancement — aussi après un premier lancement —, et toujours les règles de
sécurité de la session 3."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from src.config.maison import charger_config
from src.extract.fixture_extract import FixtureExtractor
from tests.conftest import CONFIG_TEST, FIXTURES
from tests.test_api import api, extraire_en_arriere_plan, verifier_erreur  # noqa: F401 — fixture partagée
from tests.test_depot import jpeg


def brouillon(api, nom="Vente d'automne") -> int:
    reponse = api.post("/brouillons", json={"nom": nom, "maison": "Maison Test"})
    assert reponse.status_code == 201, reponse.json()
    return reponse.json()["id"]


def envoyer(api, inventaire_id, contenu, nom, bouteille="b1", numero=1, quantite=None, signature=None):
    donnees = {"bouteille": bouteille, "numero": str(numero)}
    donnees.update({k: str(v) for k, v in (("quantite", quantite), ("signature", signature)) if v})
    return api.post(f"/inventaires/{inventaire_id}/photos", files={"fichier": (nom, contenu, "image/jpeg")}, data=donnees)


def apercu(api, inventaire_id):
    return api.get(f"/inventaires/{inventaire_id}/apercu").json()


def bouteilles(api, inventaire_id):
    return [[p["nom"] for p in b["photos"]] for b in apercu(api, inventaire_id)["bouteilles"]]


@pytest.fixture
def trois(api):
    """Trois bouteilles de deux photos, envoyées dans le désordre (réseau qui coupe)."""
    inventaire_id = brouillon(api)
    for rang in (4, 1, 6, 2, 5, 3):
        numero = (rang + 1) // 2
        reponse = envoyer(api, inventaire_id, jpeg(rang), f"photo_{'abcdef'[rang - 1]}.jpg", f"b{numero}", numero)
        assert reponse.status_code == 200 and reponse.json()["deja_recue"] is False, reponse.json()
    return inventaire_id


def test_parcours_depot_bouteille_par_bouteille_lancement_export(api, trois):
    assert bouteilles(api, trois) == [
        ["photo_a.jpg", "photo_b.jpg"], ["photo_d.jpg", "photo_c.jpg"], ["photo_f.jpg", "photo_e.jpg"]
    ]  # dans chaque bouteille : l'ordre d'arrivée ; entre bouteilles : leur numéro
    vue = apercu(api, trois)
    assert vue["peut_lancer"] is True and vue["prochain_numero"] == 4 and vue["photos_max"] == 4

    finalise = api.post(f"/inventaires/{trois}/finaliser")
    assert finalise.status_code == 200, finalise.json()
    assert finalise.json()["nb_bouteilles"] == 3 and finalise.json()["progression"]["extraction"] == "lancee"

    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))[:3]
    extraire_en_arriere_plan_deja_lance(api, trois, FixtureExtractor(charges, charger_config(CONFIG_TEST)))
    export = api.get(f"/inventaires/{trois}/export")
    assert export.status_code == 200 and len(export.content) > 1000


def extraire_en_arriere_plan_deja_lance(api, inventaire_id, extracteur, attendues=3):
    """Comme `extraire_en_arriere_plan`, l'inventaire étant déjà lancé par la finalisation."""
    import threading

    from src.donnees.base import creer_moteur, url_de_base
    from src.worker import ReglagesWorker, Worker
    from tests.test_worker import attendre

    moteur = creer_moteur(url_de_base(api.base_db))
    arret = threading.Event()
    reglages = ReglagesWorker(simultanees=1, periode_vie_s=0.2, attente_s=0.05)
    thread = threading.Thread(target=Worker(moteur, api.stockage, lambda c: extracteur, reglages).tourner, args=(arret,))
    thread.start()
    try:
        attendre(lambda: api.get(f"/inventaires/{inventaire_id}").json()["progression"]["terminee"], message="fin")
    finally:
        arret.set()
        thread.join(30)
        moteur.dispose()
    assert api.get(f"/inventaires/{inventaire_id}").json()["progression"]["par_statut"]["extraite"] == attendues


def test_une_photo_renvoyee_n_est_enregistree_qu_une_fois(api, trois):
    renvoi = envoyer(api, trois, jpeg(1), "autre_nom.jpg", "b9", 9)
    assert renvoi.status_code == 200 and renvoi.json()["deja_recue"] is True and renvoi.json()["numero"] == 1
    assert apercu(api, trois)["nb_photos"] == 6


def test_reprise_les_fichiers_deja_recus_ne_sont_pas_renvoyes(api):
    inventaire_id = brouillon(api)
    envoyer(api, inventaire_id, jpeg(1), "a.jpg", signature="a.jpg|100|1")
    reponse = api.post(f"/inventaires/{inventaire_id}/photos/deja-recues", json={"signatures": ["a.jpg|100|1", "b.jpg|200|2"]})
    assert reponse.json() == {"deja_recues": ["a.jpg|100|1"]}


def test_quantite_a_la_capture_puis_corrigee(api):
    inventaire_id = brouillon(api)
    envoyer(api, inventaire_id, jpeg(1), "a.jpg", "b1", 1, quantite=12)
    assert apercu(api, inventaire_id)["bouteilles"][0]["quantite"] == 12
    corrigee = api.put(f"/inventaires/{inventaire_id}/bouteilles-en-cours/b1/quantite", json={"quantite": 6})
    assert corrigee.status_code == 200 and corrigee.json()["bouteilles"][0]["quantite"] == 6
    groupe = corrigee.json()["bouteilles"][0]["groupe_id"]
    assert api.put(f"/inventaires/{inventaire_id}/groupes/{groupe}/quantite", json={"quantite": 2}).json()["bouteilles"][0]["quantite"] == 2


def test_couper_rattacher_supprimer(api, trois):
    photo_b = next(p for p in apercu(api, trois)["bouteilles"][0]["photos"] if p["nom"] == "photo_b.jpg")
    coupee = api.post(f"/inventaires/{trois}/photos/{photo_b['id']}/couper").json()
    assert [[p["nom"] for p in b["photos"]] for b in coupee["bouteilles"]] == [
        ["photo_a.jpg"], ["photo_b.jpg"], ["photo_d.jpg", "photo_c.jpg"], ["photo_f.jpg", "photo_e.jpg"]
    ]
    rattachee = api.post(f"/inventaires/{trois}/groupes/{coupee['bouteilles'][1]['groupe_id']}/rattacher").json()
    assert len(rattachee["bouteilles"]) == 3
    supprimee = api.delete(f"/inventaires/{trois}/groupes/{rattachee['bouteilles'][2]['groupe_id']}").json()
    assert len(supprimee["bouteilles"]) == 2 and supprimee["nb_photos"] == 4


def test_lancement_refuse_sans_bouteille_en_attente(api):
    inventaire_id = brouillon(api)
    verifier_erreur(api.post(f"/inventaires/{inventaire_id}/finaliser"), 409, "lancement_refuse", "Aucune bouteille en attente")


def test_apres_lancement_les_photos_d_une_bouteille_ne_bougent_plus(api, trois):
    photo = apercu(api, trois)["bouteilles"][0]["photos"][0]["id"]
    groupe = apercu(api, trois)["bouteilles"][0]["groupe_id"]
    api.post(f"/inventaires/{trois}/finaliser")
    for reponse in (
        envoyer(api, trois, jpeg(50), "tard.jpg", "b1", 1),
        api.delete(f"/inventaires/{trois}/photos/{photo}"),
        api.post(f"/inventaires/{trois}/photos/{photo}/couper"),
        api.delete(f"/inventaires/{trois}/groupes/{groupe}"),
    ):
        verifier_erreur(reponse, 409, "depot_ferme", "déjà analysée")


def test_ajouter_une_bouteille_apres_le_lancement(api, trois):
    api.post(f"/inventaires/{trois}/finaliser")
    prochain = apercu(api, trois)["prochain_numero"]
    assert envoyer(api, trois, jpeg(40), "nouvelle.jpg", "b-nouvelle", prochain).status_code == 200
    vue = apercu(api, trois)
    assert vue["deja_formees"] == 3 and vue["bouteilles"][0]["numero"] == 4
    assert api.post(f"/inventaires/{trois}/finaliser").json()["nb_bouteilles"] == 1
    liste = api.get(f"/inventaires/{trois}/bouteilles").json()["bouteilles"]
    assert [b["position"] for b in liste] == [1, 2, 3, 4]


def test_un_brouillon_ne_se_lance_pas_sans_etre_finalise(api, trois):
    verifier_erreur(api.post(f"/inventaires/{trois}/lancer"), 409, "lancement_refuse", "brouillon")


@pytest.mark.parametrize(
    "contenu, nom, raison",
    [(b"pas une image", "note.jpg", "n'est pas une image lisible"), (b"\x00\x00\x00\x18ftypheic", "IMG_1.HEIC", "n'est pas une image lisible")],
)
def test_non_image_et_heic_illisible_refuses_avec_une_raison_claire(api, contenu, nom, raison):
    inventaire_id = brouillon(api)
    verifier_erreur(envoyer(api, inventaire_id, contenu, nom), 422, "envoi_refuse", raison)
    assert apercu(api, inventaire_id)["nb_photos"] == 0


def test_le_plafond_de_photos_est_explique(api):
    inventaire_id = brouillon(api)
    for rang in range(4):
        envoyer(api, inventaire_id, jpeg(rang), f"{rang}.jpg")
    verifier_erreur(envoyer(api, inventaire_id, jpeg(9), "de_trop.jpg"), 422, "envoi_refuse", "4 photos au plus")


def test_une_correction_impossible_est_expliquee(api, trois):
    premiere = apercu(api, trois)["bouteilles"][0]
    verifier_erreur(
        api.post(f"/inventaires/{trois}/photos/{premiere['photos'][0]['id']}/couper"),
        422, "modification_refusee", "déjà la première photo",
    )


def test_securite_photo_d_un_autre_inventaire_et_aucun_exif(api, trois):
    autre = brouillon(api, "Autre vente")
    photo = apercu(api, trois)["bouteilles"][0]["photos"][0]
    verifier_erreur(api.get(f"/inventaires/{autre}/photos/{photo['id']}?taille=miniature"), 404, "introuvable", "Aucune photo")
    verifier_erreur(api.delete(f"/inventaires/{autre}/photos/{photo['id']}"), 404, "introuvable", "Aucune photo")

    miniature = api.get(photo["miniature"])
    assert miniature.status_code == 200
    assert dict(Image.open(io.BytesIO(miniature.content)).getexif()) == {}
    assert "prise_de_vue" not in api.get(f"/inventaires/{trois}/apercu").text  # jamais renvoyée
