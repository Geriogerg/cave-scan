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
