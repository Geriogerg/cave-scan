"""Le schéma envoyé au modèle suit la config de la maison (guide, étape 4.2).

Contraintes vérifiées : colonnes expert et système JAMAIS dans le schéma, noyau
canonique toujours extrait, listes = enums avec « non déterminable », consigne
d'abstention ajoutée par le code, best effort toujours à vérifier.
Aucune valeur de maison_test.json n'est figée : tout est lu dans la config.
"""

from __future__ import annotations

import json

import pytest

from src.config.maison import charger_config
from src.extract.schema import (
    CHAMPS_HORS_MODELE,
    NATURE_DES_CHAMPS,
    NON_DETERMINABLE,
    NON_LISIBLE,
    Couleur,
    from_tool_input,
    schema_extraction,
    tool_schema,
)
from tests.conftest import RACINE

CONFIG_TEST = RACINE / "config" / "maisons" / "maison_test.json"


@pytest.fixture
def config():
    return charger_config(CONFIG_TEST)


@pytest.fixture
def proprietes(config):
    return schema_extraction(config)["input_schema"]["properties"]


def config_modifiee(tmp_path, modifier):
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    modifier(brut)
    chemin = tmp_path / "maison.json"
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    return charger_config(chemin)


def charge_complete(config):
    """Une réponse de modèle valide pour toutes les colonnes de la maison."""
    charge = {"appellation": "Pommard", "domaine": "Domaine X", "champs_a_verifier": []}
    for colonne in config.colonnes_modele:
        if colonne.type == "liste":
            charge[colonne.cle] = colonne.codes[0]
        elif colonne.type == "nombre":
            charge[colonne.cle] = 1
        else:
            charge.setdefault(colonne.cle, f"Texte lu pour {colonne.cle}")
    return charge


# --- ce qui entre dans le schéma, et ce qui n'y entre jamais ----------------------


def test_les_colonnes_modele_entrent_dans_le_schema(config, proprietes):
    for colonne in config.colonnes_modele:
        assert colonne.cle in proprietes, colonne.cle


def test_colonnes_expert_et_systeme_absentes_du_schema(config, proprietes):
    """Critère d'acceptation. Si le modèle les recevait, il essaierait de les remplir."""
    hors_modele = [c for c in config.colonnes if not c.envoyee_au_modele]
    assert hors_modele, "la config de test doit contenir des colonnes expert/système"
    schema_texte = json.dumps(schema_extraction(config), ensure_ascii=False)
    for colonne in hors_modele:
        assert colonne.cle not in proprietes, colonne.cle
        # Pas même leur description : rien de ces colonnes n'atteint le modèle.
        if colonne.description:
            assert colonne.description not in schema_texte, colonne.cle


def test_les_champs_du_pipeline_n_entrent_jamais(proprietes):
    for champ in CHAMPS_HORS_MODELE:
        assert champ not in proprietes, champ


def test_tout_le_schema_est_requis(config):
    schema = schema_extraction(config)["input_schema"]
    assert schema["required"] == list(schema["properties"])


def test_le_noyau_reste_extrait_meme_si_la_config_ne_l_affiche_pas(tmp_path):
    """decisions.md 0021 : retirer « format » de l'affichage ne l'ôte pas de l'extraction."""

    def retirer_format(brut):
        brut["colonnes"] = [c for c in brut["colonnes"] if c["cle"] != "format"]
        brut["regroupement_export"] = [c for c in brut["regroupement_export"] if c != "format"]

    sans_format = config_modifiee(tmp_path, retirer_format)
    schema = schema_extraction(sans_format)["input_schema"]
    for champ in ("domaine", "appellation", "millesime", "format"):
        assert champ in schema["properties"], champ
        assert champ in schema["required"], champ


def test_sans_config_le_schema_v0_est_inchange():
    assert schema_extraction(None) == tool_schema()


# --- vocabulaire et consignes ----------------------------------------------------


def test_une_liste_devient_un_enum_avec_non_determinable(config, proprietes):
    for colonne in config.colonnes_modele:
        if colonne.type == "liste":
            enum = proprietes[colonne.cle]["enum"]
            assert enum == list(colonne.codes), colonne.cle
            assert enum[-1] == NON_DETERMINABLE


def test_descriptions_de_valeurs_et_regle_injectees(config, proprietes):
    for colonne in config.colonnes_modele:
        description = proprietes[colonne.cle]["description"]
        if colonne.description:
            assert colonne.description in description, colonne.cle
        if colonne.regle:
            assert colonne.regle in description, colonne.cle
        for valeur in colonne.valeurs:
            if valeur.description:
                assert valeur.description in description, (colonne.cle, valeur.code)


def test_la_consigne_d_abstention_est_toujours_ajoutee(config, proprietes):
    """« Ne jamais deviner » ne dépend pas de la rédaction de la maison."""
    for colonne in config.colonnes_modele:
        description = proprietes[colonne.cle]["description"]
        assert "Ne jamais deviner" in description, colonne.cle
        attendu = {"liste": NON_DETERMINABLE, "texte": NON_LISIBLE, "nombre": "null"}[colonne.type]
        assert attendu in description, colonne.cle


def test_le_best_effort_est_annonce_comme_tel(config, proprietes):
    for colonne in config.colonnes_best_effort:
        assert "UNIQUEMENT sur ce qui est visible" in proprietes[colonne.cle]["description"]


def test_le_code_n_injecte_aucun_exemple(tmp_path):
    """Zero-shot (CLAUDE.md) : nos textes d'encadrement n'ajoutent aucun exemple.

    Les descriptions de la maison sont neutralisées pour ne tester que ce que
    le CODE ajoute ; les exemples écrits par la maison sont, eux, signalés au
    chargement (decisions.md 0053).
    """

    def neutraliser(brut):
        for colonne in brut["colonnes"]:
            colonne["description"] = "Description neutre."
            colonne.pop("regle", None)
            for valeur in colonne.get("valeurs", []):
                valeur["description"] = "Définition neutre."

    neutre = config_modifiee(tmp_path, neutraliser)
    texte = json.dumps(schema_extraction(neutre), ensure_ascii=False).casefold()
    for indice in ("exemple", "ex.", "e.g.", "par ex"):
        assert indice not in texte, indice


# --- lecture de la réponse avec la config ------------------------------------------


def test_les_colonnes_de_maison_vont_dans_valeurs_maison(config):
    charge = charge_complete(config)
    bouteille = from_tool_input(charge, config)
    for colonne in config.colonnes_modele:
        if colonne.cle not in NATURE_DES_CHAMPS:
            assert bouteille.valeurs_maison[colonne.cle] == charge[colonne.cle], colonne.cle


def test_le_vocabulaire_de_la_maison_fait_foi_pour_un_champ_v0(config):
    """Un code de maison absent de l'enum v0 est conservé, pas rabattu."""
    couleur = config.colonne("couleur")
    propre = next((c for c in couleur.codes if c not in {m.value for m in Couleur}), None)
    if propre is None:
        pytest.skip("la config de test n'a pas de couleur hors enum v0")
    assert from_tool_input({"couleur": propre}, config).couleur == propre


def test_un_code_hors_liste_devient_non_determinable(config):
    """Tolérance : une valeur hors vocabulaire produit une abstention, pas une invention."""
    for colonne in config.colonnes_modele:
        if colonne.type == "liste":
            bouteille = from_tool_input({colonne.cle: "pas_un_code"}, config)
            valeur = (
                getattr(bouteille, colonne.cle)
                if colonne.cle in NATURE_DES_CHAMPS
                else bouteille.valeurs_maison[colonne.cle]
            )
            assert valeur == NON_DETERMINABLE, colonne.cle


def test_best_effort_toujours_dans_champs_a_verifier(config):
    """CLAUDE.md : TOUJOURS ajoutés, que le modèle ait un doute ou non."""
    best_effort = [c.cle for c in config.colonnes_best_effort]
    assert best_effort, "la config de test doit avoir des colonnes best effort"
    bouteille = from_tool_input(charge_complete(config), config)
    for cle in best_effort:
        assert cle in bouteille.champs_a_verifier, cle


def test_best_effort_ajoute_une_seule_fois(config):
    charge = charge_complete(config)
    charge["champs_a_verifier"] = [c.cle for c in config.colonnes_best_effort]
    bouteille = from_tool_input(charge, config)
    assert len(bouteille.champs_a_verifier) == len(set(bouteille.champs_a_verifier))


def test_les_doutes_du_modele_sont_conserves(config):
    charge = charge_complete(config) | {"champs_a_verifier": ["millesime"]}
    assert from_tool_input(charge, config).champs_a_verifier[0] == "millesime"
