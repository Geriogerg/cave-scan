"""Le cycle de vie par les écrans et par l'API (decisions.md 0168) : renommer,
archiver, corbeille (confirmée), clore (confirmé, avertit de ce qui n'est pas
validé), rouvrir, pause ; retirer une bouteille en relecture, la remettre depuis
le récapitulatif. Les garde-fous restent côté serveur."""

from __future__ import annotations

import re

import pytest

from src.config.maison import charger_config
from src.extract.fixture_extract import FixtureExtractor
from tests.conftest import CONFIG_TEST
from tests.test_api import api, charges, envoyer, extraire_en_arriere_plan, verifier_erreur  # noqa: F401

AUTEUR = {"X-Auteur": "Expert test"}


@pytest.fixture
def extrait(api, dossier_photos):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    return inventaire_id


def ids(api, inventaire_id):
    return [b["id"] for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]]


def test_le_suivi_propose_de_gerer_l_inventaire(api, extrait):
    page = api.get(f"/app/inventaires/{extrait}/suivi").text
    for texte in ("Gérer l'inventaire", "Renommer", "Archiver", "Clore l'inventaire", "Mettre à la corbeille",
                  "Ajouter des bouteilles"):
        assert texte in page, texte


def test_renommer_et_archiver_depuis_le_suivi(api, extrait):
    renomme = api.post(f"/app/inventaires/{extrait}/renommer", data={"nom": "Vente de Noël"}, follow_redirects=False)
    assert renomme.status_code == 303 and renomme.headers["location"].endswith("?fait=renomme")
    assert "Inventaire renommé." in api.get(renomme.headers["location"]).text
    api.post(f"/app/inventaires/{extrait}/archiver")
    accueil = api.get("/app").text
    assert "Archives (1)" in accueil and "Vente de Noël" in accueil
    # Un nom vide : on reste sur l'inventaire, le refus en clair, rien de renommé (T4-B20).
    refus = api.post(f"/app/inventaires/{extrait}/renommer", data={"nom": "  "}, follow_redirects=False)
    assert refus.status_code == 303 and refus.headers["location"].endswith("?fait=nom_vide")
    suivi = api.get(refus.headers["location"]).text
    assert "Donnez un nom" in suivi and "message attention" in suivi and "Vente de Noël" in suivi


def test_la_corbeille_demande_confirmation_et_se_restaure(api, extrait):
    confirmation = api.get(f"/app/inventaires/{extrait}/supprimer").text
    assert "n&#39;est effacé" in confirmation and "Mettre à la corbeille" in confirmation
    assert "Son analyse s" not in confirmation  # elle est finie (T4-D14)
    supprime = api.post(f"/app/inventaires/{extrait}/supprimer", follow_redirects=False)
    assert supprime.headers["location"] == "/app?fait=corbeille"
    accueil = api.get("/app").text
    assert "Corbeille (1)" in accueil and "Restaurer" in accueil
    assert api.get(f"/app/inventaires/{extrait}/suivi").status_code == 404  # plus aucun écran ne l'ouvre
    assert api.get("/inventaires").json() == [] and api.get("/inventaires", params={"corbeille": True}).json()[0]["dans_la_corbeille"]
    api.post(f"/app/inventaires/{extrait}/restaurer")
    assert api.get(f"/app/inventaires/{extrait}/suivi").status_code == 200


def test_clore_avertit_de_ce_qui_n_est_pas_valide_puis_lecture_seule(api, extrait):
    confirmation = api.get(f"/app/inventaires/{extrait}/clore").text
    assert "6 bouteilles non validées" in confirmation and "Clore l&#39;inventaire quand même" in confirmation
    api.post(f"/app/inventaires/{extrait}/clore")
    suivi = api.get(f"/app/inventaires/{extrait}/suivi").text
    assert "lecture seule" in suivi and "Rouvrir" in suivi and "Ajouter des bouteilles" not in suivi

    premiere = ids(api, extrait)[0]
    page = api.get(f"/app/inventaires/{extrait}/relecture/{premiere}").text
    assert "Inventaire clos : lecture seule." in page and '<fieldset class="champs" disabled>' in page
    refus = api.post(f"/app/inventaires/{extrait}/relecture/{premiere}/champ/millesime",
                     data={"millesime": "2001"}, headers={"HX-Request": "true"})
    assert refus.status_code == 422 and "lecture seule" in refus.text
    assert api.get(f"/inventaires/{extrait}/export").status_code == 200  # l'export reste possible
    assert api.get(f"/app/inventaires/{extrait}/depot", follow_redirects=False).status_code == 303

    rouvert = api.post(f"/app/inventaires/{extrait}/rouvrir", follow_redirects=False)
    assert rouvert.headers["location"].endswith("?fait=rouvert")


def test_clore_un_inventaire_en_cours_d_analyse_est_refuse(api, dossier_photos):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    refus = api.get(f"/app/inventaires/{inventaire_id}/clore")
    assert refus.status_code == 409 and "encore en cours" in refus.text
    verifier_erreur(api.post(f"/inventaires/{inventaire_id}/clore", headers=AUTEUR), 409, "action_refusee", "en cours d'analyse")


def test_pause_et_reprise_de_l_analyse(api, dossier_photos):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    api.post(f"/inventaires/{inventaire_id}/lancer")
    assert "Mettre l'analyse en pause" in api.get(f"/app/inventaires/{inventaire_id}/progression").text
    api.post(f"/app/inventaires/{inventaire_id}/pause")
    progression = api.get(f"/app/inventaires/{inventaire_id}/progression").text
    assert "Analyse en pause" in progression and "Reprendre l'analyse" in progression
    api.post(f"/app/inventaires/{inventaire_id}/reprendre-analyse")
    assert api.get(f"/inventaires/{inventaire_id}").json()["extraction"] == "lancee"


def test_retirer_une_bouteille_en_relecture_puis_la_remettre(api, extrait):
    premiere, seconde = ids(api, extrait)[:2]
    page = api.get(f"/app/inventaires/{extrait}/relecture/{premiere}").text
    assert "Retirer cette bouteille" in page and "data-confirmer=" in page
    retiree = api.post(f"/app/inventaires/{extrait}/relecture/{premiere}/retirer", data={"motif": "pas dans la vente"},
                       follow_redirects=False)
    assert retiree.status_code == 303 and f"/relecture/{seconde}?fait=retiree" in retiree.headers["location"]
    assert premiere not in ids(api, extrait)
    # La page d'une bouteille retirée renvoie au récapitulatif, qui la liste.
    assert api.get(f"/app/inventaires/{extrait}/relecture/{premiere}", follow_redirects=False).headers["location"].endswith("/recapitulatif")
    recap = api.get(f"/app/inventaires/{extrait}/recapitulatif").text
    assert "Bouteilles retirées" in recap and "Remettre dans l'inventaire" in recap
    api.post(f"/app/inventaires/{extrait}/bouteilles/{premiere}/remettre")
    assert premiere in ids(api, extrait)


def test_le_cycle_de_vie_par_l_api(api, extrait):
    premiere = ids(api, extrait)[0]
    assert api.patch(f"/inventaires/{extrait}", json={"nom": "Vente API"}, headers=AUTEUR).json()["nom"] == "Vente API"
    assert api.post(f"/inventaires/{extrait}/archiver", headers=AUTEUR).json()["archive"] is True
    assert api.post(f"/inventaires/{extrait}/desarchiver", headers=AUTEUR).json()["archive"] is False
    retiree = api.post(f"/inventaires/{extrait}/bouteilles/{premiere}/retirer", json={"motif": "doublon"}, headers=AUTEUR)
    assert retiree.json()["retiree"] is True and retiree.json()["evenements"][-1]["type"] == "retrait"
    assert api.post(f"/inventaires/{extrait}/bouteilles/{premiere}/remettre", headers=AUTEUR).json()["retiree"] is False
    assert api.post(f"/inventaires/{extrait}/clore", headers=AUTEUR).json()["clos"] is True
    verifier_erreur(
        api.post(f"/inventaires/{extrait}/bouteilles/{premiere}/corrections", json={"champ": "millesime", "valeur": "2001"}, headers=AUTEUR),
        409, "inventaire_clos", "lecture seule",
    )
    assert api.post(f"/inventaires/{extrait}/rouvrir", headers=AUTEUR).json()["clos"] is False
    assert api.delete(f"/inventaires/{extrait}", headers=AUTEUR).json()["dans_la_corbeille"] is True
    verifier_erreur(api.get(f"/inventaires/{extrait}"), 404, "introuvable", "dans la corbeille")
    assert api.post(f"/inventaires/{extrait}/restaurer", headers=AUTEUR).json()["dans_la_corbeille"] is False
    verifier_erreur(api.post(f"/inventaires/{extrait}/archiver"), 422, "requete_invalide", "x-auteur")


def test_les_pages_de_confirmation_tiennent_sur_un_telephone(api, extrait):
    for geste in ("supprimer", "clore", "rouvrir"):
        texte = api.get(f"/app/inventaires/{extrait}/{geste}").text
        assert 'class="barre-actions"' in texte and re.search(r'<form method="post" action="[^"]+/' + geste + '"', texte)


def test_clos_l_excel_est_l_action_principale_et_aucune_correction_se_dit(api, extrait):
    """T5-DS2 : inventaire clos, « Télécharger l'Excel » est le bouton principal du
    suivi ; T4-D14 : sans correction, le récapitulatif dit « aucune », pas « 0 sur 0 »."""
    assert "<dd>aucune</dd>" in api.get(f"/app/inventaires/{extrait}/recapitulatif").text
    assert api.post(f"/inventaires/{extrait}/clore", headers=AUTEUR).json()["clos"] is True
    suivi = api.get(f"/app/inventaires/{extrait}/suivi").text
    assert 'class="bouton principal" href="/app/inventaires/' + str(extrait) + '/excel"' in suivi
    assert 'class="bouton principal" href="/app/inventaires/' + str(extrait) + '/relecture"' not in suivi


def test_la_cloture_nomme_les_bouteilles_non_validees(api, extrait):
    """T6-B10 : avant de clore, les numéros des bouteilles non validées."""
    confirmation = api.get(f"/app/inventaires/{extrait}/clore").text
    assert "(n°1, n°2" in confirmation and confirmation.count("n°1,") == 1  # une seule fois (T9-D1)


def test_renommer_vide_garde_le_volet_ouvert(api, extrait):
    """T8-D5 : le refus d'un nom vide garde « Gérer l'inventaire » ouvert, le curseur dans le champ."""
    retour = api.post(f"/app/inventaires/{extrait}/renommer", data={"nom": "  "}, follow_redirects=True).text
    assert '<details class="gestion" open>' in retour and "autofocus" in retour.split('id="nouveau-nom"')[1].split(">")[0]


def test_renommer_trop_long_revient_au_suivi(api, extrait):
    """T8-B3 : plus de 200 caractères (champ contourné) : le suivi le dit, rien de renommé."""
    retour = api.post(f"/app/inventaires/{extrait}/renommer", data={"nom": "x" * 300}, follow_redirects=False)
    assert retour.headers["location"].endswith("fait=nom_long")

