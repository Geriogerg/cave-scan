"""L'export doit rester piloté par la config, et ne jamais remplir l'estimation."""

from __future__ import annotations

import json

import pytest
from openpyxl import load_workbook

from src.export.excel_writer import (
    Colonne,
    charger_config,
    ecrire_excel,
    valeur_cellule,
)
from src.extract.schema import Bouteille, Couleur, Format, from_tool_input
from tests.conftest import FIXTURES

CONFIG_EXEMPLE = FIXTURES.parent.parent / "config" / "maisons" / "exemple.yaml"


@pytest.fixture
def config():
    return charger_config(CONFIG_EXEMPLE)


@pytest.fixture
def bouteilles():
    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))
    return [from_tool_input(charge) for charge in charges]


@pytest.fixture
def feuille(tmp_path, bouteilles, config):
    chemin = ecrire_excel(bouteilles, config, tmp_path / "listing.xlsx")
    return load_workbook(chemin).active


# --- config -------------------------------------------------------------


def test_config_exemple_se_charge(config):
    assert config.maison == "Maison Exemple"
    assert config.police == "Arial"
    assert config.figer_entetes is True
    assert len(config.colonnes) == 17


def test_config_refuse_un_champ_inconnu(tmp_path):
    """Une faute de frappe en config doit s'arrêter ici, pas livrer une colonne vide."""
    mauvais = tmp_path / "mauvais.yaml"
    mauvais.write_text(
        "maison: X\ncolonnes:\n  - entete: Domaine\n    champ: domaien\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="champ inconnu"):
        charger_config(mauvais)


def test_config_refuse_zero_colonne(tmp_path):
    vide = tmp_path / "vide.yaml"
    vide.write_text("maison: X\ncolonnes: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="aucune colonne"):
        charger_config(vide)


# --- traduction des valeurs ---------------------------------------------


def test_colonne_sans_champ_sort_vide():
    assert valeur_cellule(Bouteille(), Colonne(entete="Lot", champ=None), {}) == ""


def test_abstentions_prennent_le_libelle_de_la_maison():
    libelles = {
        "non_lisible": "non lisible",
        "non_determinable": "non déterminable",
        "numerique_absent": "non lisible",
    }
    bouteille = Bouteille()
    assert valeur_cellule(bouteille, Colonne("A", "domaine"), libelles) == "non lisible"
    assert valeur_cellule(bouteille, Colonne("A", "format"), libelles) == "non déterminable"
    assert valeur_cellule(bouteille, Colonne("A", "contenance_cl"), libelles) == "non lisible"


def test_les_nombres_restent_des_nombres():
    bouteille = Bouteille(contenance_cl=150, degre=14.5)
    assert valeur_cellule(bouteille, Colonne("A", "contenance_cl"), {}) == 150
    assert valeur_cellule(bouteille, Colonne("A", "degre"), {}) == 14.5


def test_enums_sortent_en_texte():
    bouteille = Bouteille(couleur=Couleur.ROUGE, format=Format.MAGNUM)
    assert valeur_cellule(bouteille, Colonne("A", "couleur"), {}) == "rouge"
    assert valeur_cellule(bouteille, Colonne("A", "format"), {}) == "magnum"


def test_champs_a_verifier_est_aplati():
    bouteille = Bouteille(champs_a_verifier=["millesime", "degre"])
    assert (
        valeur_cellule(bouteille, Colonne("A", "champs_a_verifier"), {})
        == "millesime, degre"
    )


# --- fichier produit ----------------------------------------------------


def test_entetes_et_lignes(feuille, bouteilles, config):
    assert [c.value for c in feuille[1]] == [c.entete for c in config.colonnes]
    assert feuille.max_row == len(bouteilles) + 1


def test_colonne_estimation_reste_vide(feuille, config):
    """decisions.md 0005 : le modèle ne produit aucun prix."""
    index = [c.entete for c in config.colonnes].index("Estimation") + 1
    for ligne in range(2, feuille.max_row + 1):
        assert feuille.cell(row=ligne, column=index).value in (None, "")


def test_aucune_formule(feuille):
    for ligne in feuille.iter_rows():
        for cellule in ligne:
            assert not (isinstance(cellule.value, str) and cellule.value.startswith("="))


def test_police_arial_et_entetes_figes(feuille, config):
    assert feuille.freeze_panes == "A2"
    assert feuille["A1"].font.name == "Arial"
    assert feuille["A1"].font.bold is True
    assert feuille["A2"].font.name == "Arial"
    assert feuille["A2"].font.bold is False


def test_lignes_a_verifier_sont_surlignees(feuille, bouteilles, config):
    """Les bouteilles 1 et 3 des fixtures ont des champs_a_verifier."""
    attendues = {
        numero
        for numero, bouteille in enumerate(bouteilles, start=2)
        if bouteille.champs_a_verifier
    }
    assert attendues == {3, 5}

    for numero in range(2, feuille.max_row + 1):
        remplie = feuille.cell(row=numero, column=1).fill.fill_type == "solid"
        assert remplie is (numero in attendues), numero


def test_millesime_non_lisible_apparait_tel_quel(feuille, config):
    """L'abstention s'affiche, elle ne se cache pas."""
    index = [c.entete for c in config.colonnes].index("Millésime") + 1
    assert feuille.cell(row=3, column=index).value == "non lisible"
