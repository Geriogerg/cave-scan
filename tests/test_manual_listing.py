"""Le chargeur du listing expert doit échouer bruyamment, jamais en silence.

Un outil de mesure qui produit un rapport propre à partir d'un fichier mal lu
est plus dangereux qu'un outil qui plante.
"""

from __future__ import annotations

import json

import pytest

from src.compare.compare_listings import comparer
from src.extract.schema import CHAMPS_COMPARABLES, Bouteille
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


def test_xlsx_renvoie_vers_le_todo(tmp_path):
    faux = tmp_path / "listing.xlsx"
    faux.write_bytes(b"pas un vrai xlsx")
    with pytest.raises(NotImplementedError, match="reste à écrire"):
        load_manual(faux)


def test_fichier_absent(tmp_path):
    with pytest.raises(FileNotFoundError, match="introuvable"):
        load_manual(tmp_path / "fantome.json")
