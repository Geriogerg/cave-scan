"""Le chargeur du listing expert doit échouer bruyamment, jamais en silence.

Un outil de mesure qui produit un rapport propre à partir d'un fichier mal lu
est plus dangereux qu'un outil qui plante.
"""

from __future__ import annotations

import json

import pytest
from openpyxl import Workbook

from src.compare.compare_listings import comparer
from src.config.maison import charger_config
from src.export.excel_writer import ecrire_excel
from src.extract.schema import CHAMPS_COMPARABLES, Bouteille, from_tool_input
from src.io.manual_listing import (
    _aligner,
    colonnes_toujours_vides,
    load_manual,
)
from tests.conftest import FIXTURES


def ecrire(tmp_path, lignes, nom="manuel.json"):
    chemin = tmp_path / nom
    chemin.write_text(json.dumps(lignes, ensure_ascii=False), encoding="utf-8")
    return chemin


# --- alignement ---------------------------------------------------------


def test_les_champs_canoniques_sont_tous_presents():
    aligne = _aligner({"domaine": "Domaine X"})
    assert set(aligne) == set(CHAMPS_COMPARABLES)


def test_les_colonnes_inconnues_sont_ignorees():
    """Le fichier de l'expert a des colonnes qui ne nous concernent pas."""
    aligne = _aligner({"domaine": "Domaine X", "lot": 42, "estimation": "800-1000"})
    assert aligne["domaine"] == "Domaine X"
    assert "lot" not in aligne
    assert "estimation" not in aligne


# --- le garde-fou qui manquait ------------------------------------------


def test_entetes_totalement_differents_leve_une_erreur(tmp_path):
    """Le mode de panne fermé : « Producteur » au lieu de « domaine ».

    Sans ce garde-fou, le rapport sortait manuel_vide partout — propre,
    crédible, entièrement faux.
    """
    chemin = ecrire(
        tmp_path,
        [
            {"Producteur": "Domaine X", "Appellation": "Pommard", "Millesime": "2018"},
            {"Producteur": "Domaine Y", "Appellation": "Volnay", "Millesime": "2019"},
        ],
    )
    with pytest.raises(ValueError, match="aucune colonne ne correspond"):
        load_manual(chemin)


def test_une_seule_colonne_reconnue_suffit_a_passer(tmp_path):
    """On refuse le mapping NUL, pas le mapping partiel — l'expert a le droit
    de ne pas remplir la moitié de ses colonnes."""
    chemin = ecrire(tmp_path, [{"domaine": "Domaine X", "Producteur": "ignoré"}])
    lignes = load_manual(chemin)
    assert lignes[0]["domaine"] == "Domaine X"


def test_listing_vide_leve_une_erreur(tmp_path):
    with pytest.raises(ValueError, match="listing manuel vide"):
        load_manual(ecrire(tmp_path, []))


# --- avertissement (signalé, pas sanctionné) ----------------------------


def test_colonnes_toujours_vides_sont_signalees():
    manuel = load_manual(FIXTURES / "manuel.json")
    vides = colonnes_toujours_vides(manuel)
    # Les fixtures renseignent l'importateur sur une ligne : rien n'est vide partout.
    assert vides == []

    partiel = [{"domaine": "X", "appellation": ""}, {"domaine": "Y", "appellation": ""}]
    vides = colonnes_toujours_vides(partiel)
    assert "appellation" in vides
    assert "domaine" not in vides


def test_une_colonne_vide_partout_ne_fausse_pas_l_accuracy():
    """Elle compte manuel_vide, donc accuracy vaut None : rien n'est inventé."""
    rapport = comparer([Bouteille(domaine="X")], [{"domaine": "", "appellation": "X"}])
    domaine = next(s for s in rapport.scores if s.champ == "domaine")
    assert domaine.manuel_vide == 1
    assert domaine.accuracy is None


# --- formats non pris en charge -----------------------------------------


def test_csv_pas_encore_pris_en_charge(tmp_path):
    faux = tmp_path / "listing.csv"
    faux.write_text("domaine\nX\n", encoding="utf-8")
    with pytest.raises(NotImplementedError, match="Formats lus"):
        load_manual(faux)


# --- lecture .xlsx ------------------------------------------------------


def ecrire_xlsx(tmp_path, entetes, lignes, nom="listing.xlsx"):
    classeur = Workbook()
    feuille = classeur.active
    feuille.append(entetes)
    for ligne in lignes:
        feuille.append(ligne)
    chemin = tmp_path / nom
    classeur.save(chemin)
    return chemin


CONFIG_TEST = FIXTURES.parent.parent / "config" / "maisons" / "maison_test.json"


def test_lecture_d_un_xlsx(tmp_path):
    """Adapté : les en-têtes de maison viennent de la config, plus d'exemple.yaml.
    Un nom de champ canonique (« Contenance (cl) ») reste reconnu sans elle."""
    config = charger_config(CONFIG_TEST)
    chemin = ecrire_xlsx(
        tmp_path,
        [
            config.colonne("domaine").nom,
            config.colonne("appellation").nom,
            config.colonne("millesime").nom,
            "Contenance (cl)",
        ],
        [["Domaine Rossignol-Trapet", "Gevrey-Chambertin", "2018", 75]],
    )
    lignes = load_manual(chemin, config)

    assert len(lignes) == 1
    assert lignes[0]["domaine"] == "Domaine Rossignol-Trapet"
    assert lignes[0]["millesime"] == "2018"
    assert lignes[0]["contenance_cl"] == 75


def test_les_libelles_de_la_maison_sont_ramenes_a_leur_code(tmp_path):
    """On compare des codes stables, pas des libellés modifiables."""
    config = charger_config(CONFIG_TEST)
    liste = next(c for c in config.colonnes_modele if c.type == "liste")
    valeur = liste.valeurs[0]
    chemin = ecrire_xlsx(
        tmp_path, [liste.nom, config.colonne("domaine").nom], [[valeur.libelle.upper(), "Domaine X"]]
    )
    assert load_manual(chemin, config)[0][liste.cle] == valeur.code


def test_une_valeur_hors_liste_reste_telle_quelle(tmp_path):
    """Elle ressortira en désaccord, visible, plutôt que corrigée en silence."""
    config = charger_config(CONFIG_TEST)
    liste = next(c for c in config.colonnes_modele if c.type == "liste")
    chemin = ecrire_xlsx(
        tmp_path, [liste.nom, config.colonne("domaine").nom], [["Valeur inconnue", "Domaine X"]]
    )
    assert load_manual(chemin, config)[0][liste.cle] == "Valeur inconnue"


def test_les_accents_et_la_casse_des_entetes_sont_absorbes(tmp_path):
    chemin = ecrire_xlsx(tmp_path, ["MILLÉSIME", "appellation"], [["2018", "Pommard"]])
    lignes = load_manual(chemin)
    assert lignes[0]["millesime"] == "2018"
    assert lignes[0]["appellation"] == "Pommard"


def test_les_colonnes_maison_sont_ignorees(tmp_path):
    """Lot et Estimation ne nous concernent pas."""
    chemin = ecrire_xlsx(
        tmp_path, ["Lot", "Domaine", "Estimation"], [[42, "Domaine X", "800-1000"]]
    )
    assert load_manual(chemin)[0]["domaine"] == "Domaine X"


def test_les_lignes_vides_sont_sautees(tmp_path):
    chemin = ecrire_xlsx(
        tmp_path, ["Domaine"], [["Domaine X"], [None], ["Domaine Y"], [""]]
    )
    assert len(load_manual(chemin)) == 2


def test_un_xlsx_aux_entetes_inconnus_leve_une_erreur(tmp_path):
    chemin = ecrire_xlsx(tmp_path, ["Producteur", "Cru"], [["Domaine X", "Pommard"]])
    with pytest.raises(ValueError, match="aucune colonne ne correspond"):
        load_manual(chemin)


def test_aller_retour_excel_le_fichier_produit_se_relit(tmp_path):
    """Le test que l'utilisateur peut faire seul : exporter, éditer, comparer.

    Sans cet aller-retour, impossible de se comparer à soi-même avant que le
    fichier de l'expert existe.
    """
    charges = json.loads(
        (FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8")
    )
    bouteilles = [from_tool_input(charge) for charge in charges]
    config = charger_config(CONFIG_TEST)
    chemin = ecrire_excel(bouteilles, config, tmp_path / "auto.xlsx")

    relu = load_manual(chemin, config)

    assert len(relu) == len(bouteilles)
    assert relu[0]["domaine"] == "Domaine Rossignol-Trapet"
    assert relu[0]["millesime"] == "2018"

    # Et comparé à lui-même : zéro désaccord — libellés relus comme des codes,
    # abstentions relues comme des cases vides (jamais comme des valeurs).
    rapport = comparer(bouteilles, relu)
    assert rapport.desaccords == []


def test_fichier_absent(tmp_path):
    with pytest.raises(FileNotFoundError, match="introuvable"):
        load_manual(tmp_path / "fantome.json")
