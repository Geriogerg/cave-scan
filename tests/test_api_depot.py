"""Dépôt des photos par l'API JSON (session 4) : une photo par requête,
idempotent, ordre corrigeable, finalisation, et toujours les règles de sécurité
de la session 3."""

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


def brouillon(api, nom="Vente d'automne", sans_contre=False) -> int:
    reponse = api.post("/brouillons", json={"nom": nom, "maison": "Maison Test", "sans_contre": sans_contre})
    assert reponse.status_code == 201, reponse.json()
    return reponse.json()["id"]


def envoyer(api, inventaire_id, contenu, nom, date=None, signature=None):
    donnees = {k: v for k, v in (("prise_de_vue", date), ("signature", signature)) if v}
    return api.post(f"/inventaires/{inventaire_id}/photos", files={"fichier": (nom, contenu, "image/jpeg")}, data=donnees)


def apercu(api, inventaire_id):
    return api.get(f"/inventaires/{inventaire_id}/apercu").json()


def ordre(api, inventaire_id):
    return [
        (p["etiquette"]["nom"], p["contre_etiquette"]["nom"] if p["contre_etiquette"] else None)
        for p in apercu(api, inventaire_id)["paires"]
    ]


@pytest.fixture
def six(api):
    """Six photos envoyées dans le désordre, avec leur date de prise de vue."""
    inventaire_id = brouillon(api)
    for rang in (4, 1, 6, 2, 5, 3):
        reponse = envoyer(api, inventaire_id, jpeg(rang), f"photo_{'abcdef'[rang - 1]}.jpg", f"2026-09-17T15:56:{rang:02d}")
        assert reponse.status_code == 200 and reponse.json()["deja_recue"] is False
    return inventaire_id


def test_parcours_brouillon_depot_ordre_lancement_export(api, six):
    assert ordre(api, six) == [("photo_a.jpg", "photo_b.jpg"), ("photo_c.jpg", "photo_d.jpg"), ("photo_e.jpg", "photo_f.jpg")]
    assert apercu(api, six)["peut_lancer"] is True

    inverse = api.post(f"/inventaires/{six}/paires/2/inverser").json()
    assert inverse["paires"][1]["etiquette"]["nom"] == "photo_d.jpg"

    finalise = api.post(f"/inventaires/{six}/finaliser")
    assert finalise.status_code == 200, finalise.json()
    assert finalise.json()["nb_bouteilles"] == 3 and finalise.json()["progression"]["extraction"] == "lancee"

    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))[:3]
    extraire_en_arriere_plan_deja_lance(api, six, FixtureExtractor(charges, charger_config(CONFIG_TEST)))
    export = api.get(f"/inventaires/{six}/export")
    assert export.status_code == 200 and len(export.content) > 1000


def extraire_en_arriere_plan_deja_lance(api, inventaire_id, extracteur):
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
    assert api.get(f"/inventaires/{inventaire_id}").json()["progression"]["par_statut"]["extraite"] == 3


def test_une_photo_renvoyee_n_est_enregistree_qu_une_fois(api, six):
    renvoi = envoyer(api, six, jpeg(1), "autre_nom.jpg")
    assert renvoi.status_code == 200 and renvoi.json()["deja_recue"] is True
    assert apercu(api, six)["nb_photos"] == 6


def test_reprise_les_fichiers_deja_recus_ne_sont_pas_renvoyes(api):
    inventaire_id = brouillon(api)
    envoyer(api, inventaire_id, jpeg(1), "a.jpg", signature="a.jpg|100|1")
    reponse = api.post(f"/inventaires/{inventaire_id}/photos/deja-recues", json={"signatures": ["a.jpg|100|1", "b.jpg|200|2"]})
    assert reponse.json() == {"deja_recues": ["a.jpg|100|1"]}


def test_lancement_refuse_si_impair_avec_le_message_prevu(api, six):
    photo = apercu(api, six)["paires"][0]["etiquette"]["id"]
    apres = api.delete(f"/inventaires/{six}/photos/{photo}").json()
    assert apres["peut_lancer"] is False and "Nombre impair de photos (5)" in apres["anomalies"][0]
    verifier_erreur(api.post(f"/inventaires/{six}/finaliser"), 409, "lancement_refuse", "Nombre impair de photos (5)")


def test_apres_finalisation_plus_aucune_modification(api, six):
    photo = apercu(api, six)["paires"][0]["etiquette"]["id"]
    api.post(f"/inventaires/{six}/finaliser")
    for reponse in (
        envoyer(api, six, jpeg(50), "tard.jpg"),
        api.delete(f"/inventaires/{six}/photos/{photo}"),
        api.post(f"/inventaires/{six}/photos/{photo}/deplacer", json={"position": 2}),
        api.post(f"/inventaires/{six}/paires/1/inverser"),
        api.post(f"/inventaires/{six}/retrier"),
    ):
        verifier_erreur(reponse, 409, "depot_ferme", "ne peuvent plus être modifiées")
    assert apercu(api, six)["nb_photos"] == 6


def test_un_brouillon_ne_se_lance_pas_sans_etre_finalise(api, six):
    verifier_erreur(api.post(f"/inventaires/{six}/lancer"), 409, "lancement_refuse", "brouillon")


@pytest.mark.parametrize(
    "contenu, nom, raison",
    [(b"pas une image", "note.jpg", "n'est pas une image lisible"), (b"\x00\x00\x00\x18ftypheic", "IMG_1.HEIC", "Le plus compatible")],
)
def test_non_image_et_heic_refuses_avec_une_raison_claire(api, contenu, nom, raison):
    inventaire_id = brouillon(api)
    verifier_erreur(envoyer(api, inventaire_id, contenu, nom), 422, "envoi_refuse", raison)
    assert apercu(api, inventaire_id)["nb_photos"] == 0


def test_une_correction_impossible_est_expliquee(api, six):
    photo = apercu(api, six)["paires"][0]["etiquette"]["id"]
    verifier_erreur(api.post(f"/inventaires/{six}/photos/{photo}/deplacer", json={"position": 7}), 422, "modification_refusee", "entre 1 et 6")


def test_securite_photo_d_un_autre_inventaire_et_aucun_exif(api, six):
    autre = brouillon(api, "Autre vente")
    photo = apercu(api, six)["paires"][0]["etiquette"]
    verifier_erreur(api.get(f"/inventaires/{autre}/photos/{photo['id']}?taille=miniature"), 404, "introuvable", "Aucune photo")
    verifier_erreur(api.delete(f"/inventaires/{autre}/photos/{photo['id']}"), 404, "introuvable", "Aucune photo")

    miniature = api.get(photo["miniature"])
    assert miniature.status_code == 200
    assert dict(Image.open(io.BytesIO(miniature.content)).getexif()) == {}
    texte = api.get(f"/inventaires/{six}/apercu").text
    assert "2026" not in texte and "prise_de_vue" not in texte  # la date sert au tri, jamais renvoyée
    assert photo["datee"] is True


def test_etiquettes_seules_par_l_api(api):
    inventaire_id = brouillon(api, sans_contre=True)
    for rang in range(1, 4):
        envoyer(api, inventaire_id, jpeg(rang), f"e{rang}.jpg", f"2026-09-17T15:00:0{rang}")
    vue = apercu(api, inventaire_id)
    assert vue["sans_contre"] and vue["peut_lancer"] and len(vue["paires"]) == 3
    assert api.post(f"/inventaires/{inventaire_id}/finaliser").json()["nb_bouteilles"] == 3
