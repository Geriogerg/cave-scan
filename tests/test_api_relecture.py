"""API de la relecture (session 5) : mêmes services que l'écran, même format d'erreur."""

from __future__ import annotations

import pytest

from src.config.maison import charger_config
from src.extract.fixture_extract import FixtureExtractor
from tests.conftest import CONFIG_TEST
from tests.test_api import AUTEUR, api, charges, envoyer, extraire_en_arriere_plan  # noqa: F401 — fixture partagée
from tests.test_api import verifier_erreur


@pytest.fixture
def inventaire(api, dossier_photos):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    return inventaire_id


def bouteilles(api, inventaire_id):
    return [b["id"] for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]]


def chemin(inventaire_id, bouteille_id, suite=""):
    return f"/inventaires/{inventaire_id}/bouteilles/{bouteille_id}{suite}"


def test_la_fiche_porte_sa_version_et_l_api_previent_d_une_modification_faite_ailleurs(api, inventaire):
    premiere = bouteilles(api, inventaire)[0]
    fiche = api.get(chemin(inventaire, premiere)).json()
    assert fiche["version"] and fiche["paire_signalee"] is False and fiche["evenements"] == []
    corrigee = api.post(chemin(inventaire, premiere, "/corrections"),
                        json={"champ": "millesime", "valeur": "2001", "version": fiche["version"]}, headers=AUTEUR)
    assert corrigee.status_code == 200 and corrigee.json()["version"] != fiche["version"]
    perimee = api.post(chemin(inventaire, premiere, "/corrections"),
                       json={"champ": "millesime", "valeur": "1990", "version": fiche["version"]}, headers=AUTEUR)
    verifier_erreur(perimee, 409, "modification_concurrente", "modifiée ailleurs")
    assert any("2001" in changement for changement in perimee.json()["detail"])
    # Sans version (comme avant la session 5) : aucune vérification.
    assert api.post(chemin(inventaire, premiere, "/corrections"), json={"champ": "cuvee", "valeur": "X"},
                    headers=AUTEUR).status_code == 200


def test_revenir_a_la_valeur_du_modele(api, inventaire):
    premiere = bouteilles(api, inventaire)[0]
    api.post(chemin(inventaire, premiere, "/corrections"), json={"champ": "millesime", "valeur": "1999"}, headers=AUTEUR)
    retour = api.post(chemin(inventaire, premiere, "/revenir"), json={"champ": "millesime"}, headers=AUTEUR)
    assert retour.status_code == 200 and retour.json()["valeurs_courantes"]["millesime"] == "2018"
    assert [h["nouvelle_valeur"] for h in retour.json()["historique"]] == ["1999", "2018"]
    verifier_erreur(api.post(chemin(inventaire, premiere, "/revenir"), json={"champ": "millesime"}, headers=AUTEUR),
                    422, "saisie_refusee", "déjà la valeur lue")


def test_valider_avec_le_temps_de_relecture(api, inventaire):
    premiere = bouteilles(api, inventaire)[0]
    valide = api.post(chemin(inventaire, premiere, "/valider"), json={"temps_ms": 4200}, headers=AUTEUR)
    assert valide.status_code == 200 and valide.json()["statut"] == "validee" and valide.json()["temps_relecture_ms"] == 4200
    stats = api.get(f"/inventaires/{inventaire}").json()["statistiques"]
    assert stats["temps_relecture_total_ms"] == 4200 and stats["temps_relecture_moyen_ms"] == 4200
    # Sans corps, comme avant la session 5.
    assert api.post(chemin(inventaire, bouteilles(api, inventaire)[1], "/valider"), headers=AUTEUR).status_code == 200


def test_signalement_reanalyse_separation(api, inventaire):
    premiere, seconde = bouteilles(api, inventaire)[:2]

    signalee = api.post(chemin(inventaire, premiere, "/signalement"), json={"motif": "décalage"}, headers=AUTEUR)
    assert signalee.status_code == 200 and signalee.json()["paire_signalee"] is True
    assert signalee.json()["evenements"][0]["detail"] == {"motif": "décalage"}
    verifier_erreur(api.post(chemin(inventaire, premiere, "/valider"), headers=AUTEUR), 409, "validation_refusee", "problème de photos")
    levee = api.delete(chemin(inventaire, premiere, "/signalement"), headers=AUTEUR)
    assert levee.status_code == 200 and levee.json()["paire_signalee"] is False

    avant = api.get(chemin(inventaire, premiere)).json()["photos"]
    assert api.post(chemin(inventaire, premiere, "/inverser-photos"), headers=AUTEUR).status_code in (404, 405)

    reanalyse = api.post(chemin(inventaire, seconde, "/reanalyser"), headers=AUTEUR)
    assert reanalyse.status_code == 200 and reanalyse.json()["statut"] == "a_extraire"

    api.put(chemin(inventaire, premiere, "/quantite"), json={"quantite": 6}, headers=AUTEUR)
    nouvelle = api.post(chemin(inventaire, premiere, "/separer"), json={"quantite": 2}, headers=AUTEUR)
    assert nouvelle.status_code == 201
    assert nouvelle.json()["quantite"] == 2 and nouvelle.json()["separee_de_id"] == premiere
    assert nouvelle.json()["photos"] == avant  # mêmes photos
    verifier_erreur(api.post(chemin(inventaire, premiere, "/separer"), json={"quantite": 4}, headers=AUTEUR),
                    409, "action_refusee", "on peut en séparer 3 au plus")

    stats = api.get(f"/inventaires/{inventaire}").json()["statistiques"]
    assert (stats["nb_signalees"], stats["nb_reanalysees"], stats["nb_separees"]) == (1, 1, 1)


def test_recapitulatif(api, inventaire):
    ids = bouteilles(api, inventaire)
    api.post(chemin(inventaire, ids[0], "/signalement"), headers=AUTEUR)
    api.post(chemin(inventaire, ids[1], "/valider"), headers=AUTEUR)
    recap = api.get(f"/inventaires/{inventaire}/recapitulatif").json()
    assert (recap["total"], recap["validees"], recap["termine"]) == (6, 1, False)
    assert [b["position"] for b in recap["signalees"]] == [1]
    assert [b["position"] for b in recap["restantes"]] == [3, 4, 5, 6]
    assert "temps_relecture_total_ms" in recap["statistiques"]


def test_valider_l_inventaire_ne_valide_rien(api, inventaire):
    refus = api.post(f"/inventaires/{inventaire}/valider", headers=AUTEUR)
    verifier_erreur(refus, 409, "validation_refusee", "6 bouteille(s) à relire")
    assert api.get(f"/inventaires/{inventaire}").json()["progression"]["par_statut"]["validee"] == 0
