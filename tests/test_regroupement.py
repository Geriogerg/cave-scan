"""Une ligne = une bouteille ; regroupement à l'export seulement (guide, étape 4.3).

Critère d'acceptation : 5 bouteilles identiques en bon état + 1 identique
mais d'état différent = 2 lignes, quantités 5 et 1.
Les valeurs sont lues dans maison_test.json, jamais figées ici.
"""

from __future__ import annotations

import json

import pytest
from openpyxl import load_workbook

from src.config.maison import COLONNE_QUANTITE, charger_config
from src.export.excel_writer import ecrire_excel, regrouper
from src.extract.schema import NATURE_DES_CHAMPS, NON_DETERMINABLE, Bouteille
from tests.conftest import RACINE

CONFIG_TEST = RACINE / "config" / "maisons" / "maison_test.json"


@pytest.fixture
def config():
    return charger_config(CONFIG_TEST)


def poser(bouteille, colonne, valeur):
    if colonne.cle in NATURE_DES_CHAMPS:
        setattr(bouteille, colonne.cle, valeur)
    else:
        bouteille.valeurs_maison[colonne.cle] = valeur


def complete(config, identifiant, **valeurs):
    """Une bouteille propre (rien à relire), éventuellement surchargée par clé."""
    bouteille = Bouteille(id=identifiant)
    for colonne in config.colonnes_modele:
        if colonne.cle in valeurs:
            poser(bouteille, colonne, valeurs[colonne.cle])
        elif colonne.type == "liste":
            poser(bouteille, colonne, colonne.codes[0])
        elif colonne.type == "nombre":
            poser(bouteille, colonne, 1)
        else:
            poser(bouteille, colonne, f"Texte lu pour {colonne.cle}")
    return bouteille


def cle_d_etat(config):
    """La clé d'état : une clé de regroupement de type liste PROPRE à la maison
    (pas un champ v0), avec au moins deux valeurs réelles."""
    for cle in config.regroupement_export:
        colonne = config.colonne(cle)
        if colonne.type == "liste" and cle not in NATURE_DES_CHAMPS and len(colonne.codes) >= 3:
            return colonne  # 2 codes réels + non_determinable
    pytest.skip("la config de test n'a pas de clé d'état de type liste")


def abstention(colonne):
    return {"liste": NON_DETERMINABLE, "texte": "non_lisible", "nombre": None}[colonne.type]


def exporter(tmp_path, bouteilles, config):
    chemin = ecrire_excel(bouteilles, config, tmp_path / "listing.xlsx")
    return load_workbook(chemin).active


def colonne_xlsx(feuille, config, cle):
    index = [c.cle for c in config.colonnes].index(cle) + 1
    return [feuille.cell(row=ligne, column=index).value for ligne in range(2, feuille.max_row + 1)]


# --- le critère d'acceptation -------------------------------------------------


def test_regroupement_5_plus_1(tmp_path, config):
    etat = cle_d_etat(config)
    bon, abime = etat.codes[0], etat.codes[1]
    bouteilles = [complete(config, f"B-{i}", **{etat.cle: bon}) for i in range(5)]
    bouteilles.append(complete(config, "B-5", **{etat.cle: abime}))

    feuille = exporter(tmp_path, bouteilles, config)

    assert feuille.max_row == 3  # en-tête + 2 lignes
    assert colonne_xlsx(feuille, config, COLONNE_QUANTITE) == [5, 1]
    assert colonne_xlsx(feuille, config, etat.cle) == [etat.libelle(bon), etat.libelle(abime)]
    assert colonne_xlsx(feuille, config, "id") == ["B-0, B-1, B-2, B-3, B-4", "B-5"]


def test_en_interne_une_ligne_reste_une_bouteille(config):
    """Le regroupement ne touche que l'export : la liste de bouteilles est intacte."""
    bouteilles = [complete(config, f"B-{i}") for i in range(3)]
    groupes = regrouper(bouteilles, config)
    assert len(groupes) == 1
    assert len(bouteilles) == 3
    assert all(bouteille.quantite == 1 for bouteille in bouteilles)


# --- quand on ne fusionne PAS ------------------------------------------------------


def test_une_cle_differente_empeche_la_fusion(config):
    cle = config.colonne(config.regroupement_export[0])
    autre = cle.codes[1] if cle.type == "liste" else "Autre valeur"
    groupes = regrouper([complete(config, "B-1"), complete(config, "B-2", **{cle.cle: autre})], config)
    assert len(groupes) == 2


def test_une_abstention_sur_une_cle_empeche_la_fusion(config):
    """« Illisible » ne veut pas dire « identique » : on ne fusionne pas sur un inconnu."""
    for cle in config.regroupement_export:
        colonne = config.colonne(cle)
        bouteilles = [complete(config, f"B-{i}", **{cle: abstention(colonne)}) for i in range(2)]
        assert len(regrouper(bouteilles, config)) == 2, cle


def test_une_bouteille_a_relire_garde_sa_ligne(tmp_path, config):
    """Fusionnée, son abstention disparaîtrait derrière la valeur des autres."""
    hors_cle = next(
        c for c in config.colonnes_modele if c.cle not in config.regroupement_export
    )
    propre = complete(config, "B-1")
    a_relire = complete(config, "B-2", **{hors_cle.cle: abstention(hors_cle)})
    assert len(regrouper([propre, a_relire], config)) == 2


def test_l_egalite_est_stricte_sans_pliage(config):
    """Plier casse et accents serait déjà normaliser (decisions.md 0007)."""
    texte = next(
        config.colonne(c) for c in config.regroupement_export if config.colonne(c).type == "texte"
    )
    groupes = regrouper(
        [complete(config, "B-1", **{texte.cle: "Domaine Fèvre"}), complete(config, "B-2", **{texte.cle: "DOMAINE FEVRE"})],
        config,
    )
    assert len(groupes) == 2


def test_sans_cles_de_regroupement_une_ligne_par_bouteille(tmp_path):
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["regroupement_export"] = []
    chemin = tmp_path / "sans_regroupement.json"
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    config = charger_config(chemin)
    assert len(regrouper([complete(config, f"B-{i}") for i in range(4)], config)) == 4


# --- ce que montre une ligne fusionnée ----------------------------------------------


def test_les_quantites_saisies_par_l_expert_s_additionnent(tmp_path, config):
    deux, trois = complete(config, "B-1"), complete(config, "B-2")
    deux.quantite, trois.quantite = 2, 3
    feuille = exporter(tmp_path, [deux, trois], config)
    assert colonne_xlsx(feuille, config, COLONNE_QUANTITE) == [5]


def test_une_colonne_hors_cle_qui_differe_garde_toutes_ses_valeurs(tmp_path, config):
    """Un regroupement ne fait rien disparaître."""
    hors_cle = next(
        c for c in config.colonnes_modele
        if c.cle not in config.regroupement_export and c.type == "texte"
    )
    a = complete(config, "B-1", **{hors_cle.cle: "Première description."})
    b = complete(config, "B-2", **{hors_cle.cle: "Seconde description."})
    feuille = exporter(tmp_path, [a, b], config)
    assert colonne_xlsx(feuille, config, hors_cle.cle) == ["Première description. / Seconde description."]


def test_l_ordre_de_premiere_apparition_est_conserve(config):
    cle = config.colonne(config.regroupement_export[0])
    autre = cle.codes[1] if cle.type == "liste" else "Autre valeur"
    x1, y1, x2 = complete(config, "X1"), complete(config, "Y1", **{cle.cle: autre}), complete(config, "X2")
    groupes = regrouper([x1, y1, x2], config)
    assert [[b.id for b in g] for g in groupes] == [["X1", "X2"], ["Y1"]]


def test_les_doutes_des_bouteilles_regroupees_sont_reunis(tmp_path, config):
    best_effort = [c.cle for c in config.colonnes_best_effort]
    a, b = complete(config, "B-1"), complete(config, "B-2")
    a.champs_a_verifier = list(best_effort)
    b.champs_a_verifier = list(reversed(best_effort))
    feuille = exporter(tmp_path, [a, b], config)
    assert colonne_xlsx(feuille, config, "a_verifier") == [", ".join(best_effort)]
