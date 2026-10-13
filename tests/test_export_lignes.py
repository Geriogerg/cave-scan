"""L'Excel : une ligne par bouteille, toujours (decisions.md 0170).

- Refusé tant qu'une bouteille n'est pas encore analysée ou qu'une bouteille
  ajoutée n'est pas lancée : aucune ne manque en silence.
- Une bouteille en erreur d'analyse a sa ligne, d'une couleur à part,
  « Erreur d'analyse » dans « À vérifier », jamais fusionnée ; « Saisie
  manuelle » une fois validée à la main.
- Valider reste facultatif ; la colonne système « relue », si la maison la
  veut, dit « oui » pour les bouteilles validées.
- Le temps passé sur une bouteille ouverte compte, même sans la valider (0169).
"""

from __future__ import annotations

import io
import json

import pytest
from openpyxl import load_workbook

from src.config.maison import charger_config
from src.export.excel_writer import COULEUR_ERREUR, EtatLigne, regrouper
from src.extract.fixture_extract import FixtureExtractor
from src.extract.schema import from_tool_input
from src.services.cycle_de_vie import clore
from src.services.depot import ajouter_photo
from src.services.extraction import extraire_inventaire
from src.services.inventaires import charger_inventaire, creer_inventaire
from src.services.pilotage import avancement
from src.services.relecture import ajouter_temps_de_relecture, corriger, valider
from src.services.restitution import ExportRefuse, exporter, stats_inventaire
from tests.conftest import CONFIG_TEST, FIXTURES
from tests.test_api import api, charges, envoyer, extraire_en_arriere_plan, verifier_erreur  # noqa: F401
from tests.test_depot import jpeg
from tests.test_extraction import ExtracteurScenario
from tests.test_relecture_ecran import PROPRE

EXPERT = "Expert test"
OBLIGATOIRES = {"domaine": "Domaine X", "appellation": "Pommard", "millesime": "2001", "format": "bouteille"}


def extraire(session, nom_maison, dossier_photos, stockage, extracteur, config=CONFIG_TEST):
    cree = creer_inventaire(session, nom_maison, config, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, extracteur, stockage)
    return cree.inventaire_id


def feuille_exportee(session, inventaire_id, tmp_path):
    return load_workbook(exporter(session, inventaire_id, tmp_path / "export.xlsx")).active


def colonne(feuille, nom):
    """Les valeurs d'une colonne, ligne d'en-tête exclue."""
    index = [cellule.value for cellule in feuille[1]].index(nom)
    return [ligne[index].value for ligne in feuille.iter_rows(min_row=2)]


def couleurs(feuille):
    """La couleur de fond de chaque ligne (celle de sa première cellule)."""
    return [ligne[0].fill.fgColor.rgb if ligne[0].fill.fill_type else None for ligne in feuille.iter_rows(min_row=2)]


# --- refus : chaque bouteille doit avoir sa ligne ------------------------------------------------


def test_l_export_est_refuse_tant_qu_une_bouteille_n_est_pas_analysee(session, nom_maison, dossier_photos, stockage, tmp_path):
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    with pytest.raises(ExportRefuse, match="sa ligne.*6 bouteille.*en cours"):
        exporter(session, cree.inventaire_id, tmp_path / "e.xlsx")
    assert not (tmp_path / "e.xlsx").exists()


def test_l_export_est_refuse_tant_qu_une_bouteille_ajoutee_n_est_pas_lancee(session, nom_maison, dossier_photos, stockage, tmp_path):
    inventaire_id = extraire(session, nom_maison, dossier_photos, stockage, ExtracteurScenario())
    assert avancement(session, inventaire_id).excel_disponible
    ajouter_photo(session, inventaire_id, io.BytesIO(jpeg(42)), "ajout.jpg", stockage, bouteille="ajout", numero=7)
    assert not avancement(session, inventaire_id).excel_disponible
    with pytest.raises(ExportRefuse, match="1 bouteille.*pas encore lancée"):
        exporter(session, inventaire_id, tmp_path / "e.xlsx")


def test_une_bouteille_retiree_ne_bloque_pas_l_export(session, nom_maison, dossier_photos, stockage, tmp_path):
    from src.services.cycle_de_vie import retirer_bouteille

    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    inventaire = charger_inventaire(session, cree.inventaire_id)
    retirer_bouteille(session, inventaire.bouteilles[5].id, EXPERT)  # jamais analysée, retirée
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario(), stockage)
    assert len(colonne(feuille_exportee(session, cree.inventaire_id, tmp_path), "N°")) == 5


# --- erreur d'analyse : la ligne existe et le dit --------------------------------------------------


def test_une_bouteille_en_erreur_a_sa_ligne_signalee_et_jamais_fusionnee(session, nom_maison, dossier_photos, stockage, tmp_path):
    """Deux bouteilles en erreur ont les mêmes valeurs (aucune) : chacune garde sa ligne."""
    inventaire_id = extraire(
        session, nom_maison, dossier_photos, stockage, ExtracteurScenario({3: "passagere", 4: "passagere"})
    )
    feuille = feuille_exportee(session, inventaire_id, tmp_path)

    a_verifier = colonne(feuille, "À vérifier")
    assert len(a_verifier) == 6  # une ligne par bouteille
    assert a_verifier[2] == a_verifier[3] == "Erreur d'analyse"
    assert "Erreur d'analyse" not in a_verifier[:2] + a_verifier[4:]
    teintes = couleurs(feuille)
    assert teintes[2].endswith(COULEUR_ERREUR) and teintes[3].endswith(COULEUR_ERREUR)
    assert not any(t and t.endswith(COULEUR_ERREUR) for t in teintes[:2] + teintes[4:])


def test_une_bouteille_validee_en_saisie_manuelle_est_signalee_comme_telle(session, nom_maison, dossier_photos, stockage, tmp_path):
    inventaire_id = extraire(session, nom_maison, dossier_photos, stockage, ExtracteurScenario({4: "passagere"}))
    en_erreur = charger_inventaire(session, inventaire_id).bouteilles[3]
    for champ, valeur in OBLIGATOIRES.items():
        corriger(session, en_erreur.id, champ, valeur, EXPERT)
    valider(session, en_erreur.id, EXPERT)

    feuille = feuille_exportee(session, inventaire_id, tmp_path)
    assert colonne(feuille, "À vérifier")[3] == "Saisie manuelle"
    assert colonne(feuille, "Domaine / Château")[3] == "Domaine X"
    assert not (couleurs(feuille)[3] or "").endswith(COULEUR_ERREUR)


def test_l_export_est_permis_sans_rien_valider_et_avec_des_erreurs(session, nom_maison, dossier_photos, stockage, tmp_path):
    """Valider bouteille par bouteille reste facultatif ; une erreur a sa ligne."""
    inventaire_id = extraire(session, nom_maison, dossier_photos, stockage, ExtracteurScenario({1: "passagere"}))
    assert len(colonne(feuille_exportee(session, inventaire_id, tmp_path), "À vérifier")) == 6
    clore(session, inventaire_id, EXPERT)  # la clôture suit la même règle
    assert len(colonne(feuille_exportee(session, inventaire_id, tmp_path), "À vérifier")) == 6


def test_le_regroupement_ne_fusionne_jamais_une_bouteille_en_erreur_ou_saisie_a_la_main():
    config = charger_config(CONFIG_TEST)
    a, b = (from_tool_input(dict(PROPRE), config) for _ in range(2))
    a.id, b.id = "a", "b"
    assert regrouper([a, b], config) == [[a, b]]  # identiques, sans doute : une seule ligne
    for etat in (EtatLigne(erreur=True), EtatLigne(saisie_manuelle=True, relue=True)):
        assert regrouper([a, b], config, {"b": etat}) == [[a], [b]]
    assert regrouper([a, b], config, {"a": EtatLigne(relue=True), "b": EtatLigne(relue=True)}) == [[a, b]]


# --- colonne système « relue » (facultative) -------------------------------------------------------


@pytest.fixture
def config_avec_relue(tmp_path):
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["colonnes"].append(
        {"cle": "relue", "nom": "Relue", "type": "texte", "source": "systeme", "description": "Validée par l'expert."}
    )
    chemin = tmp_path / "maison_relue.json"
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    return chemin


def test_la_colonne_relue_dit_oui_pour_les_bouteilles_validees(session, nom_maison, dossier_photos, stockage, tmp_path, config_avec_relue):
    charges = [dict(PROPRE, domaine=f"Domaine {rang}") for rang in range(1, 7)]
    inventaire_id = extraire(
        session, nom_maison, dossier_photos, stockage,
        FixtureExtractor(charges, charger_config(config_avec_relue)), config=config_avec_relue,
    )
    inventaire = charger_inventaire(session, inventaire_id)
    for rang in (0, 2):
        valider(session, inventaire.bouteilles[rang].id, EXPERT)
    assert colonne(feuille_exportee(session, inventaire_id, tmp_path), "Relue") == ["oui", None, "oui", None, None, None]


def test_la_config_avertit_s_il_manque_la_colonne_a_verifier(tmp_path):
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["colonnes"] = [c for c in brut["colonnes"] if c["cle"] != "a_verifier"]
    chemin = tmp_path / "sans_a_verifier.json"
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    assert any("a_verifier" in a and "couleur" in a for a in charger_config(chemin).avertissements)
    assert not any("a_verifier" in a for a in charger_config(CONFIG_TEST).avertissements)


# --- par les écrans et l'API -----------------------------------------------------------------------


def test_l_api_et_le_recapitulatif_disent_pourquoi_l_excel_attend(api, dossier_photos):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    refus = api.get(f"/inventaires/{inventaire_id}/export")
    verifier_erreur(refus, 409, "export_refuse", "6 bouteille(s) encore en cours d'analyse")
    recap = api.get(f"/app/inventaires/{inventaire_id}/recapitulatif").text
    assert "Excel — il reste 6 bouteille(s)" in recap
    assert "Télécharger l'Excel" not in recap

    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    assert api.get(f"/inventaires/{inventaire_id}/export").status_code == 200
    assert "Télécharger l'Excel" in api.get(f"/app/inventaires/{inventaire_id}/recapitulatif").text


# --- temps de relecture sans validation (0169) ------------------------------------------------------


def test_le_temps_passe_sans_valider_est_compte(session, nom_maison, dossier_photos, stockage):
    inventaire_id = extraire(session, nom_maison, dossier_photos, stockage, ExtracteurScenario())
    premiere = charger_inventaire(session, inventaire_id).bouteilles[0]
    ajouter_temps_de_relecture(session, premiere.id, 40_000)
    ajouter_temps_de_relecture(session, premiere.id, 20_000)
    stats = stats_inventaire(session, inventaire_id)
    assert stats.temps_relecture_total_ms == 60_000 and stats.bouteilles_chronometrees == 1
    assert premiere.statut == "extraite"  # mesurer n'est pas valider

    clore(session, inventaire_id, EXPERT)  # une mesure, pas une modification
    ajouter_temps_de_relecture(session, premiere.id, 5_000)
    assert stats_inventaire(session, inventaire_id).temps_relecture_total_ms == 65_000


def test_l_ecran_envoie_le_temps_en_quittant_la_bouteille(api, dossier_photos):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    premiere = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"][0]["id"]

    page = api.get(f"/app/inventaires/{inventaire_id}/relecture/{premiere}").text
    assert 'name="_temps_ms"' in page
    reponse = api.post(f"/app/inventaires/{inventaire_id}/relecture/{premiere}/temps", data={"temps_ms": "12000"})
    assert reponse.status_code == 204
    stats = api.get(f"/inventaires/{inventaire_id}").json()["statistiques"]
    assert stats["temps_relecture_total_ms"] == 12000
    autre = api.post(f"/app/inventaires/{inventaire_id + 1}/relecture/{premiere}/temps", data={"temps_ms": "1000"})
    assert autre.status_code == 404  # la bouteille d'un autre inventaire : rien n'est compté
