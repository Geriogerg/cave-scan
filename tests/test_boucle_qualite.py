"""Points relevés par l'agent testeur-web (boucle qualité, docs/tests/journal.md),
vérifiés ici pour qu'ils ne reviennent pas."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from src.config.maison import charger_config
from src.donnees.modeles import Extraction
from src.extract.fixture_extract import FixtureExtractor
from src.services.extraction import extraire_inventaire
from src.services.inventaires import charger_inventaire, creer_inventaire
from src.services.pilotage import avancement
from tests.conftest import CONFIG_TEST
from tests.test_api import api, charges, envoyer, extraire_en_arriere_plan  # noqa: F401
from tests.test_extraction import ExtracteurScenario

AUTEUR = {"X-Auteur": "Expert test"}


def test_la_duree_d_une_analyse_terminee_ne_grandit_plus(session, nom_maison, dossier_photos, stockage):
    """T1-m1 : « Analyse terminée en X s » s'arrête à la dernière lecture."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario(), stockage)
    inventaire = charger_inventaire(session, cree.inventaire_id)
    premiere = session.scalar(select(func.min(Extraction.cree_le)))
    derniere = session.scalar(select(func.max(Extraction.cree_le)))
    inventaire.extraction_lancee_le = premiere - timedelta(seconds=5)
    session.commit()
    etat = avancement(session, cree.inventaire_id)
    assert etat.terminee
    assert etat.ecoule_s == (derniere - inventaire.extraction_lancee_le).total_seconds()
    assert avancement(session, cree.inventaire_id).ecoule_s == etat.ecoule_s


def test_inventaire_clos_la_relecture_propose_la_suivante_au_lieu_de_valider(api, dossier_photos):
    """T1-m9 : en lecture seule, le bouton passe à la suivante, sans requête refusée."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    ids = [b["id"] for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]]
    api.post(f"/app/inventaires/{inventaire_id}/clore")
    page = api.get(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}").text
    assert "data-lecture-seule" in page and "Bouteille suivante" in page
    assert 'type="submit" class="bouton principal" id="valider"' not in page


def test_remettre_une_bouteille_le_dit(api, dossier_photos):
    """T1-m11 : la remise dans l'inventaire affiche ce qui s'est passé."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    premiere = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"][0]["id"]
    api.post(f"/app/inventaires/{inventaire_id}/relecture/{premiere}/retirer", headers=AUTEUR)
    page = api.post(f"/app/inventaires/{inventaire_id}/bouteilles/{premiere}/remettre", headers=AUTEUR).text
    assert "Bouteille remise dans l&#39;inventaire" in page


def test_une_adresse_mal_formee_ou_inconnue_donne_une_page_en_francais(api):
    """T1-m12 : ni « inventaire_id », ni JSON brut dans le navigateur."""
    mal_formee = api.get("/app/inventaires/abc/suivi")
    assert mal_formee.status_code == 404 and "Cette adresse n&#39;existe pas" in mal_formee.text
    assert "inventaire_id" not in mal_formee.text
    inconnue = api.get("/nimportequoi", headers={"Accept": "text/html"})
    assert inconnue.status_code == 404 and inconnue.text.lstrip().startswith("<!doctype html>")
    assert api.get("/nimportequoi").json()["code"] == "introuvable"  # l'API garde son JSON


def test_une_quantite_demesuree_est_refusee_en_clair_partout(api, dossier_photos):
    """T2-B1 : 99999999999999999999 faisait une erreur 500 (SQLite)."""
    from src.services.relecture import CorrectionRefusee, quantite_valide

    enorme = "99999999999999999999"
    try:
        quantite_valide(enorme)
    except CorrectionRefusee as refus:
        assert "Quantité trop grande" in str(refus)
    else:
        raise AssertionError("quantité démesurée acceptée")

    from src.services.depot import _quantite
    from src.services.envoi import EnvoiRefuse

    try:
        _quantite(int(enorme))
    except EnvoiRefuse as refus:
        assert "Quantité trop grande" in str(refus)
    else:
        raise AssertionError("quantité démesurée acceptée au dépôt")

    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    premiere = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"][0]["id"]
    reponse = api.post(f"/app/inventaires/{inventaire_id}/relecture/{premiere}/champ/quantite",
                       data={"quantite": enorme}, headers={"HX-Request": "true", **AUTEUR})
    assert reponse.status_code == 422 and "Quantité trop grande" in reponse.text


def test_un_texte_trop_long_est_refuse(session, nom_maison, dossier_photos, stockage):
    """T2-B5 : un collage accidentel de 5 000 caractères."""
    import pytest

    from src.services.relecture import CorrectionRefusee, corriger

    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario(), stockage)
    premiere = charger_inventaire(session, cree.inventaire_id).bouteilles[0]
    with pytest.raises(CorrectionRefusee, match="1000 au plus"):
        corriger(session, premiere.id, "cuvee", "x" * 5000, "expert")


def test_les_consignes_d_origine_legerement_modifiees_ne_declenchent_pas_l_alerte_few_shot(tmp_path):
    """T3-R8 : les citations du texte d'origine (« observee »…) ne sont pas un exemple ;
    une citation AJOUTÉE par la maison, si."""
    import json

    from src.config.maison import charger_config
    from src.extract.consignes import CONSIGNES_MODIFIABLES

    def avertissements(consignes):
        brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
        brut["consignes"] = consignes
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
        return [a for a in charger_config(chemin).avertissements if a.startswith("Consignes générales")]

    ajout_sans_exemple = "\nPrécise toujours le climat s'il est écrit."
    ajout_avec_exemple = "\nPar exemple, réponds « Château Margaux 1990 »."
    assert avertissements(CONSIGNES_MODIFIABLES + ajout_sans_exemple) == []
    assert avertissements(CONSIGNES_MODIFIABLES + ajout_avec_exemple) != []


def test_le_score_signale_des_consignes_modifiees(tmp_path, capsys):
    """R5 : avec des consignes modifiées, le rapport de score le dit ; avec celles
    d'origine, rien."""
    import json

    import run_v0
    from src.compare.compare_listings import AVERTISSEMENT_CONSIGNES

    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["consignes"] = "Lis les étiquettes avec soin ; précise toujours le climat s'il est écrit."
    modifiee = tmp_path / "modifiee.json"
    modifiee.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")

    assert run_v0.main(["--dry-run", "--maison", str(CONFIG_TEST), "--sortie", str(tmp_path / "a.xlsx")]) == 0
    assert AVERTISSEMENT_CONSIGNES not in capsys.readouterr().out
    assert run_v0.main(["--dry-run", "--maison", str(modifiee), "--sortie", str(tmp_path / "b.xlsx")]) == 0
    sortie = capsys.readouterr().out
    assert AVERTISSEMENT_CONSIGNES in sortie and "Comparaison auto vs manuel" in sortie


def test_l_excel_refuse_depuis_un_ecran_revient_au_suivi_avec_la_raison(api, dossier_photos):
    """T3-D4 : un Excel refusé (bouteille sans ligne) ne laisse ni téléchargement
    annulé en silence, ni JSON brut : retour au suivi, avec la raison."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]  # pas encore analysé
    refus = api.get(f"/app/inventaires/{inventaire_id}/excel", follow_redirects=False)
    assert refus.status_code == 303 and refus.headers["location"].endswith("/suivi?fait=excel_refuse")
    assert "pas encore disponible" in api.get(refus.headers["location"]).text
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    fichier = api.get(f"/app/inventaires/{inventaire_id}/excel")
    assert fichier.status_code == 200 and "attachment" in fichier.headers["content-disposition"]


def test_suggestions_du_tour_3(api, dossier_photos):
    """T3-DS2 : l'Excel porte le nom de la vente ; T3-DS3 : bouteille signalée, Valider
    désactivé avec la raison ; T3-DS6 : relecture finie, « Clore » sur place."""
    inventaire_id = envoyer(api, dossier_photos, nom="Cave Dupont").json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    entete = api.get(f"/app/inventaires/{inventaire_id}/excel").headers["content-disposition"]
    assert "filename*=UTF-8''Cave%20Dupont" in entete and "%E2%80%94" in entete and entete.endswith(".xlsx")

    ids = [b["id"] for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]]
    api.post(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}/signaler", headers=AUTEUR)
    page = api.get(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}").text
    assert 'id="valider" disabled' in page and "problème de photos signalé" in page

    api.post(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}/lever-signalement", headers=AUTEUR)
    for bouteille_id in ids:
        api.post(f"/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/valider", json={}, headers=AUTEUR)
    recap = api.get(f"/app/inventaires/{inventaire_id}/recapitulatif").text
    assert f'href="/app/inventaires/{inventaire_id}/clore"' in recap


def test_restaurer_un_inventaire_analyse_laisse_reanalyser(session, nom_maison, dossier_photos, stockage):
    """T4-D1 : corbeille puis restauration d'un inventaire fini : « Réanalyser »
    marche (plus d'impasse « analyse annulée »)."""
    from src.services.cas_particuliers import reanalyser
    from src.services.cycle_de_vie import restaurer, supprimer
    from src.services.pilotage import lancer

    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    lancer(session, cree.inventaire_id)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario(), stockage)
    supprimer(session, cree.inventaire_id, "Expert test")
    restaurer(session, cree.inventaire_id, "Expert test")
    inventaire = charger_inventaire(session, cree.inventaire_id)
    assert inventaire.extraction == "lancee"
    assert reanalyser(session, inventaire.bouteilles[0].id, "Expert test") is True


def test_une_citation_dans_les_consignes_n_est_pas_un_exemple(tmp_path):
    """T3-D2 : « Grand Cru » à recopier tel quel est une précision, pas un exemple."""
    import json

    from src.config.maison import charger_config
    from src.extract.consignes import CONSIGNES_MODIFIABLES

    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["consignes"] = CONSIGNES_MODIFIABLES + "\nPRÉCISION : la mention « Grand Cru » se recopie telle quelle."
    chemin = tmp_path / "c.json"
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    alertes = [a for a in charger_config(chemin).avertissements if a.startswith("Consignes")]
    assert alertes == [] and not any("few-shot" in a for a in charger_config(chemin).avertissements)
