"""Relecture : la correction ne touche jamais l'extraction, la saisie est validée
selon son type, la validation suit les règles de statut.

Critères d'acceptation du guide : une correction ne modifie jamais
l'extraction ; `valeurs_courantes` renvoie la dernière correction ;
l'historique garde toutes les corrections ; `corriger` refuse un champ inconnu
et une valeur hors liste.
Point 1 de la validation (saisie par type, estimation saisie par l'expert) et
point 7 (statuts d'inventaire).
"""

from __future__ import annotations

import json

import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.config.maison import charger_config
from src.donnees.base import creer_moteur
from src.donnees.modeles import Correction, Extraction
from src.export.excel_writer import ecrire_excel
from src.extract.fixture_extract import FixtureExtractor
from src.extract.schema import NON_DETERMINABLE
from src.services.extraction import extraire_bouteille, extraire_inventaire
from src.services.inventaires import charger_inventaire, config_figee, creer_inventaire
from src.services.relecture import (
    CorrectionRefusee,
    ValidationRefusee,
    corriger,
    valeurs_courantes,
    valeurs_modele,
    valider,
)
from tests.conftest import CONFIG_TEST, FIXTURES
from tests.test_extraction import ExtracteurScenario


@pytest.fixture
def inventaire_id(session, nom_maison, dossier_photos, stockage):
    """Inventaire de 6 bouteilles extraites sur les fixtures, config de test."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))
    extracteur = FixtureExtractor(charges, charger_config(CONFIG_TEST))
    extraire_inventaire(session, cree.inventaire_id, extracteur, stockage)
    return cree.inventaire_id


def bouteille(session, inventaire_id, rang=0):
    return charger_inventaire(session, inventaire_id).bouteilles[rang]


def liste_de_maison(session, inventaire_id):
    return next(c for c in config_figee(charger_inventaire(session, inventaire_id)).colonnes
                if c.type == "liste" and c.envoyee_au_modele)


def photographie_des_extractions(session):
    """Le contenu exact de la table extraction, lu en SQL brut par une autre connexion."""
    moteur = create_engine(str(session.get_bind().url))
    with moteur.connect() as connexion:
        lignes = connexion.exec_driver_sql("SELECT * FROM extraction ORDER BY id").fetchall()
    moteur.dispose()
    return [tuple(ligne) for ligne in lignes]


# --- une correction ne modifie jamais l'extraction (critère n°1 du guide) ------------------


def test_une_correction_ne_modifie_jamais_l_extraction(session, inventaire_id):
    """L'erreur la plus grave de la session : l'écrasement de la sortie du modèle."""
    avant = photographie_des_extractions(session)
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, "millesime", "1999", "expert")
    corriger(session, cible.id, "domaine", "Autre domaine", "expert")
    corriger(session, cible.id, "quantite", 3, "expert")
    assert photographie_des_extractions(session) == avant


def test_la_valeur_du_modele_reste_lisible_apres_correction(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    lu = valeurs_modele(session, cible.id).millesime
    corriger(session, cible.id, "millesime", "1999", "expert")
    assert valeurs_modele(session, cible.id).millesime == lu
    assert valeurs_courantes(session, cible.id).millesime == "1999"


def test_valeurs_courantes_renvoie_la_derniere_correction(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, "millesime", "2015", "expert A")
    corriger(session, cible.id, "millesime", "2016", "expert B")
    assert valeurs_courantes(session, cible.id).millesime == "2016"


def test_l_historique_garde_toutes_les_corrections(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    lu = valeurs_modele(session, cible.id).millesime
    corriger(session, cible.id, "millesime", "2015", "expert A")
    corriger(session, cible.id, "millesime", "2016", "expert B")
    historique = session.scalars(
        select(Correction).where(Correction.bouteille_id == cible.id, Correction.champ == "millesime")
        .order_by(Correction.id)
    ).all()
    assert [(c.ancienne_valeur, c.nouvelle_valeur, c.auteur) for c in historique] == [
        (lu, "2015", "expert A"), ("2015", "2016", "expert B"),
    ]
    assert all(c.cree_le is not None for c in historique)


# --- corriger refuse (critère du guide) ---------------------------------------------------


def test_corriger_refuse_un_champ_inconnu(session, inventaire_id):
    with pytest.raises(CorrectionRefusee, match="Champ inconnu.+Champs corrigeables"):
        corriger(session, bouteille(session, inventaire_id).id, "prix_de_reserve", "500", "expert")


def test_corriger_refuse_une_valeur_hors_liste(session, inventaire_id):
    liste = liste_de_maison(session, inventaire_id)
    with pytest.raises(CorrectionRefusee, match="n'est pas une valeur de la liste"):
        corriger(session, bouteille(session, inventaire_id).id, liste.cle, "valeur inventée", "expert")


@pytest.mark.parametrize("champ", ["id", "a_verifier", "statut", "champs_a_verifier", "couleur_source"])
def test_corriger_refuse_ce_que_calcule_l_outil(session, inventaire_id, champ):
    with pytest.raises(CorrectionRefusee):
        corriger(session, bouteille(session, inventaire_id).id, champ, "x", "expert")


def test_une_correction_a_toujours_un_auteur(session, inventaire_id):
    with pytest.raises(CorrectionRefusee, match="auteur"):
        corriger(session, bouteille(session, inventaire_id).id, "millesime", "2015", "  ")


def test_un_refus_n_ecrit_rien(session, inventaire_id):
    with pytest.raises(CorrectionRefusee):
        corriger(session, bouteille(session, inventaire_id).id, "quantite", 0, "expert")
    assert session.scalar(select(func.count()).select_from(Correction)) == 0


# --- point 1 : saisie validée selon le type de la colonne ----------------------------------


@pytest.mark.parametrize("saisie, attendu", [(5, 5), ("3", 3), (" 12 ", 12)])
def test_quantite_entier_superieur_ou_egal_a_un(session, inventaire_id, saisie, attendu):
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, "quantite", saisie, "expert")
    assert cible.quantite == attendu
    assert valeurs_courantes(session, cible.id).quantite == attendu


@pytest.mark.parametrize("saisie", [0, -1, 2.5, "cinq", "", True, None])
def test_quantite_invalide_refusee(session, inventaire_id, saisie):
    with pytest.raises(CorrectionRefusee, match="Quantité invalide"):
        corriger(session, bouteille(session, inventaire_id).id, "quantite", saisie, "expert")


def test_liste_code_connu(session, inventaire_id):
    liste = liste_de_maison(session, inventaire_id)
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, liste.cle, liste.codes[1], "expert")
    assert getattr(valeurs_courantes(session, cible.id), liste.cle) == liste.codes[1]


def test_liste_un_libelle_est_ramene_a_son_code(session, inventaire_id):
    """On stocke toujours un code connu, même si l'expert tape le libellé."""
    liste = liste_de_maison(session, inventaire_id)
    valeur = liste.valeurs[1]
    correction = corriger(session, bouteille(session, inventaire_id).id, liste.cle, valeur.libelle.upper(), "expert")
    assert correction.nouvelle_valeur == valeur.code


def test_liste_non_determinable_est_une_saisie_valide(session, inventaire_id):
    liste = liste_de_maison(session, inventaire_id)
    correction = corriger(session, bouteille(session, inventaire_id).id, liste.cle, NON_DETERMINABLE, "expert")
    assert correction.nouvelle_valeur == NON_DETERMINABLE


def test_texte_libre(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, "cuvee", "Clos Saint-Jacques, « vieilles vignes »", "expert")
    assert valeurs_courantes(session, cible.id).cuvee == "Clos Saint-Jacques, « vieilles vignes »"


@pytest.mark.parametrize("saisie, attendu", [("13,5", 13.5), ("14", 14), (12.5, 12.5)])
def test_nombre(session, inventaire_id, saisie, attendu):
    """Un champ v0 extrait mais non affiché reste corrigeable, avec son type."""
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, "degre", saisie, "expert")
    assert valeurs_courantes(session, cible.id).degre == attendu


def test_nombre_invalide_refuse(session, inventaire_id):
    with pytest.raises(CorrectionRefusee, match="attend un nombre"):
        corriger(session, bouteille(session, inventaire_id).id, "degre", "beaucoup", "expert")


def test_l_estimation_saisie_par_l_expert_apparait_a_l_export(session, inventaire_id, tmp_path):
    """Point 1 : l'expert saisit l'estimation (CLAUDE.md : lui seul)."""
    inventaire = charger_inventaire(session, inventaire_id)
    config = config_figee(inventaire)
    estimation = next(c for c in config.colonnes if c.source == "expert" and c.cle != "quantite")
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, estimation.cle, "800-1000", "expert")

    chemin = ecrire_excel(
        [valeurs_courantes(session, b.id) for b in inventaire.bouteilles], config, tmp_path / "e.xlsx"
    )
    feuille = load_workbook(chemin).active
    index = [c.cle for c in config.colonnes].index(estimation.cle) + 1
    assert feuille.cell(row=2, column=index).value == "800-1000"
    assert all(feuille.cell(row=r, column=index).value is None for r in range(3, feuille.max_row + 1))


def test_le_modele_ne_peut_toujours_pas_remplir_l_estimation(session, nom_maison, dossier_photos, stockage):
    """Même si sa réponse contient une estimation, elle n'atteint ni les valeurs
    ni l'export : seules les colonnes lues sont remplies par le modèle."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage, limite=1)
    config = charger_config(CONFIG_TEST)
    experts = [c.cle for c in config.colonnes if c.source == "expert" and c.cle != "quantite"]
    charge = {"appellation": "Pommard"} | {cle: "800-1000" for cle in experts}
    extraire_inventaire(session, cree.inventaire_id, FixtureExtractor([charge], config), stockage)

    valeurs = valeurs_courantes(session, charger_inventaire(session, cree.inventaire_id).bouteilles[0].id)
    for cle in experts:
        assert cle not in valeurs.valeurs_maison


# --- point 7 : statuts de bouteille et d'inventaire ----------------------------------------


def valider_tout(session, inventaire_id, sauf=()):
    for b in charger_inventaire(session, inventaire_id).bouteilles:
        if b.position not in sauf:
            valider(session, b.id, "expert")


def test_l_inventaire_passe_a_valide_quand_toutes_ses_bouteilles_le_sont(session, inventaire_id):
    inventaire = charger_inventaire(session, inventaire_id)
    valider_tout(session, inventaire_id, sauf={6})
    assert inventaire.statut == "ouvert"
    valider(session, inventaire.bouteilles[5].id, "expert")
    assert inventaire.statut == "valide"


def test_une_correction_sur_une_bouteille_validee_la_remet_a_relire(session, inventaire_id):
    """Point 7, règle 1 : bouteille à relire, inventaire de nouveau ouvert."""
    valider_tout(session, inventaire_id)
    inventaire = charger_inventaire(session, inventaire_id)
    assert inventaire.statut == "valide"

    cible = inventaire.bouteilles[2]
    corriger(session, cible.id, "millesime", "1990", "expert B")

    assert cible.statut == "extraite"  # « à relire »
    assert inventaire.statut == "ouvert"
    statuts = [(c.ancienne_valeur, c.nouvelle_valeur, c.auteur) for c in cible.corrections if c.champ == "statut"]
    assert statuts == [("extraite", "validee", "expert"), ("validee", "extraite", "expert B")]


def test_une_bouteille_en_erreur_se_valide_en_saisie_manuelle_une_fois_ses_champs_obligatoires_saisis(
    session, nom_maison, dossier_photos, stockage
):
    """Point 7, règle 2, revu en session 6 (decisions.md 0169) : une bouteille
    dont l'analyse a échoué ne bloque plus l'inventaire, mais elle ne se valide
    qu'avec ses champs obligatoires saisis à la main — et c'est tracé."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario({4: "passagere"}), stockage)
    inventaire = charger_inventaire(session, cree.inventaire_id)
    en_erreur = inventaire.bouteilles[3]
    assert en_erreur.statut == "erreur"

    valider_tout(session, cree.inventaire_id, sauf={4})
    with pytest.raises(ValidationRefusee, match="Château, Appellation, Millésime, Format"):
        valider(session, en_erreur.id, "expert")
    assert inventaire.statut == "ouvert"

    # Une partie seulement : toujours refusée, avec ce qui manque encore.
    corriger(session, en_erreur.id, "millesime", "2001", "expert")
    with pytest.raises(ValidationRefusee, match="remplissez d'abord : Domaine.*Format"):
        valider(session, en_erreur.id, "expert")
    assert inventaire.statut == "ouvert"

    for champ, valeur in (("domaine", "Domaine X"), ("appellation", "Pommard"), ("format", "bouteille")):
        corriger(session, en_erreur.id, champ, valeur, "expert")
    valider(session, en_erreur.id, "expert")
    assert en_erreur.statut == "validee" and inventaire.statut == "valide"
    trace = [c for c in en_erreur.corrections if c.champ == "statut"][-1]
    assert (trace.ancienne_valeur, trace.nouvelle_valeur) == ("erreur", "validee")  # « saisie manuelle »

    # Modifiée ensuite, elle redevient « en erreur » (aucune analyse réussie), pas « extraite ».
    corriger(session, en_erreur.id, "millesime", "2002", "expert")
    assert en_erreur.statut == "erreur" and inventaire.statut == "ouvert"


def test_on_ne_valide_pas_une_bouteille_pas_encore_extraite(session, nom_maison, dossier_photos, stockage):
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    with pytest.raises(ValidationRefusee, match="pas encore lue"):
        valider(session, charger_inventaire(session, cree.inventaire_id).bouteilles[0].id, "expert")


def test_valider_deux_fois_ne_trace_qu_une_validation(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    valider(session, cible.id, "expert")
    valider(session, cible.id, "expert")
    assert len([c for c in cible.corrections if c.champ == "statut"]) == 1


def test_une_relance_forcee_d_une_bouteille_validee_la_remet_a_relire(session, inventaire_id, stockage):
    valider_tout(session, inventaire_id)
    inventaire = charger_inventaire(session, inventaire_id)
    cible = inventaire.bouteilles[0]
    extraire_bouteille(session, cible.id, ExtracteurScenario(), stockage, forcer=True)
    assert cible.statut == "extraite"
    assert inventaire.statut == "ouvert"
    assert cible.corrections[-1].auteur.startswith("relance forcée")


def test_les_corrections_survivent_a_une_relance(session, inventaire_id, stockage):
    """Une nouvelle extraction ne fait pas disparaître le travail de l'expert."""
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, "millesime", "1999", "expert")
    extraire_bouteille(session, cible.id, ExtracteurScenario(), stockage, forcer=True)
    assert valeurs_courantes(session, cible.id).millesime == "1999"
    assert session.scalar(select(func.count()).select_from(Extraction).where(Extraction.bouteille_id == cible.id)) == 2


# --- relecture depuis la base : rien ne se perd (remplace les tests du journal) -------------


def test_un_code_propre_a_la_maison_n_est_jamais_perdu_a_la_relecture(
    session, nom_maison, dossier_photos, stockage
):
    """Successeur de « le journal se relit sans rien perdre » : relue depuis la
    base, par une AUTRE connexion, la sortie du modèle garde les codes de la
    maison — « champagne » n'est pas une couleur v0, il ne doit pas être rabattu
    sur l'enum v0 — et une correction vers un autre code de la maison aussi."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    cible = bouteille(session, cree.inventaire_id)
    charge = {"couleur": "champagne", "etat_etiquette": "legerement_marquee", "domaine": "Maison X"}
    extraire_bouteille(session, cible.id, FixtureExtractor([charge], charger_config(CONFIG_TEST)), stockage)
    corriger(session, cible.id, "etat_etiquette", "tachee", "expert")

    autre_moteur = creer_moteur(str(session.get_bind().url))
    with Session(autre_moteur) as autre:
        modele = valeurs_modele(autre, cible.id)
        courantes = valeurs_courantes(autre, cible.id)
    autre_moteur.dispose()

    assert modele.couleur == "champagne"
    assert modele.valeurs_maison["etat_etiquette"] == "legerement_marquee"
    assert courantes.couleur == "champagne"
    assert courantes.valeurs_maison["etat_etiquette"] == "tachee"
    assert courantes.quantite == 1 and courantes.id == cible.identifiant
