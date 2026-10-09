"""Ce qui sort d'un inventaire : export, statistiques, score du modèle.

Critères d'acceptation du guide couverts ici :
- non-régression : sur les fixtures, l'Excel exporté depuis la base est
  identique en contenu à celui de la session 1 ;
- modifier le JSON de config après création ne change pas l'export de cet
  inventaire ; un nouvel inventaire utilise une nouvelle version ;
- stats_inventaire renvoie des chiffres cohérents sur les fixtures.
"""

from __future__ import annotations

import json
import shutil

import pytest
from openpyxl import load_workbook

from src.compare.compare_listings import ENTETE_SCORE_MODELE, formater_rapport
from src.config.maison import charger_config
from src.export.excel_writer import ecrire_excel
from src.extract.base import SortieModele
from src.extract.fixture_extract import FixtureExtractor
from src.io.photos import apparier_photos
from src.normalize.normalize import normalize
from src.services.extraction import extraire_bouteille, extraire_inventaire
from src.services.inventaires import charger_inventaire, creer_inventaire
from src.services.relecture import corriger, valeurs_courantes, valider
from src.services.restitution import (
    bouteille_par_reference,
    comparer_au_listing,
    exporter,
    stats_inventaire,
)
from tests.conftest import CONFIG_TEST, FIXTURES
from tests.test_extraction import ExtracteurScenario


def charges():
    return json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))


def inventaire_sur_fixtures(session, nom_maison, dossier, stockage, config=CONFIG_TEST, nom="Cave"):
    cree = creer_inventaire(session, nom_maison, config, dossier, nom, stockage)
    extracteur = FixtureExtractor(charges(), charger_config(config))
    extraire_inventaire(session, cree.inventaire_id, extracteur, stockage)
    return cree.inventaire_id


def contenu_xlsx(chemin):
    """Tout ce qui fait le contenu d'un export : valeurs, types, surlignage,
    polices, largeurs, gel des en-têtes, propriétés du fichier."""
    classeur = load_workbook(chemin)
    feuille = classeur.active
    return {
        "feuille": feuille.title,
        "gel": feuille.freeze_panes,
        "cellules": [
            (c.coordinate, c.value, c.data_type, c.fill.fill_type, c.fill.fgColor.rgb, c.font.name, c.font.bold)
            for rangee in feuille.iter_rows()
            for c in rangee
        ],
        "largeurs": {lettre: dimension.width for lettre, dimension in feuille.column_dimensions.items()},
        "proprietes": (
            classeur.properties.title,
            classeur.properties.version,
            classeur.properties.subject,
            classeur.properties.language,
        ),
    }


# --- non-régression (critère du guide) ---------------------------------------------------


def export_comme_en_session_1(dossier, chemin):
    """Le chemin de la session 1 : extraction en mémoire, puis export direct."""
    config = charger_config(CONFIG_TEST)
    extracteur = FixtureExtractor(charges(), config)
    bouteilles = []
    for vues in apparier_photos(dossier).bouteilles:
        bouteille = normalize(extracteur.extract(vues.etiquette, vues.contre_etiquette))
        bouteille.id = vues.identifiant
        bouteilles.append(bouteille)
    return ecrire_excel(bouteilles, config, chemin)


def test_l_export_depuis_la_base_est_identique_a_celui_de_la_session_1(
    session, nom_maison, dossier_photos, stockage, tmp_path
):
    attendu = export_comme_en_session_1(dossier_photos, tmp_path / "session_1.xlsx")
    inventaire_id = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage)
    obtenu = exporter(session, inventaire_id, tmp_path / "depuis_la_base.xlsx")

    assert contenu_xlsx(obtenu) == contenu_xlsx(attendu)
    assert len(contenu_xlsx(obtenu)["cellules"]) == 7 * 12  # en-tête + 6 lignes, 12 colonnes


# --- config figée (critère du guide) ------------------------------------------------------


def test_modifier_le_json_apres_creation_ne_change_pas_l_export(session, nom_maison, dossier_photos, stockage, tmp_path):
    config = tmp_path / "maison_test.json"
    shutil.copy(CONFIG_TEST, config)
    ancien = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage, config=config, nom="A")
    avant = contenu_xlsx(exporter(session, ancien, tmp_path / "avant.xlsx"))

    brut = json.loads(config.read_text(encoding="utf-8"))
    brut["version"] += 1
    colonne = next(c for c in brut["colonnes"] if c["cle"] == "couleur")
    for valeur in colonne["valeurs"]:
        valeur["libelle"] += " (modifié)"
    config.write_text(json.dumps(brut, ensure_ascii=False, indent=2), encoding="utf-8")

    # L'inventaire existant ne bouge pas…
    assert contenu_xlsx(exporter(session, ancien, tmp_path / "apres.xlsx")) == avant

    # … un nouvel inventaire, lui, prend la nouvelle version.
    nouveau = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage, config=config, nom="B")
    assert charger_inventaire(session, nouveau).config_version.numero == 2
    feuille = load_workbook(exporter(session, nouveau, tmp_path / "nouveau.xlsx")).active
    index = [c.value for c in feuille[1]].index(colonne["nom"]) + 1
    couleurs = [feuille.cell(row=r, column=index).value for r in range(2, feuille.max_row + 1)]
    assert couleurs and all(c.endswith("(modifié)") for c in couleurs if c)
    assert load_workbook(tmp_path / "nouveau.xlsx").properties.version == str(brut["version"])


# --- export : corrections et regroupement ------------------------------------------------------


def test_l_export_affiche_les_corrections(session, nom_maison, dossier_photos, stockage, tmp_path):
    inventaire_id = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage)
    premiere = charger_inventaire(session, inventaire_id).bouteilles[0]
    corriger(session, premiere.id, "millesime", "1999", "expert")
    feuille = load_workbook(exporter(session, inventaire_id, tmp_path / "e.xlsx")).active
    index = [c.value for c in feuille[1]].index("Millésime") + 1
    assert feuille.cell(row=2, column=index).value == "1999"


class ExtracteurComplet:
    """Toutes les colonnes lues renseignées, identiques : de quoi regrouper."""

    modele = "complet"
    version_prompt = "v"

    def __init__(self, config):
        self.charge = {}
        for colonne in config.colonnes_modele:
            if colonne.type == "liste":
                self.charge[colonne.cle] = colonne.codes[0]
            elif colonne.type == "nombre":
                self.charge[colonne.cle] = 1
            else:
                self.charge[colonne.cle] = "Texte lu"

    def extraire_brut(self, etiquette, contre_etiquette=None, autres=None):
        return SortieModele(brut=dict(self.charge), modele=self.modele, version_prompt=self.version_prompt)

    def extract(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


def test_la_quantite_corrigee_est_additionnee_au_regroupement(session, nom_maison, dossier_photos, stockage, tmp_path):
    """Remplace le test « quantité modifiée au journal » : même exigence, par corriger."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurComplet(charger_config(CONFIG_TEST)), stockage)
    premiere = charger_inventaire(session, cree.inventaire_id).bouteilles[0]
    corriger(session, premiere.id, "quantite", 3, "expert")

    feuille = load_workbook(exporter(session, cree.inventaire_id, tmp_path / "e.xlsx")).active
    assert feuille.max_row == 2  # une seule ligne : 6 bouteilles identiques
    index = [c.value for c in feuille[1]].index("Qté") + 1
    assert feuille.cell(row=2, column=index).value == 8  # 3 + 5 × 1


# --- score du modèle (decisions.md 0081) ------------------------------------------------------


def test_la_comparaison_donne_le_meme_score_qu_en_session_1(session, nom_maison, dossier_photos, stockage):
    inventaire_id = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage)
    resultat = comparer_au_listing(session, inventaire_id, FIXTURES / "manuel.json")
    reperes = {(d.ligne, d.champ) for d in resultat.rapport.desaccords}
    assert reperes == {(4, "domaine"), (2, "cuvee"), (3, "millesime")}


def test_le_score_du_modele_ignore_les_corrections(session, nom_maison, dossier_photos, stockage):
    """Corriger le millésime comme le dit l'expert ne doit pas améliorer le
    score du MODÈLE, qui a bien lu 2004."""
    inventaire_id = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage)
    quatrieme = charger_inventaire(session, inventaire_id).bouteilles[3]
    corriger(session, quatrieme.id, "millesime", "2001", "expert")

    resultat = comparer_au_listing(session, inventaire_id, FIXTURES / "manuel.json")
    assert (3, "millesime") in {(d.ligne, d.champ) for d in resultat.rapport.desaccords}
    assert valeurs_courantes(session, quatrieme.id).millesime == "2001"


def test_le_rapport_dit_que_c_est_le_score_du_modele(session, nom_maison, dossier_photos, stockage):
    inventaire_id = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage)
    texte = formater_rapport(comparer_au_listing(session, inventaire_id, FIXTURES / "manuel.json").rapport)
    assert ENTETE_SCORE_MODELE in texte
    assert "SCORE DU MODÈLE" in texte and "sans les corrections" in texte


# --- statistiques (critère du guide) -----------------------------------------------------------


def test_stats_coherentes_sur_les_fixtures(session, nom_maison, dossier_photos, stockage):
    inventaire_id = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage)
    stats = stats_inventaire(session, inventaire_id)

    assert stats.nb_bouteilles == 6
    assert sum(stats.par_statut.values()) == stats.nb_bouteilles
    assert stats.par_statut["extraite"] == 6
    assert stats.nb_extractions == 6 and stats.nb_extractions_en_erreur == 0
    # Fixtures : aucun token consommé, donc aucun coût — et surtout pas un faux.
    assert (stats.tokens_entree, stats.tokens_sortie, stats.extractions_mesurees) == (0, 0, 0)
    assert stats.tokens_par_bouteille is None
    assert stats.champs_les_plus_corriges == []


def test_stats_cout_en_tokens_par_bouteille(session, nom_maison, dossier_photos, stockage):
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario(), stockage)
    stats = stats_inventaire(session, cree.inventaire_id)
    assert (stats.tokens_entree, stats.tokens_sortie) == (6000, 1200)
    assert stats.tokens_par_bouteille == (1000, 200)
    assert stats.duree_totale_ms >= 0


def test_stats_une_relance_est_comptee_dans_le_cout(session, nom_maison, dossier_photos, stockage):
    """Une relance est facturée : elle pèse sur le coût par bouteille."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario({2: "passagere"}), stockage)
    premiere = charger_inventaire(session, cree.inventaire_id).bouteilles[0]
    extraire_bouteille(session, premiere.id, ExtracteurScenario(), stockage, forcer=True)

    stats = stats_inventaire(session, cree.inventaire_id)
    assert stats.nb_extractions == 7
    assert stats.nb_extractions_en_erreur == 1
    assert stats.extractions_mesurees == 6  # la panne passagère n'a rien consommé
    assert stats.tokens_entree == 6000
    assert stats.par_statut["erreur"] == 1


def test_stats_champs_les_plus_corriges(session, nom_maison, dossier_photos, stockage):
    inventaire_id = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage)
    bouteilles = charger_inventaire(session, inventaire_id).bouteilles
    corriger(session, bouteilles[0].id, "millesime", "2015", "expert")
    corriger(session, bouteilles[1].id, "millesime", "2016", "expert")
    corriger(session, bouteilles[1].id, "domaine", "Domaine Y", "expert")
    valider(session, bouteilles[2].id, "expert")  # un changement de statut n'est pas une correction

    stats = stats_inventaire(session, inventaire_id)
    assert stats.champs_les_plus_corriges == [("millesime", 2), ("domaine", 1)]
    assert (stats.nb_corrections, stats.nb_bouteilles_corrigees) == (3, 2)
    assert stats.par_statut["validee"] == 1


# --- désigner une bouteille comme l'utilisateur la voit --------------------------------------------


def test_une_bouteille_se_designe_par_identifiant_ou_position(session, nom_maison, dossier_photos, stockage):
    inventaire_id = inventaire_sur_fixtures(session, nom_maison, dossier_photos, stockage)
    troisieme = charger_inventaire(session, inventaire_id).bouteilles[2]
    assert bouteille_par_reference(session, inventaire_id, troisieme.identifiant.lower()).id == troisieme.id
    assert bouteille_par_reference(session, inventaire_id, "3").id == troisieme.id
    with pytest.raises(LookupError, match="Aucune bouteille"):
        bouteille_par_reference(session, inventaire_id, "B-INEXISTANT")
