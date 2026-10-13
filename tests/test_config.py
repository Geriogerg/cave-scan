"""La config de maison est validée strictement au chargement (guide, étape 4.1).

Une config mal écrite ne doit jamais produire un export plausible et faux :
chaque anomalie doit être refusée avec un message qui dit quoi corriger.
Aucun test ne fige une VALEUR de maison_test.json (fichier fictif) : on teste
la forme, sur des copies modifiées.
"""

from __future__ import annotations

import copy
import json

import pytest

from src.config.maison import (
    LIBELLE_NON_DETERMINABLE,
    ConfigInvalide,
    charger_config,
)
from src.extract.schema import NON_DETERMINABLE
from tests.conftest import RACINE

CONFIG_TEST = RACINE / "tests" / "fixtures" / "maison_test.json"


@pytest.fixture
def brut():
    """Le contenu de maison_test.json, à modifier dans chaque test."""
    return json.loads(CONFIG_TEST.read_text(encoding="utf-8"))


def ecrire(tmp_path, contenu, nom="maison.json"):
    chemin = tmp_path / nom
    texte = contenu if isinstance(contenu, str) else json.dumps(contenu, ensure_ascii=False)
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def colonne(brut, cle):
    return next(c for c in brut["colonnes"] if c["cle"] == cle)


def refusee(tmp_path, brut, motif):
    with pytest.raises(ConfigInvalide, match=motif):
        charger_config(ecrire(tmp_path, brut))


# --- la config de test --------------------------------------------------


def test_la_config_de_test_est_valide():
    config = charger_config(CONFIG_TEST)
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    assert [c.cle for c in config.colonnes] == [c["cle"] for c in brut["colonnes"]]
    assert config.version == brut["version"]


def test_la_version_est_un_entier_conserve():
    config = charger_config(CONFIG_TEST)
    assert isinstance(config.version, int) and not isinstance(config.version, bool)


def test_les_cles_de_commentaire_sont_ignorees(tmp_path, brut):
    brut["_note"] = "commentaire libre"
    colonne(brut, "domaine")["_note"] = "idem dans une colonne"
    charger_config(ecrire(tmp_path, brut))


# --- « Non déterminable » ajouté d'office ---------------------------------


def test_non_determinable_ajoute_a_chaque_liste():
    config = charger_config(CONFIG_TEST)
    listes = [c for c in config.colonnes if c.type == "liste"]
    assert listes, "la config de test doit contenir au moins une liste"
    for liste in listes:
        assert liste.codes[-1] == NON_DETERMINABLE, liste.cle
        assert liste.libelle(NON_DETERMINABLE) == LIBELLE_NON_DETERMINABLE


def test_non_determinable_n_est_pas_ecrit_dans_le_fichier(brut):
    """Ajouté au chargement, sans figurer dans le JSON."""
    for col in brut["colonnes"]:
        for valeur in col.get("valeurs", []):
            assert valeur["code"] != NON_DETERMINABLE


def test_non_determinable_absent_des_colonnes_non_liste():
    config = charger_config(CONFIG_TEST)
    for col in config.colonnes:
        if col.type != "liste":
            assert col.valeurs == ()


def test_ecrire_non_determinable_soi_meme_est_refuse(tmp_path, brut):
    colonne(brut, "couleur")["valeurs"].append(
        {"code": "non_determinable", "libelle": "Non déterminable"}
    )
    refusee(tmp_path, brut, "ajoutée d'office")


# --- clés uniques ---------------------------------------------------------


def test_cle_json_en_double_refusee(tmp_path):
    """`json` garderait silencieusement la dernière occurrence."""
    texte = CONFIG_TEST.read_text(encoding="utf-8").replace(
        '"nom": "Appellation",', '"nom": "Appellation", "nom": "Appel.",', 1
    )
    assert texte != CONFIG_TEST.read_text(encoding="utf-8")
    with pytest.raises(ConfigInvalide, match=r"« nom » en double.*« appellation »"):
        charger_config(ecrire(tmp_path, texte))


def test_cle_racine_en_double_refusee(tmp_path):
    texte = CONFIG_TEST.read_text(encoding="utf-8")
    version = json.loads(texte)["version"]
    texte = texte.replace(f'"version": {version},', f'"version": {version}, "version": {version + 1},', 1)
    with pytest.raises(ConfigInvalide, match="« version » en double"):
        charger_config(ecrire(tmp_path, texte))


def test_deux_colonnes_meme_cle_refusees(tmp_path, brut):
    brut["colonnes"].append(copy.deepcopy(colonne(brut, "cuvee")) | {"nom": "Autre en-tête"})
    refusee(tmp_path, brut, "« cuvee » : clé en double")


def test_deux_colonnes_meme_en_tete_refusees(tmp_path, brut):
    """À la casse près : le fichier de l'expert serait impossible à relire."""
    colonne(brut, "cuvee")["nom"] = colonne(brut, "appellation")["nom"].upper()
    refusee(tmp_path, brut, "même en-tête")


def test_code_en_double_refuse(tmp_path, brut):
    valeurs = colonne(brut, "couleur")["valeurs"]
    valeurs.append(dict(valeurs[0]) | {"libelle": "Autre libellé"})
    refusee(tmp_path, brut, "code « .+ » en double")


def test_libelle_en_double_refuse(tmp_path, brut):
    valeurs = colonne(brut, "couleur")["valeurs"]
    valeurs.append({"code": "nouveau_code", "libelle": valeurs[0]["libelle"].upper()})
    refusee(tmp_path, brut, "libellé .+ en double")


# --- types et sources connus ----------------------------------------------


@pytest.mark.parametrize("type_", ["date", "booleen", "", None])
def test_type_inconnu_refuse(tmp_path, brut, type_):
    colonne(brut, "cuvee")["type"] = type_
    refusee(tmp_path, brut, "type .+ inconnu")


@pytest.mark.parametrize("source", ["ocr", "humain", "", None])
def test_source_inconnue_refusee(tmp_path, brut, source):
    colonne(brut, "cuvee")["source"] = source
    refusee(tmp_path, brut, "source .+ inconnue")


def test_cle_de_colonne_inconnue_refusee(tmp_path, brut):
    """Une faute de frappe ne doit pas passer pour un champ ignoré."""
    colonne(brut, "cuvee")["descripton"] = "faute de frappe"
    refusee(tmp_path, brut, "clé inconnue « descripton »")


def test_cle_racine_inconnue_refusee(tmp_path, brut):
    brut["regroupment_export"] = []
    refusee(tmp_path, brut, "clé inconnue « regroupment_export »")


def test_liste_sans_valeurs_refusee(tmp_path, brut):
    del colonne(brut, "couleur")["valeurs"]
    refusee(tmp_path, brut, "exige « valeurs »")


def test_valeurs_sur_un_texte_refusees(tmp_path, brut):
    colonne(brut, "cuvee")["valeurs"] = [{"code": "x", "libelle": "X"}]
    refusee(tmp_path, brut, "n'a de sens que pour le type liste")


@pytest.mark.parametrize("version", ["1", 0, -2, True, None, 1.5])
def test_version_invalide_refusee(tmp_path, brut, version):
    brut["version"] = version
    refusee(tmp_path, brut, "« version » : entier")


def test_cle_mal_formee_refusee(tmp_path, brut):
    colonne(brut, "cuvee")["cle"] = "Cuvée climat"
    refusee(tmp_path, brut, "identifiant en minuscules")


def test_json_illisible_refuse(tmp_path):
    with pytest.raises(ConfigInvalide, match=r"JSON illisible.*abîmé \(ligne"):
        charger_config(ecrire(tmp_path, '{"maison": "X",, }'))


def test_config_sans_colonne_refusee(tmp_path, brut):
    brut["colonnes"] = []
    refusee(tmp_path, brut, "« colonnes » : liste non vide")


def test_toutes_les_erreurs_sont_rapportees_ensemble(tmp_path, brut):
    """Une seule exécution doit tout dire, pas une erreur à la fois."""
    colonne(brut, "cuvee")["type"] = "date"
    colonne(brut, "domaine")["source"] = "ocr"
    brut["version"] = "un"
    with pytest.raises(ConfigInvalide) as capture:
        charger_config(ecrire(tmp_path, brut))
    message = str(capture.value)
    assert "config invalide (3)" in message
    assert "cuvee" in message and "domaine" in message and "version" in message


def test_fichier_absent():
    with pytest.raises(FileNotFoundError):
        charger_config(CONFIG_TEST.with_name("absente.json"))


# --- cohérence avec ce que le pipeline sait faire -------------------------


def test_colonne_systeme_inconnue_refusee(tmp_path, brut):
    """L'outil ne saurait pas la calculer : ce serait une colonne vide inexpliquée."""
    brut["colonnes"].append({"cle": "date_vente", "nom": "Date", "type": "texte", "source": "systeme"})
    refusee(tmp_path, brut, "ne sait pas calculer")


def test_quantite_doit_rester_saisie_par_l_expert(tmp_path, brut):
    colonne(brut, "quantite")["source"] = "modele"
    refusee(tmp_path, brut, "saisie par l'expert")


@pytest.mark.parametrize("cle", ["id", "a_verifier", "champs_a_verifier", "couleur_source", "photos_meme_bouteille"])
def test_le_modele_ne_peut_pas_remplir_un_champ_du_pipeline(tmp_path, brut, cle):
    brut["colonnes"].append({"cle": cle, "nom": f"En-tête {cle}", "type": "texte", "source": "modele"})
    refusee(tmp_path, brut, "réservé au pipeline|calculée par l'outil")


def test_une_config_ne_change_pas_la_nature_d_un_champ_v0(tmp_path, brut):
    """La couleur reste une liste : une config ne peut pas en faire du texte libre."""
    col = colonne(brut, "couleur")
    col["type"] = "texte"
    del col["valeurs"]
    refusee(tmp_path, brut, "champ liste du contrat Bouteille")


def test_colonne_expert_sur_un_champ_extrait_refusee(tmp_path, brut):
    colonne(brut, "cuvee")["source"] = "expert"
    refusee(tmp_path, brut, "ambigu qui remplit quoi")


# --- noyau canonique (decisions.md 0021) -----------------------------------


def test_canonique_hors_noyau_refuse(tmp_path, brut):
    colonne(brut, "cuvee")["canonique"] = True
    refusee(tmp_path, brut, "noyau canonique")


def test_champ_du_noyau_sans_marque_canonique_refuse(tmp_path, brut):
    del colonne(brut, "millesime")["canonique"]
    refusee(tmp_path, brut, "ajouter \"canonique\": true")


def test_le_noyau_n_a_pas_a_etre_affiche(tmp_path, brut):
    """« même si une config ne l'affiche pas » : retirer la colonne est permis."""
    brut["colonnes"] = [c for c in brut["colonnes"] if c["cle"] != "format"]
    brut["regroupement_export"] = [c for c in brut["regroupement_export"] if c != "format"]
    config = charger_config(ecrire(tmp_path, brut))
    assert config.colonne("format") is None


# --- regroupement -----------------------------------------------------------


def test_regroupement_sur_colonne_inexistante_refuse(tmp_path, brut):
    brut["regroupement_export"].append("region_inexistante")
    refusee(tmp_path, brut, "aucune colonne de clé « region_inexistante »")


def test_regroupement_sur_colonne_expert_accepte_et_sur_colonne_systeme_refuse(tmp_path, brut):
    """decisions.md 0160 : deux lots différents ne doivent jamais fusionner ; une
    colonne calculée par l'outil ne décrit pas la bouteille."""
    brut["regroupement_export"].append("estimation")
    assert "estimation" in charger_config(ecrire(tmp_path, json.dumps(brut, ensure_ascii=False))).regroupement_export
    brut["regroupement_export"].append("a_verifier")
    refusee(tmp_path, brut, "« a_verifier » est calculée par l'outil")


# --- vocabulaire --------------------------------------------------------------


def test_un_libelle_se_decode_en_code_casse_et_accents_compris(tmp_path, brut):
    valeur = colonne(brut, "couleur")["valeurs"][0]
    valeur["libelle"] = "Libellé Accentué"
    config = charger_config(ecrire(tmp_path, brut))
    couleur = config.colonne("couleur")
    assert couleur.code_depuis("LIBELLE ACCENTUE") == valeur["code"]
    assert couleur.code_depuis(valeur["code"]) == valeur["code"]
    assert couleur.code_depuis("valeur absente de la liste") is None


# --- few-shot dans la config (decisions.md 0053) -----------------------------


def test_un_exemple_dans_une_description_est_signale(tmp_path, brut):
    colonne(brut, "cuvee")["description"] = "Nom de la cuvée, par exemple « Les Clos »."
    config = charger_config(ecrire(tmp_path, brut))
    assert any("« cuvee »" in a and "few-shot" in a for a in config.avertissements)


def test_un_exemple_dans_une_colonne_expert_n_est_pas_signale(tmp_path, brut):
    """Jamais envoyée au modèle : aucun risque de few-shot."""
    colonne(brut, "estimation")["description"] = "Par exemple « 800-1000 »."
    config = charger_config(ecrire(tmp_path, brut))
    assert not any("« estimation »" in a for a in config.avertissements)


def test_une_description_sans_exemple_n_est_pas_signalee(tmp_path, brut):
    for col in brut["colonnes"]:
        col["description"] = "Description neutre."
        col.pop("regle", None)
        for valeur in col.get("valeurs", []):
            valeur["description"] = "Définition neutre."
    config = charger_config(ecrire(tmp_path, brut))
    assert config.avertissements == ()
