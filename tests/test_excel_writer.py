"""L'export suit la config de la maison, et respecte les contraintes dures.

Réécrit pour la config JSON (l'ancienne version encodait le format YAML). Les
contraintes dures gardent la même exigence :
- la colonne estimation (et toute colonne expert) reste vide ;
- une abstention n'est jamais masquée : case vide ET ligne surlignée (CLAUDE.md),
  jamais remplacée par une valeur ;
- aucune formule ;
- police Arial, en-têtes figés.

Aucune valeur de maison_test.json (fichier fictif) n'est figée ici : codes et
libellés sont lus dans la config.
"""

from __future__ import annotations

import json

import pytest
from openpyxl import load_workbook

from src.config.maison import COLONNE_QUANTITE, charger_config
from src.export.excel_writer import a_relire, ecrire_excel
from src.extract.schema import (
    NATURE_DES_CHAMPS,
    NON_DETERMINABLE,
    NON_LISIBLE,
    Bouteille,
    from_tool_input,
)
from tests.conftest import FIXTURES, RACINE

CONFIG_TEST = RACINE / "tests" / "fixtures" / "maison_test.json"


@pytest.fixture
def config():
    return charger_config(CONFIG_TEST)


def config_modifiee(tmp_path, modifier):
    """Copie de maison_test.json modifiée par `modifier(dict)`, puis rechargée."""
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    modifier(brut)
    chemin = tmp_path / "maison_modifiee.json"
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    return charger_config(chemin)


def poser(bouteille, colonne, valeur):
    """Écrit une valeur là où le pipeline la range pour cette colonne."""
    if colonne.cle in NATURE_DES_CHAMPS:
        setattr(bouteille, colonne.cle, valeur)
    else:
        bouteille.valeurs_maison[colonne.cle] = valeur


def bouteille_complete(config):
    """Toutes les colonnes lues par le modèle renseignées, sans aucun doute."""
    bouteille = Bouteille(id="B-TEST")
    for colonne in config.colonnes_modele:
        if colonne.type == "liste":
            poser(bouteille, colonne, colonne.codes[0])
        elif colonne.type == "nombre":
            poser(bouteille, colonne, 1)
        else:
            poser(bouteille, colonne, f"Texte lu pour {colonne.cle}")
    return bouteille


def exporter(tmp_path, bouteilles, config):
    chemin = ecrire_excel(bouteilles, config, tmp_path / "listing.xlsx")
    return load_workbook(chemin).active


def cellule(feuille, config, cle, ligne=2):
    index = [c.cle for c in config.colonnes].index(cle) + 1
    return feuille.cell(row=ligne, column=index)


def surlignee(feuille, ligne):
    return feuille.cell(row=ligne, column=1).fill.fill_type == "solid"


@pytest.fixture
def fixtures():
    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))
    return [from_tool_input(charge) for charge in charges]


# --- l'export suit la config ------------------------------------------------


def test_entetes_et_ordre_exactement_selon_la_config(tmp_path, config, fixtures):
    feuille = exporter(tmp_path, fixtures, config)
    assert [c.value for c in feuille[1]] == [c.nom for c in config.colonnes]
    assert feuille.max_row == len(fixtures) + 1


def test_changer_un_libelle_dans_le_json_change_l_export(tmp_path, config):
    """Critère d'acceptation : un libellé modifié dans le JSON change l'export,
    sans toucher au code."""
    liste = next(c for c in config.colonnes_modele if c.type == "liste")
    code = liste.codes[0]

    def modifier(brut):
        colonne = next(c for c in brut["colonnes"] if c["cle"] == liste.cle)
        colonne["nom"] = "En-tête renommé"
        valeur = next(v for v in colonne["valeurs"] if v["code"] == code)
        valeur["libelle"] = "Libellé renommé"

    modifiee = config_modifiee(tmp_path, modifier)
    bouteille = bouteille_complete(modifiee)
    feuille = exporter(tmp_path, [bouteille], modifiee)

    assert cellule(feuille, modifiee, liste.cle, ligne=1).value == "En-tête renommé"
    assert cellule(feuille, modifiee, liste.cle).value == "Libellé renommé"


def test_reordonner_les_colonnes_dans_le_json_reordonne_l_export(tmp_path):
    inversee = config_modifiee(tmp_path, lambda brut: brut["colonnes"].reverse())
    feuille = exporter(tmp_path, [bouteille_complete(inversee)], inversee)
    assert [c.value for c in feuille[1]] == [c.nom for c in inversee.colonnes]


def test_un_code_s_affiche_avec_son_libelle(tmp_path, config):
    bouteille = bouteille_complete(config)
    feuille = exporter(tmp_path, [bouteille], config)
    for colonne in config.colonnes_modele:
        if colonne.type == "liste":
            assert cellule(feuille, config, colonne.cle).value == colonne.libelle(colonne.codes[0])


def test_la_version_de_la_config_est_copiee_dans_l_export(tmp_path, config, fixtures):
    """Guide, étape 4.1 : savoir quelle config a produit un fichier."""
    chemin = ecrire_excel(fixtures, config, tmp_path / "listing.xlsx")
    proprietes = load_workbook(chemin).properties
    assert proprietes.version == str(config.version)
    assert config.maison in proprietes.title
    assert f"v{config.version}" in proprietes.title


def test_l_identifiant_s_affiche(tmp_path, config):
    feuille = exporter(tmp_path, [bouteille_complete(config)], config)
    assert cellule(feuille, config, "id").value == "B-TEST"


# --- colonnes expert : jamais remplies par l'outil ---------------------------


def test_colonnes_expert_restent_vides_estimation_comprise(tmp_path, config, fixtures):
    """decisions.md 0005 : le modèle ne produit aucun prix. Plus largement,
    l'outil n'écrit dans aucune colonne expert, sauf la quantité (1 par défaut)."""
    experts = [c for c in config.colonnes if c.source == "expert" and c.cle != COLONNE_QUANTITE]
    assert experts, "la config de test doit contenir au moins une colonne expert"

    feuille = exporter(tmp_path, fixtures, config)
    for colonne in experts:
        for ligne in range(2, feuille.max_row + 1):
            assert cellule(feuille, config, colonne.cle, ligne).value is None, (colonne.cle, ligne)


def test_une_estimation_renvoyee_par_le_modele_n_atteint_pas_l_export(tmp_path, config):
    """Même si le modèle la renvoie, elle n'existe nulle part dans la bouteille."""
    experts = [c for c in config.colonnes if c.source == "expert" and c.cle != COLONNE_QUANTITE]
    charge = {colonne.cle: "800-1000" for colonne in experts} | {"appellation": "Pommard"}
    feuille = exporter(tmp_path, [from_tool_input(charge)], config)
    for colonne in experts:
        assert cellule(feuille, config, colonne.cle).value is None


def test_la_quantite_vaut_un_par_defaut(tmp_path, config, fixtures):
    feuille = exporter(tmp_path, fixtures, config)
    for ligne in range(2, feuille.max_row + 1):
        assert cellule(feuille, config, COLONNE_QUANTITE, ligne).value == 1


# --- abstention : case vide ET ligne surlignée (CLAUDE.md) --------------------


@pytest.mark.parametrize("type_", ["texte", "liste"])
def test_une_abstention_laisse_la_case_vide_et_surligne_la_ligne(tmp_path, config, type_):
    """Remplace l'ancien test « le libellé d'abstention s'affiche » : la règle a
    changé (CLAUDE.md), l'exigence non — l'abstention reste VISIBLE."""
    colonne = next(c for c in config.colonnes_modele if c.type == type_)
    bouteille = bouteille_complete(config)
    poser(bouteille, colonne, NON_LISIBLE if type_ == "texte" else NON_DETERMINABLE)

    feuille = exporter(tmp_path, [bouteille], config)

    assert cellule(feuille, config, colonne.cle).value is None
    assert surlignee(feuille, 2)


def test_une_abstention_n_est_jamais_ecrite_ni_maquillee(tmp_path, config):
    """Ni le code interne, ni « Non déterminable », ni une valeur de repli."""
    bouteille = Bouteille(id="B-TEST")  # tout en abstention
    feuille = exporter(tmp_path, [bouteille], config)
    for colonne in config.colonnes_modele:
        valeur = cellule(feuille, config, colonne.cle).value
        assert valeur is None, (colonne.cle, valeur)
    assert surlignee(feuille, 2)


def test_une_ligne_complete_sans_doute_n_est_pas_surlignee(tmp_path, config):
    feuille = exporter(tmp_path, [bouteille_complete(config)], config)
    assert not surlignee(feuille, 2)


def test_un_doute_precis_du_modele_surligne_la_ligne(tmp_path, config):
    bouteille = bouteille_complete(config)
    hors_best_effort = next(c for c in config.colonnes_modele if c.source == "modele")
    bouteille.champs_a_verifier.append(hors_best_effort.cle)
    assert a_relire(bouteille, config)


def test_les_champs_best_effort_ne_surlignent_pas_a_eux_seuls(tmp_path, config):
    """Toujours à vérifier par principe : s'ils surlignaient, toutes les lignes le seraient."""
    bouteille = bouteille_complete(config)
    bouteille.champs_a_verifier = [c.cle for c in config.colonnes_best_effort]
    assert bouteille.champs_a_verifier, "la config de test doit avoir des colonnes best effort"
    feuille = exporter(tmp_path, [bouteille], config)
    assert not surlignee(feuille, 2)
    assert cellule(feuille, config, "a_verifier").value == ", ".join(c.nom for c in config.colonnes_best_effort)


def test_un_code_hors_vocabulaire_est_affiche_et_surligne(tmp_path, config):
    """Jamais masqué : visible tel quel, et la ligne demande une relecture."""
    liste = next(c for c in config.colonnes_modele if c.type == "liste")
    bouteille = bouteille_complete(config)
    poser(bouteille, liste, "code_hors_vocabulaire")
    feuille = exporter(tmp_path, [bouteille], config)
    assert cellule(feuille, config, liste.cle).value == "code_hors_vocabulaire"
    assert surlignee(feuille, 2)


# --- forme du fichier -----------------------------------------------------------


def test_aucune_formule(tmp_path, config, fixtures):
    feuille = exporter(tmp_path, fixtures, config)
    for rangee in feuille.iter_rows():
        for case in rangee:
            assert case.data_type != "f", case.coordinate


def test_un_texte_lu_qui_ressemble_a_une_formule_reste_du_texte(tmp_path, config):
    """Une étiquette ne doit jamais faire exécuter une formule à l'ouverture."""
    texte = next(c for c in config.colonnes_modele if c.type == "texte")
    bouteille = bouteille_complete(config)
    poser(bouteille, texte, "=1+1")
    feuille = exporter(tmp_path, [bouteille], config)
    case = cellule(feuille, config, texte.cle)
    assert case.data_type == "s"
    assert case.value == "=1+1"


def test_police_arial_et_entetes_figes(tmp_path, config, fixtures):
    feuille = exporter(tmp_path, fixtures, config)
    assert feuille.freeze_panes == "A2"
    assert feuille["A1"].font.name == "Arial"
    assert feuille["A1"].font.bold is True
    assert feuille["A2"].font.name == "Arial"
    assert feuille["A2"].font.bold is False


def test_les_colonnes_nombre_ne_contiennent_que_des_nombres(tmp_path):
    """Une colonne numérique doit rester triable : nombres ou case vide."""

    def ajouter_degre(brut):
        brut["colonnes"].append(
            {"cle": "degre", "nom": "Degré", "type": "nombre", "source": "modele"}
        )

    config = config_modifiee(tmp_path, ajouter_degre)
    avec, sans = bouteille_complete(config), bouteille_complete(config)
    avec.degre, sans.degre = 13.5, None
    feuille = exporter(tmp_path, [avec, sans], config)

    assert cellule(feuille, config, "degre", 2).value == 13.5
    assert cellule(feuille, config, "degre", 3).value is None
    assert surlignee(feuille, 3)
    for ligne in (2, 3):
        valeur = cellule(feuille, config, COLONNE_QUANTITE, ligne).value
        assert isinstance(valeur, int)


def test_a_verifier_liste_les_champs_par_leur_nom_de_colonne(tmp_path, config):
    """Rapport du testeur, T1-M2 : les noms de colonnes de la maison, pas les clés."""
    bouteille = bouteille_complete(config)
    bouteille.champs_a_verifier = ["millesime", "format"]
    feuille = exporter(tmp_path, [bouteille], config)
    attendu = f"{config.colonne('millesime').nom}, {config.colonne('format').nom}"
    assert attendu == "Millésime, Format"
    assert cellule(feuille, config, "a_verifier").value == attendu
