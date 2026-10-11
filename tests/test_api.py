"""API JSON : critères d'acceptation du guide de session 3.

Hors ligne : le worker tourne dans le test avec un extracteur de fixtures ; les
attentes portent sur une CONDITION (progression terminée), jamais une durée.
"""

from __future__ import annotations

import io
import json
import shutil
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image

import inventaire as cli_inventaire
import run_v0
from src.api.app import creer_app
from src.config.maison import charger_config
from src.donnees.base import creer_moteur, url_de_base
from src.extract.fixture_extract import FixtureExtractor, generer_photos_fictives
from src.worker import ReglagesWorker, Worker
from tests.conftest import CONFIG_TEST, FIXTURES
from tests.test_worker import attendre

AUTEUR = {"X-Auteur": "Expert test"}


def charges():
    return json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))


@pytest.fixture
def api(tmp_path):
    base, stockage = tmp_path / "api.db", tmp_path / "stockage"
    app = creer_app(base, stockage=stockage)
    with TestClient(app) as client:
        client.base_db, client.stockage = base, stockage
        yield client


def envoyer(api, dossier: Path, nom="Cave Dupont", maison="Maison Test"):
    """Le dossier comme la ligne de commande le lit : une photo à la racine = une
    bouteille, un sous-dossier = une bouteille et ses photos (decisions.md 0166),
    envoyé d'un coup avec `photos_par_bouteille`."""
    from src.io.photos import cle_naturelle

    fichiers, tailles = [], []
    for entree in sorted(dossier.iterdir(), key=lambda p: cle_naturelle(p.name)):
        photos = sorted(entree.iterdir(), key=lambda p: cle_naturelle(p.name)) if entree.is_dir() else [entree]
        fichiers += [("photos", (p.name, p.read_bytes(), "image/jpeg")) for p in photos]
        tailles.append(str(len(photos)))
    return api.post(
        "/inventaires",
        data={"nom": nom, "maison": maison, "photos_par_bouteille": ",".join(tailles)},
        files=fichiers,
    )


def extraire_en_arriere_plan(api, inventaire_id: int, extracteur) -> None:
    """Lance par l'API, fait tourner un worker, attend la FIN lue par l'API."""
    assert api.post(f"/inventaires/{inventaire_id}/lancer").json()["effectuee"] is True
    moteur = creer_moteur(url_de_base(api.base_db))
    arret = threading.Event()
    worker = Worker(moteur, api.stockage, lambda config: extracteur, ReglagesWorker(simultanees=1, periode_vie_s=0.2, attente_s=0.05))
    thread = threading.Thread(target=worker.tourner, args=(arret,))
    thread.start()
    try:
        attendre(
            lambda: api.get(f"/inventaires/{inventaire_id}").json()["progression"]["terminee"],
            message="extraction terminée",
        )
    finally:
        arret.set()
        thread.join(30)
        moteur.dispose()


def contenu_excel(chemin_ou_octets) -> list[list]:
    source = io.BytesIO(chemin_ou_octets) if isinstance(chemin_ou_octets, bytes) else chemin_ou_octets
    feuille = load_workbook(source).active
    return [
        [(cellule.value, cellule.fill.fgColor.rgb if cellule.fill and cellule.fill.fill_type else None) for cellule in ligne]
        for ligne in feuille.iter_rows()
    ]


# --- parcours complet ---------------------------------------------------------------------


def test_parcours_complet_et_excel_identique_a_la_ligne_de_commande(api, dossier_photos, tmp_path, monkeypatch):
    # 1. Créer avec les photos, lancer, attendre la fin.
    cree = envoyer(api, dossier_photos)
    assert cree.status_code == 201, cree.json()
    inventaire_id = cree.json()["id"]
    assert cree.json()["nb_bouteilles"] == 6
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    etat = api.get(f"/inventaires/{inventaire_id}").json()
    assert etat["progression"]["par_statut"]["extraite"] == 6 and etat["extraction"] == "lancee"

    # 2. Lister, corriger, valider, exporter.
    page = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()
    assert page["total"] == 6 and [b["position"] for b in page["bouteilles"]] == list(range(1, 7))
    premiere = page["bouteilles"][0]["id"]
    corrigee = api.post(
        f"/inventaires/{inventaire_id}/bouteilles/{premiere}/corrections",
        json={"champ": "millesime", "valeur": "2001"},
        headers=AUTEUR,
    )
    assert corrigee.status_code == 200, corrigee.json()
    assert corrigee.json()["valeurs_courantes"]["millesime"] == "2001"
    assert corrigee.json()["valeurs_modele"]["millesime"] == "2018"  # le modèle, intact
    # Pas de validation en masse (decisions.md 0138) : chaque bouteille se valide
    # une par une ; valider l'inventaire ne fait que le constater.
    refus = api.post(f"/inventaires/{inventaire_id}/valider", headers=AUTEUR)
    assert refus.status_code == 409 and "6 bouteille(s) à relire" in refus.json()["message"]
    for bouteille in page["bouteilles"]:
        une = api.post(f"/inventaires/{inventaire_id}/bouteilles/{bouteille['id']}/valider", headers=AUTEUR)
        assert une.status_code == 200, une.json()
    valide = api.post(f"/inventaires/{inventaire_id}/valider", headers=AUTEUR)
    assert valide.status_code == 200 and valide.json()["nombre"] == 6
    assert api.get(f"/inventaires/{inventaire_id}").json()["statut"] == "valide"
    export = api.get(f"/inventaires/{inventaire_id}/export")
    assert export.status_code == 200
    assert "attachment" in export.headers["content-disposition"]

    # 3. Les mêmes données par la ligne de commande : même Excel.
    base_cli, sortie_cli = tmp_path / "cli.db", tmp_path / "cli.xlsx"
    monkeypatch.setattr(run_v0, "_extracteur", lambda *a: FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    assert run_v0.main(["--photos", str(dossier_photos), "--base", str(base_cli), "--sortie", str(tmp_path / "x.xlsx")]) == 0
    assert cli_inventaire.main(["corriger", "1", "1", "millesime", "2001", "--auteur", "Expert test", "--base", str(base_cli)]) == 0
    assert cli_inventaire.main(["exporter", "1", "--sortie", str(sortie_cli), "--base", str(base_cli)]) == 0

    assert contenu_excel(export.content) == contenu_excel(sortie_cli)


def test_lancer_deux_fois_ne_change_rien(api, dossier_photos):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    assert api.post(f"/inventaires/{inventaire_id}/lancer").json()["effectuee"] is True
    deuxieme = api.post(f"/inventaires/{inventaire_id}/lancer").json()
    assert deuxieme["effectuee"] is False and deuxieme["progression"]["extraction"] == "lancee"
    assert api.post(f"/inventaires/{inventaire_id}/annuler").json()["progression"]["extraction"] == "annulee"


# --- refus avec un message clair ----------------------------------------------------------


def verifier_erreur(reponse, statut, code, extrait):
    corps = reponse.json()
    assert reponse.status_code == statut, corps
    assert set(corps) == {"code", "message", "detail"}
    assert corps["code"] == code
    assert extrait in corps["message"]


def test_un_regroupement_qui_ne_correspond_pas_aux_photos_est_refuse(api, dossier_photos):
    """On ne devine jamais quelle photo va avec quelle bouteille (decisions.md 0166)."""
    fichiers = [("photos", (f"{i}.jpg", (dossier_photos / "bouteille_01" / "1_etiquette.jpg").read_bytes(), "image/jpeg")) for i in range(3)]
    reponse = api.post("/inventaires", data={"nom": "Cave", "maison": "Maison Test", "photos_par_bouteille": "2,2"}, files=fichiers)
    verifier_erreur(reponse, 422, "envoi_refuse", "ne correspond pas aux 3 photos")
    assert api.get("/inventaires").json() == []  # rien n'a été créé


def test_sans_regroupement_une_photo_par_bouteille(api, dossier_photos):
    fichiers = [("photos", (p.name, p.read_bytes(), "image/jpeg")) for p in sorted((dossier_photos / "bouteille_01").iterdir())]
    reponse = api.post("/inventaires", data={"nom": "Cave", "maison": "Maison Test"}, files=fichiers)
    assert reponse.status_code == 201 and reponse.json()["nb_bouteilles"] == 2


def test_un_fichier_qui_n_est_pas_une_image_est_refuse(api, dossier_photos):
    (dossier_photos / "bouteille_06" / "2_contre.jpg").write_bytes(b"ceci n'est pas une photo")
    verifier_erreur(envoyer(api, dossier_photos), 422, "envoi_refuse", "n'est pas une image lisible")


def test_une_photo_heic_d_iphone_est_acceptee(api, dossier_photos):
    """decisions.md 0158 : lue, stockée telle quelle, affichée en JPEG."""
    from PIL import Image

    jpeg = dossier_photos / "bouteille_06" / "2_contre.jpg"
    with Image.open(jpeg) as image:
        image.save(dossier_photos / "bouteille_06" / "2_contre.heic", format="HEIF")
    jpeg.unlink()
    reponse = envoyer(api, dossier_photos)
    assert reponse.status_code == 201, reponse.text
    inventaire_id = reponse.json()["id"]
    bouteille = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"][-1]
    fiche = api.get(f"/inventaires/{inventaire_id}/bouteilles/{bouteille['id']}").json()
    affichee = api.get(fiche["photos"][1]["reduite"])
    assert affichee.status_code == 200 and affichee.headers["content-type"] == "image/jpeg"


def test_photos_en_double_refusees(api, dossier_photos):
    shutil.copytree(dossier_photos / "bouteille_01", dossier_photos / "bouteille_07")
    verifier_erreur(envoyer(api, dossier_photos), 422, "photos_invalides", "deux fois")


def test_la_limite_de_photos_permet_300_bouteilles():
    from src.services import envoi

    assert envoi.NOMBRE_MAX >= 600


def test_trop_de_photos_refusees(api, tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.envoi.NOMBRE_MAX", 4)
    dossier = generer_photos_fictives(tmp_path / "p", 3)  # 6 photos > 4
    verifier_erreur(envoyer(api, dossier), 422, "envoi_refuse", "au maximum")


def test_une_photo_trop_lourde_est_refusee(api, dossier_photos, monkeypatch):
    monkeypatch.setattr("src.services.envoi.TAILLE_MAX_OCTETS", 100)
    verifier_erreur(envoyer(api, dossier_photos), 422, "envoi_refuse", "trop lourde")


def test_maison_inconnue_refusee(api, dossier_photos):
    verifier_erreur(envoyer(api, dossier_photos, maison="Maison Fantôme"), 422, "envoi_refuse", "Aucune config")


@pytest.fixture
def extrait(api, dossier_photos):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    return inventaire_id


def test_valeur_hors_liste_refusee(api, extrait):
    bouteille = api.get(f"/inventaires/{extrait}/bouteilles").json()["bouteilles"][0]["id"]
    reponse = api.post(
        f"/inventaires/{extrait}/bouteilles/{bouteille}/corrections",
        json={"champ": "couleur", "valeur": "violet"},
        headers=AUTEUR,
    )
    verifier_erreur(reponse, 422, "saisie_refusee", "n'est pas une valeur de la liste « couleur »")


def test_l_auteur_est_exige_pour_corriger(api, extrait):
    bouteille = api.get(f"/inventaires/{extrait}/bouteilles").json()["bouteilles"][0]["id"]
    reponse = api.post(f"/inventaires/{extrait}/bouteilles/{bouteille}/corrections", json={"champ": "millesime", "valeur": "1999"})
    verifier_erreur(reponse, 422, "requete_invalide", "x-auteur")


def test_quantite(api, extrait):
    bouteille = api.get(f"/inventaires/{extrait}/bouteilles").json()["bouteilles"][1]["id"]
    reponse = api.put(f"/inventaires/{extrait}/bouteilles/{bouteille}/quantite", json={"quantite": 3}, headers=AUTEUR)
    assert reponse.status_code == 200 and reponse.json()["quantite"] == 3
    assert reponse.json()["valeurs_courantes"]["quantite"] == 3
    verifier_erreur(
        api.put(f"/inventaires/{extrait}/bouteilles/{bouteille}/quantite", json={"quantite": 0}, headers=AUTEUR),
        422, "requete_invalide", "quantite",
    )


def test_inventaire_avec_une_bouteille_en_erreur_ne_se_valide_pas(api, dossier_photos):
    from src.extract.base import SortieModele

    class UneEnErreur(FixtureExtractor):
        def extraire_brut(self, photos):
            sortie = super().extraire_brut(photos)
            if self._index == 2:
                return SortieModele(brut=None, modele="m", version_prompt="v", erreur="ServerError : 503")
            return sortie

    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, UneEnErreur(charges(), charger_config(CONFIG_TEST)))
    verifier_erreur(api.post(f"/inventaires/{inventaire_id}/valider", headers=AUTEUR), 409, "validation_refusee", "en erreur (n°2)")
    relance = api.post(f"/inventaires/{inventaire_id}/relancer-erreurs").json()
    assert relance["nombre"] == 1 and relance["progression"]["par_statut"]["a_extraire"] == 1


# --- consultation ---------------------------------------------------------------------------


def test_liste_paginee_et_filtree(api, extrait):
    page = api.get(f"/inventaires/{extrait}/bouteilles", params={"page": 2, "par_page": 4}).json()
    assert page["total"] == 6 and [b["position"] for b in page["bouteilles"]] == [5, 6]
    assert api.get(f"/inventaires/{extrait}/bouteilles", params={"statut": "validee"}).json()["total"] == 0
    a_verifier = api.get(f"/inventaires/{extrait}/bouteilles", params={"a_verifier": True}).json()
    sans_doute = api.get(f"/inventaires/{extrait}/bouteilles", params={"a_verifier": False}).json()
    assert a_verifier["total"] + sans_doute["total"] == 6 and a_verifier["total"] > 0
    assert all(b["a_verifier"] for b in a_verifier["bouteilles"])
    verifier_erreur(api.get(f"/inventaires/{extrait}/bouteilles", params={"statut": "n_importe"}), 422, "requete_invalide", "statut")


def test_fiche_d_une_bouteille_voisines_et_photos(api, extrait):
    ids = [b["id"] for b in api.get(f"/inventaires/{extrait}/bouteilles").json()["bouteilles"]]
    fiche = api.get(f"/inventaires/{extrait}/bouteilles/{ids[1]}").json()
    assert (fiche["precedente_id"], fiche["suivante_id"]) == (ids[0], ids[2])
    assert api.get(f"/inventaires/{extrait}/bouteilles/{ids[0]}").json()["precedente_id"] is None
    assert fiche["position"] == 2 and fiche["historique"] == []
    assert "estimation" not in fiche["valeurs_modele"]  # le modèle ne la remplit jamais
    assert [photo["numero"] for photo in fiche["photos"]] == [1, 2]  # toutes ses photos, dans l'ordre
    for lien in (fiche["photos"][0]["reduite"], fiche["photos"][1]["originale"]):
        reponse = api.get(lien)
        assert reponse.status_code == 200 and reponse.headers["content-type"] == "image/jpeg"


def test_inventaire_ou_bouteille_introuvable(api, extrait):
    verifier_erreur(api.get("/inventaires/999"), 404, "introuvable", "Aucun inventaire n°999")
    verifier_erreur(api.get(f"/inventaires/{extrait}/bouteilles/999"), 404, "introuvable", "Aucune bouteille n°999")


# --- photos : étanchéité entre inventaires, aucune métadonnée -----------------------------------


def test_une_photo_demandee_via_un_autre_inventaire_est_refusee(api, dossier_photos, tmp_path):
    premier = envoyer(api, dossier_photos).json()["id"]
    second = envoyer(api, generer_photos_fictives(tmp_path / "autres", 1), nom="Autre").json()["id"]
    photo = api.get(f"/inventaires/{premier}/bouteilles").json()["bouteilles"][0]["id"]
    photo_id = api.get(f"/inventaires/{premier}/bouteilles/{photo}").json()["photos"][0]["reduite"].rsplit("/", 1)[1]

    assert api.get(f"/inventaires/{premier}/photos/{photo_id}").status_code == 200
    verifier_erreur(api.get(f"/inventaires/{second}/photos/{photo_id}"), 404, "introuvable", f"Aucune photo n°{photo_id}")


def photo_avec_gps(chemin: Path, couleur, orientation=6) -> None:
    image = Image.new("RGB", (40, 20), couleur)
    exif = Image.Exif()
    exif[0x0132] = "2026:01:01 10:00:00"
    exif[0x0112] = orientation  # rotation de 90° à appliquer pour l'affichage
    exif[0x8825] = {1: "N", 2: (48.0, 51.0, 24.0), 3: "E", 4: (2.0, 21.0, 8.0)}  # GPS : la cave
    image.save(chemin, "JPEG", exif=exif.tobytes())


def tout_le_json(api, inventaire_id) -> str:
    morceaux = [api.get("/inventaires").text, api.get(f"/inventaires/{inventaire_id}").text]
    for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]:
        morceaux.append(api.get(f"/inventaires/{inventaire_id}/bouteilles/{b['id']}").text)
    return "\n".join(morceaux)


def test_aucune_reponse_ne_contient_de_metadonnees_exif(api, tmp_path):
    dossier = tmp_path / "gps"
    dossier.mkdir()
    photo_avec_gps(dossier / "a_etiquette.jpg", (200, 30, 30))
    photo_avec_gps(dossier / "b_contre.jpg", (30, 200, 30))
    assert Image.open(dossier / "a_etiquette.jpg").getexif().get_ifd(0x8825)  # l'original a bien du GPS
    inventaire_id = envoyer(api, dossier).json()["id"]
    fiche = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"][0]["id"]
    liens = api.get(f"/inventaires/{inventaire_id}/bouteilles/{fiche}").json()["photos"]

    for lien in [lien for photo in liens for lien in (photo["reduite"], photo["originale"])]:
        octets = api.get(lien).content
        servie = Image.open(io.BytesIO(octets))
        assert dict(servie.getexif()) == {} and b"Exif" not in octets
        assert servie.size == (20, 40)  # rotation EXIF appliquée pour l'affichage
    texte = tout_le_json(api, inventaire_id).lower()
    for indice in ("exif", "gps", "48.0", "stockage"):
        assert indice not in texte
    # L'original stocké, lui, n'a pas été touché.
    stockees = list(api.stockage.iterdir())
    assert any(Image.open(p).getexif().get_ifd(0x8825) for p in stockees)


# --- documentation -----------------------------------------------------------------------------

ROUTES_DOCUMENTEES = {
    "/maisons": {"get"},
    "/inventaires": {"get", "post"},
    "/inventaires/{inventaire_id}": {"get"},
    "/inventaires/{inventaire_id}/lancer": {"post"},
    "/inventaires/{inventaire_id}/annuler": {"post"},
    "/inventaires/{inventaire_id}/relancer-erreurs": {"post"},
    "/inventaires/{inventaire_id}/valider": {"post"},
    "/inventaires/{inventaire_id}/export": {"get"},
    "/inventaires/{inventaire_id}/bouteilles": {"get"},
    "/inventaires/{inventaire_id}/bouteilles/{bouteille_id}": {"get"},
    "/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/corrections": {"post"},
    "/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/quantite": {"put"},
    "/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/valider": {"post"},
    "/inventaires/{inventaire_id}/photos/{photo_id}": {"get", "delete"},
    # Session 4 — dépôt des photos (ajouts approuvés le 2026-10-10).
    "/brouillons": {"post"},
    "/inventaires/{inventaire_id}/photos": {"post"},
    "/inventaires/{inventaire_id}/photos/deja-recues": {"post"},
    "/inventaires/{inventaire_id}/apercu": {"get"},
    "/inventaires/{inventaire_id}/finaliser": {"post"},
    # Session 6 — une bouteille = un groupe de photos (plan validé le 2026-10-11) ;
    # « déplacer », « inverser une paire », « retrier » et « inverser les photos » disparaissent.
    "/inventaires/{inventaire_id}/photos/{photo_id}/couper": {"post"},
    "/inventaires/{inventaire_id}/groupes/{groupe_id}/rattacher": {"post"},
    "/inventaires/{inventaire_id}/groupes/{groupe_id}/quantite": {"put"},
    "/inventaires/{inventaire_id}/groupes/{groupe_id}": {"delete"},
    "/inventaires/{inventaire_id}/bouteilles-en-cours/{cle}/quantite": {"put"},
    # Session 5 — relecture (ajouts approuvés avec le plan, le 2026-10-10).
    "/inventaires/{inventaire_id}/recapitulatif": {"get"},
    "/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/revenir": {"post"},
    "/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/reanalyser": {"post"},
    "/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/signalement": {"post", "delete"},
    "/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/separer": {"post"},
}


def test_la_documentation_interactive_est_generee_et_a_jour(api):
    assert api.get("/docs").status_code == 200
    chemins = api.get("/openapi.json").json()["paths"]
    assert {chemin: set(operations) for chemin, operations in chemins.items()} == ROUTES_DOCUMENTEES
    for operations in chemins.values():
        for operation in operations.values():
            assert operation.get("summary"), operation  # chaque route dit ce qu'elle fait


def test_maisons(api):
    maisons = api.get("/maisons").json()
    assert {"maison": "Maison Test", "fichier": "maison_test.json"}.items() <= next(
        m for m in maisons if m["fichier"] == "maison_test.json"
    ).items()
