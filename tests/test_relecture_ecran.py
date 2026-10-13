"""Services de l'écran de relecture (guide de session 5, §8, « tests automatisés »).

Hors ligne, sans modèle : les extractions viennent des fixtures, la réanalyse
passe par la file d'attente et un faux modèle. Chaque test nomme le critère du
guide qu'il vérifie.
"""

from __future__ import annotations

import json

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from src.config.maison import charger_config
from src.donnees.modeles import Correction, EnregistrementImmuable, EvenementBouteille, Extraction
from src.extract.fixture_extract import FixtureExtractor
from src.services.cas_particuliers import (
    ActionRefusee,
    evenements_de,
    lever_signalement,
    reanalyser,
    separer,
    signaler_paire,
)
from src.services.consultation import (
    etats_de_relecture,
    fiche_de_relecture,
    prochaine_a_relire,
    recapitulatif,
    voisines,
)
from src.services.extraction import extraire_inventaire, traiter_reservee
from src.services.file_attente import reserver_bouteille
from src.services.inventaires import charger_inventaire, creer_inventaire
from src.services.pilotage import annuler
from src.services.relecture import (
    CorrectionRefusee,
    ModificationConcurrente,
    SaisiesRefusees,
    TEMPS_RELECTURE_MAX_MS,
    ValidationRefusee,
    corriger,
    corriger_en_relecture,
    revenir_a_la_valeur_du_modele,
    valeurs_courantes,
    valeurs_courantes_de_l_inventaire,
    valeurs_modele,
    valider,
    valider_en_relecture,
    valider_inventaire,
    version_de,
)
from src.services.restitution import exporter, stats_inventaire
from tests.conftest import CONFIG_TEST, FIXTURES
from tests.test_extraction import ExtracteurScenario
from tests.test_relecture import photographie_des_extractions

EXPERT = "Expert test"

# Une lecture complète, sans aucun doute : la bouteille n'est pas « à relire »,
# l'export peut donc la fusionner avec une bouteille identique (decisions.md 0140).
PROPRE = {
    "domaine": "Domaine Propre",
    "appellation": "Pommard",
    "cuvee": "Les Rugiens",
    "millesime": "2015",
    "couleur": "rouge",
    "couleur_source": "observee",
    "format": "bouteille",
    "niveau": "haute_epaule",
    "etat_etiquette": "parfait",
    "etat_capsule": "intacte",
    "description_etat": "Étiquette propre, capsule intacte.",
    "champs_a_verifier": [],
}


@pytest.fixture
def inventaire_id(session, nom_maison, dossier_photos, stockage):
    """6 bouteilles extraites sur les fixtures habituelles (doutes compris)."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))
    extraire_inventaire(session, cree.inventaire_id, FixtureExtractor(charges, charger_config(CONFIG_TEST)), stockage)
    return cree.inventaire_id


@pytest.fixture
def propre(session, nom_maison, dossier_photos, stockage):
    """6 bouteilles lues sans aucun doute, de domaines différents."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Propre", stockage)
    charges = [dict(PROPRE, domaine=f"Domaine {rang}") for rang in range(1, 7)]
    extraire_inventaire(session, cree.inventaire_id, FixtureExtractor(charges, charger_config(CONFIG_TEST)), stockage)
    return cree.inventaire_id


def bouteille(session, inventaire_id, rang=0):
    return charger_inventaire(session, inventaire_id).bouteilles[rang]


def saisies_affichees(session, inventaire_id, bouteille_id):
    """Ce que le formulaire de l'écran envoie s'il n'a pas été touché."""
    return {c.cle: c.saisie for c in fiche_de_relecture(session, inventaire_id, bouteille_id).champs}


def lignes_export(session, inventaire_id, tmp_path):
    feuille = load_workbook(exporter(session, inventaire_id, tmp_path / "export.xlsx")).active
    entetes = [cellule.value for cellule in feuille[1]]
    return [dict(zip(entetes, [c.value for c in ligne])) for ligne in feuille.iter_rows(min_row=2)]


# --- enregistrement immédiat (critère : « enregistrée sans action supplémentaire ») -----


def test_une_saisie_est_enregistree_et_apparait_dans_l_historique_sans_toucher_l_extraction(session, inventaire_id):
    avant = photographie_des_extractions(session)
    cible = bouteille(session, inventaire_id)
    version = version_de(session, cible.id)

    correction = corriger_en_relecture(session, cible.id, "millesime", "2001", EXPERT, version)

    assert correction is not None and correction.ancienne_valeur == "2018" and correction.nouvelle_valeur == "2001"
    assert valeurs_courantes(session, cible.id).millesime == "2001"
    assert valeurs_modele(session, cible.id).millesime == "2018"  # le modèle, intact
    historique = fiche_de_relecture(session, inventaire_id, cible.id).historique
    assert any("Millésime : 2018 → 2001" in ligne.texte and ligne.auteur == EXPERT for ligne in historique)
    assert photographie_des_extractions(session) == avant


def test_une_saisie_identique_n_ajoute_rien_a_l_historique(session, inventaire_id):
    cible = bouteille(session, inventaire_id, 1)  # Château Margaux, degré non lu
    assert corriger_en_relecture(session, cible.id, "domaine", "Château Margaux", EXPERT, None) is None
    corriger(session, cible.id, "degre", "13,5", EXPERT)
    assert corriger_en_relecture(session, cible.id, "degre", "13.5", EXPERT, None) is None  # même nombre
    assert [c.champ for c in cible.corrections] == ["degre"]


def test_valider_un_formulaire_intact_n_ecrit_aucune_correction(session, inventaire_id):
    """Les abstentions s'affichent vides (« à remplir ») : renvoyer le formulaire
    tel quel ne doit JAMAIS remplacer « non lisible » par une chaîne vide."""
    cible = bouteille(session, inventaire_id, 1)  # millésime et cuvée non lisibles
    valider_en_relecture(
        session, cible.id, EXPERT, saisies_affichees(session, inventaire_id, cible.id), version_de(session, cible.id)
    )
    assert cible.statut == "validee"
    assert [c.champ for c in cible.corrections] == ["statut"]
    assert valeurs_courantes(session, cible.id).millesime == "non_lisible"


def test_valider_enregistre_d_abord_ce_que_l_ecran_n_avait_pas_encore_enregistre(session, inventaire_id):
    """Une sortie de champ manquée ne perd rien : la validation l'enregistre."""
    cible = bouteille(session, inventaire_id, 1)
    saisies = saisies_affichees(session, inventaire_id, cible.id) | {"millesime": "2005", "quantite": "3"}
    valider_en_relecture(session, cible.id, EXPERT, saisies, version_de(session, cible.id))
    courantes = valeurs_courantes(session, cible.id)
    assert (courantes.millesime, courantes.quantite, cible.statut) == ("2005", 3, "validee")


# --- revenir à la valeur du modèle ----------------------------------------------------------


def test_revenir_a_la_valeur_du_modele_cree_une_correction_et_ne_supprime_rien(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, "millesime", "1999", EXPERT)
    revenir_a_la_valeur_du_modele(session, cible.id, "millesime", EXPERT)

    assert valeurs_courantes(session, cible.id).millesime == "2018"
    assert [(c.ancienne_valeur, c.nouvelle_valeur) for c in cible.corrections] == [("2018", "1999"), ("1999", "2018")]
    with pytest.raises(CorrectionRefusee, match="déjà la valeur lue"):
        revenir_a_la_valeur_du_modele(session, cible.id, "millesime", EXPERT)


def test_revenir_vers_une_abstention_ou_un_nombre_absent(session, inventaire_id):
    cible = bouteille(session, inventaire_id, 1)  # millésime non lisible, degré absent
    corriger(session, cible.id, "millesime", "2010", EXPERT)
    corriger(session, cible.id, "degre", "13", EXPERT)
    revenir_a_la_valeur_du_modele(session, cible.id, "millesime", EXPERT)
    revenir_a_la_valeur_du_modele(session, cible.id, "degre", EXPERT)
    courantes = valeurs_courantes(session, cible.id)
    assert courantes.millesime == "non_lisible" and courantes.degre is None


@pytest.mark.parametrize("champ", ["quantite", "estimation", "inconnu"])
def test_revenir_refuse_un_champ_sans_lecture_du_modele(session, inventaire_id, champ):
    with pytest.raises(CorrectionRefusee):
        revenir_a_la_valeur_du_modele(session, bouteille(session, inventaire_id).id, champ, EXPERT)


# --- saisies refusées : message clair, validation bloquée -----------------------------------


def test_une_valeur_hors_liste_ou_une_quantite_invalide_est_refusee_et_bloque_la_validation(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    with pytest.raises(CorrectionRefusee, match="« bleu » n'est pas une valeur de la liste « couleur »"):
        corriger_en_relecture(session, cible.id, "couleur", "bleu", EXPERT, None)
    with pytest.raises(CorrectionRefusee, match=r"Quantité invalide : « 0 » \(entier ≥ 1 attendu\)"):
        corriger_en_relecture(session, cible.id, "quantite", "0", EXPERT, None)

    saisies = saisies_affichees(session, inventaire_id, cible.id) | {"couleur": "bleu", "quantite": "0", "millesime": "2017"}
    with pytest.raises(SaisiesRefusees) as refus:
        valider_en_relecture(session, cible.id, EXPERT, saisies, version_de(session, cible.id))
    assert set(refus.value.refus) == {"couleur", "quantite"}
    assert "Bouteille non validée" in str(refus.value)
    assert cible.statut == "extraite"  # pas validée
    assert valeurs_courantes(session, cible.id).millesime == "2017"  # la saisie valide, elle, est gardée

    saisies |= {"couleur": "Blanc", "quantite": "2"}  # un libellé est ramené à son code
    valider_en_relecture(session, cible.id, EXPERT, saisies, version_de(session, cible.id))
    courantes = valeurs_courantes(session, cible.id)
    assert (cible.statut, courantes.couleur, courantes.quantite) == ("validee", "blanc", 2)


def test_modifier_une_bouteille_validee_la_remet_a_relire(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    valider(session, cible.id, EXPERT)
    corriger_en_relecture(session, cible.id, "cuvee", "Autre", EXPERT, version_de(session, cible.id))
    assert cible.statut == "extraite"
    assert charger_inventaire(session, inventaire_id).statut == "ouvert"


# --- modification concurrente ---------------------------------------------------------------


def test_l_avertissement_de_modification_concurrente_se_declenche(session, inventaire_id):
    """Deux onglets sur la même bouteille : le second n'écrase pas sans le savoir."""
    cible = bouteille(session, inventaire_id)
    vue_par_a = vue_par_b = version_de(session, cible.id)

    corriger_en_relecture(session, cible.id, "millesime", "2001", "Onglet B", vue_par_b)
    with pytest.raises(ModificationConcurrente) as alerte:
        corriger_en_relecture(session, cible.id, "millesime", "1990", "Onglet A", vue_par_a)
    assert "modifiée ailleurs" in str(alerte.value)
    assert any("Millésime" in changement and "2001" in changement and "Onglet B" in changement
               for changement in alerte.value.changements)
    assert valeurs_courantes(session, cible.id).millesime == "2001"  # rien écrit

    with pytest.raises(ModificationConcurrente):
        valider_en_relecture(session, cible.id, "Onglet A", {}, vue_par_a)
    assert cible.statut == "extraite"

    # « Enregistrer quand même » : l'historique garde les deux.
    corriger_en_relecture(session, cible.id, "millesime", "1990", "Onglet A", vue_par_a, forcer=True)
    assert [(c.nouvelle_valeur, c.auteur) for c in cible.corrections] == [("2001", "Onglet B"), ("1990", "Onglet A")]


def test_la_version_change_a_chaque_enregistrement(session, inventaire_id, stockage):
    cible = bouteille(session, inventaire_id)
    versions = [version_de(session, cible.id)]
    corriger(session, cible.id, "cuvee", "X", EXPERT)
    versions.append(version_de(session, cible.id))
    signaler_paire(session, cible.id, EXPERT)
    versions.append(version_de(session, cible.id))
    lever_signalement(session, cible.id, EXPERT)
    reanalyser(session, cible.id, EXPERT)
    versions.append(version_de(session, cible.id))
    traiter_reservee(session, reserver_bouteille(session, "w", inventaire_id), ExtracteurScenario(), stockage, "w")
    versions.append(version_de(session, cible.id))
    assert len(set(versions)) == len(versions)


# --- réanalyser -----------------------------------------------------------------------------


def test_reanalyser_conserve_l_ancienne_extraction_et_les_corrections_restent_prioritaires(session, inventaire_id, stockage):
    avant = photographie_des_extractions(session)
    cible = bouteille(session, inventaire_id)
    corriger(session, cible.id, "millesime", "1999", EXPERT)
    valider(session, cible.id, EXPERT)

    assert reanalyser(session, cible.id, EXPERT) is True
    assert cible.statut == "a_extraire"
    assert reanalyser(session, cible.id, EXPERT) is False  # déjà en attente
    # Le worker la reprend : seule cette bouteille est dans la file.
    reservee = reserver_bouteille(session, "w", inventaire_id)
    assert reservee == cible.id and reserver_bouteille(session, "w", inventaire_id) is None
    traiter_reservee(session, reservee, ExtracteurScenario(), stockage, "w")

    assert photographie_des_extractions(session)[: len(avant)] == avant  # l'ancienne, intacte
    assert session.scalar(select(func.count()).select_from(Extraction).where(Extraction.bouteille_id == cible.id)) == 2
    courantes = valeurs_courantes(session, cible.id)
    assert courantes.millesime == "1999"  # la correction l'emporte sur la nouvelle lecture
    assert courantes.domaine == "Domaine X"  # le reste vient de la nouvelle extraction
    assert cible.statut == "extraite"  # validée avant : à relire
    statuts = [(c.ancienne_valeur, c.nouvelle_valeur) for c in cible.corrections if c.champ == "statut"]
    assert statuts == [("extraite", "validee"), ("validee", "a_extraire")]
    assert [e.type for e in evenements_de(session, cible.id)] == ["reanalyse"]


def test_reanalyser_une_bouteille_en_erreur(session, nom_maison, dossier_photos, stockage):
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario({2: "passagere"}), stockage)
    en_erreur = bouteille(session, cree.inventaire_id, 1)
    assert en_erreur.statut == "erreur"
    fiche = fiche_de_relecture(session, cree.inventaire_id, en_erreur.id)
    assert fiche.erreur == "Le service d'analyse n'a pas répondu à temps (panne passagère)."
    assert "RateLimitError" not in fiche.erreur  # jamais le message technique brut

    reanalyser(session, en_erreur.id, EXPERT)
    traiter_reservee(session, reserver_bouteille(session, "w", cree.inventaire_id), ExtracteurScenario(), stockage, "w")
    assert en_erreur.statut == "extraite"


def test_reanalyser_refuse_si_l_analyse_de_l_inventaire_est_annulee(session, inventaire_id):
    annuler(session, inventaire_id)
    with pytest.raises(ActionRefusee, match="a été annulée : relancez-la depuis l'écran de suivi"):
        reanalyser(session, bouteille(session, inventaire_id).id, EXPERT)


# --- signaler un problème de photos (« Inverser les photos » a disparu avec les rôles, 0166) ---


def test_une_bouteille_signalee_ne_peut_pas_etre_validee(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    valider(session, cible.id, EXPERT)
    assert signaler_paire(session, cible.id, EXPERT, "contre-étiquette d'un autre vin") is True
    assert cible.statut == "extraite"  # elle n'est plus validée
    assert signaler_paire(session, cible.id, EXPERT) is False

    with pytest.raises(ValidationRefusee, match="problème de photos"):
        valider(session, cible.id, EXPERT)
    with pytest.raises(ValidationRefusee, match="problème de photos"):
        valider_en_relecture(session, cible.id, EXPERT, {}, version_de(session, cible.id))
    for autre in charger_inventaire(session, inventaire_id).bouteilles[1:]:
        valider(session, autre.id, EXPERT)
    with pytest.raises(ValidationRefusee, match=r"1 bouteille\(s\) avec un problème de photos signalé \(n°1\)"):
        valider_inventaire(session, inventaire_id, EXPERT)

    assert lever_signalement(session, cible.id, EXPERT) is True
    valider(session, cible.id, EXPERT)
    assert valider_inventaire(session, inventaire_id, EXPERT) == 6
    assert [e.type for e in evenements_de(session, cible.id)] == ["signalement_paire", "signalement_leve"]


# --- séparer ----------------------------------------------------------------------------------


def test_separer_cree_une_seconde_bouteille_liee_aux_memes_photos_et_l_export_produit_deux_lignes(session, propre, tmp_path):
    source = bouteille(session, propre, 1)
    corriger(session, source.id, "quantite", 6, EXPERT)
    corriger(session, source.id, "millesime", "2014", EXPERT)  # corrigé AVANT la séparation
    position = source.position

    nouvelle = separer(session, source.id, 1, EXPERT)

    assert nouvelle.groupe_id == source.groupe_id and nouvelle.photos == source.photos  # les mêmes photos
    assert nouvelle.separee_de_id == source.id and nouvelle.identifiant == f"{source.identifiant}-2"
    assert (source.quantite, nouvelle.quantite) == (5, 1)  # la somme est conservée
    inventaire = charger_inventaire(session, propre)
    assert [b.position for b in inventaire.bouteilles] == list(range(1, 8))
    assert inventaire.bouteilles[position].id == nouvelle.id  # juste après sa source
    assert valeurs_courantes(session, nouvelle.id).millesime == "2014"  # mêmes valeurs que la source
    assert session.scalar(select(func.count()).select_from(Extraction).where(Extraction.bouteille_id == nouvelle.id)) == 0

    # Identiques sur les colonnes de regroupement : l'écran prévient, l'export fusionne (0140).
    fiche = fiche_de_relecture(session, propre, nouvelle.id)
    assert fiche.fusionnee_avec == [source.identifiant] and "État étiquette" in fiche.regroupement
    lignes = [l for l in lignes_export(session, propre, tmp_path) if l["Domaine / Château"] == "Domaine 2"]
    assert len(lignes) == 1 and lignes[0]["Qté"] == 6

    # L'expert ajuste l'état de l'exemplaire abîmé : deux lignes.
    corriger(session, nouvelle.id, "etat_etiquette", "abimee", EXPERT)
    assert fiche_de_relecture(session, propre, nouvelle.id).fusionnee_avec == []
    lignes = [l for l in lignes_export(session, propre, tmp_path) if l["Domaine / Château"] == "Domaine 2"]
    assert [(l["Qté"], l["État étiquette"]) for l in lignes] == [(5, "Parfait"), (1, "Abîmée")]


def test_separer_refuse_ce_qui_ne_tient_pas(session, inventaire_id, nom_maison, dossier_photos, stockage):
    cible = bouteille(session, inventaire_id)
    with pytest.raises(ActionRefusee, match="Indiquez d'abord la quantité totale"):
        separer(session, cible.id, 1, EXPERT)  # quantité 1 : rien à séparer
    corriger(session, cible.id, "quantite", 3, EXPERT)
    with pytest.raises(ActionRefusee, match="on peut en séparer 2 au plus"):
        separer(session, cible.id, 3, EXPERT)
    with pytest.raises(CorrectionRefusee, match="Quantité invalide"):
        separer(session, cible.id, "zéro", EXPERT)
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Pas extraite", stockage)
    with pytest.raises(ActionRefusee, match="déjà analysée"):
        separer(session, bouteille(session, cree.inventaire_id).id, 1, EXPERT)


def test_separer_deux_fois_et_identifiants_uniques(session, propre):
    source = bouteille(session, propre)
    corriger(session, source.id, "quantite", 4, EXPERT)
    premiere = separer(session, source.id, 1, EXPERT)
    seconde = separer(session, source.id, 1, EXPERT)
    corriger(session, premiere.id, "quantite", 1, EXPERT)
    assert [premiere.identifiant, seconde.identifiant] == [f"{source.identifiant}-2", f"{source.identifiant}-3"]
    assert [b.quantite for b in charger_inventaire(session, propre).bouteilles[:3]] == [2, 1, 1]


def test_les_statistiques_comptent_la_separation_a_part(session, propre):
    source = bouteille(session, propre)
    corriger(session, source.id, "quantite", 6, EXPERT)
    corriger(session, source.id, "cuvee", "Autre", EXPERT)
    separer(session, source.id, 2, EXPERT)
    stats = stats_inventaire(session, propre)
    assert stats.nb_separees == 1
    # Les valeurs reprises et les quantités réparties ne sont pas des corrections de l'expert.
    assert stats.nb_corrections == 2 and stats.corrections_par_bouteille == {source.identifiant: 2}


# --- temps de relecture -----------------------------------------------------------------------


def test_le_temps_de_relecture_est_enregistre_a_la_validation(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    valider_en_relecture(session, cible.id, EXPERT, {}, version_de(session, cible.id), temps_ms=4200)
    assert cible.temps_relecture_ms == 4200
    # Rouverte et modifiée : le temps s'ajoute.
    corriger(session, cible.id, "cuvee", "X", EXPERT)
    valider_en_relecture(session, cible.id, EXPERT, {}, version_de(session, cible.id), temps_ms=1800)
    assert cible.temps_relecture_ms == 6000
    # Une valeur absurde est bornée, une valeur négative ignorée.
    autre = bouteille(session, inventaire_id, 1)
    valider(session, autre.id, EXPERT, temps_ms=10 * TEMPS_RELECTURE_MAX_MS)
    valider(session, bouteille(session, inventaire_id, 2).id, EXPERT, temps_ms=-5)
    stats = stats_inventaire(session, inventaire_id)
    assert stats.temps_relecture_total_ms == 6000 + TEMPS_RELECTURE_MAX_MS
    assert stats.bouteilles_chronometrees == 2


def test_un_refus_de_validation_n_enregistre_pas_le_temps(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    signaler_paire(session, cible.id, EXPERT)
    with pytest.raises(ValidationRefusee):
        valider_en_relecture(session, cible.id, EXPERT, {}, version_de(session, cible.id), temps_ms=3000)
    assert cible.temps_relecture_ms == 0


def test_statistiques_de_relecture(session, inventaire_id, stockage):
    b1, b2, b3 = charger_inventaire(session, inventaire_id).bouteilles[:3]
    corriger(session, b1.id, "millesime", "2001", EXPERT)
    corriger(session, b1.id, "cuvee", "X", EXPERT)
    corriger(session, b2.id, "millesime", "2002", EXPERT)
    reanalyser(session, b2.id, EXPERT)
    signaler_paire(session, b3.id, EXPERT)
    lever_signalement(session, b3.id, EXPERT)
    stats = stats_inventaire(session, inventaire_id)
    assert stats.corrections_par_bouteille == {b1.identifiant: 2, b2.identifiant: 1}
    assert stats.champs_les_plus_corriges[0] == ("millesime", 2)
    assert (stats.nb_reanalysees, stats.nb_signalees, stats.nb_separees) == (1, 1, 0)


# --- l'export reflète toutes les corrections ---------------------------------------------------


def test_l_export_reflete_toutes_les_corrections(session, inventaire_id, tmp_path):
    cible = bouteille(session, inventaire_id, 1)  # Château Margaux
    for champ, saisie in (("millesime", "2009"), ("couleur", "Blanc"), ("format", "magnum"),
                          ("etat_etiquette", "abimee"), ("description_etat", "Étiquette déchirée."),
                          ("estimation", "450"), ("quantite", "2"), ("cuvee", "Pavillon")):
        corriger_en_relecture(session, cible.id, champ, saisie, EXPERT, None)
    ligne = next(l for l in lignes_export(session, inventaire_id, tmp_path) if l["Domaine / Château"] == "Château Margaux")
    assert (ligne["Millésime"], ligne["Couleur"], ligne["Format"], ligne["État étiquette"]) == ("2009", "Blanc", "Magnum", "Abîmée")
    assert (ligne["Description de l'état"], ligne["Estimation (€)"], ligne["Qté"], ligne["Cuvée / Climat"]) == (
        "Étiquette déchirée.", "450", 2, "Pavillon")


# --- la fiche de relecture --------------------------------------------------------------------


def test_la_fiche_dit_d_ou_vient_chaque_valeur(session, inventaire_id):
    cible = bouteille(session, inventaire_id, 1)  # Château Margaux : couleur déduite, millésime illisible
    corriger(session, cible.id, "domaine", "Ch. Margaux", EXPERT)
    corriger(session, cible.id, "cuvee", "Pavillon Rouge", EXPERT)  # le modèle n'avait rien lu
    champs = {c.cle: c for c in fiche_de_relecture(session, inventaire_id, cible.id).champs}

    assert list(champs)[:3] == ["quantite", "domaine", "appellation"]  # ordre de la config
    assert "id" not in champs and "a_verifier" not in champs  # colonnes système : pas dans le formulaire
    assert champs["appellation"].origine == "lue"
    assert champs["couleur"].origine == "deduite"
    assert champs["etat_etiquette"].origine == "proposee"
    assert champs["domaine"].origine == "corrigee" and champs["domaine"].lue == "Château Margaux"
    assert champs["domaine"].peut_revenir
    assert champs["cuvee"].origine == "saisie" and champs["cuvee"].lue == "non lisible"
    assert champs["quantite"].origine == "defaut" and champs["estimation"].origine == "vide"
    assert champs["estimation"].lue is None  # le modèle ne remplit jamais l'estimation
    # « Non lisible » : à remplir, jamais affiché comme une valeur.
    assert champs["millesime"].a_remplir and champs["millesime"].saisie == "" and champs["millesime"].origine == "a_remplir"
    assert champs["millesime"].a_verifier  # doute signalé par le modèle
    assert not champs["etat_etiquette"].a_verifier  # best effort : signalé par son origine, pas surligné
    assert champs["couleur"].options[-1] == ("non_determinable", "Non déterminable")


def test_la_fiche_signale_les_doutes_hors_formulaire_et_la_paire(session, nom_maison, dossier_photos, stockage):
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    charges = [dict(PROPRE, champs_a_verifier=["degre"], photos_meme_bouteille="non")] * 6
    extraire_inventaire(session, cree.inventaire_id, FixtureExtractor(charges, charger_config(CONFIG_TEST)), stockage)
    fiche = fiche_de_relecture(session, cree.inventaire_id, bouteille(session, cree.inventaire_id).id)
    assert fiche.doutes_ailleurs == ["degre"]
    assert fiche.doute_paire and "même bouteille" in fiche.notes_modele


# --- navigation -------------------------------------------------------------------------------


def test_la_navigation_saute_les_bouteilles_pas_encore_extraites(session, nom_maison, dossier_photos, stockage):
    """La relecture commence pendant que l'extraction continue (guide, §1)."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "En cours", stockage)
    inventaire = charger_inventaire(session, cree.inventaire_id)
    from src.services.pilotage import lancer

    lancer(session, cree.inventaire_id)
    for _ in range(3):  # 3 bouteilles extraites sur 6
        traiter_reservee(session, reserver_bouteille(session, "w"), ExtracteurScenario(), stockage, "w")
    reanalyser(session, inventaire.bouteilles[1].id, EXPERT)  # la n°2 repart dans la file

    etats = etats_de_relecture(session, cree.inventaire_id)
    ids = [b.id for b in inventaire.bouteilles]
    assert voisines(etats, ids[0]) == (None, ids[2])  # n°2 en attente : sautée
    assert voisines(etats, ids[2]) == (ids[0], None)  # n°4 à 6 pas encore extraites
    assert prochaine_a_relire(etats) == ids[0]
    valider(session, ids[0], EXPERT)
    assert prochaine_a_relire(etats_de_relecture(session, cree.inventaire_id), apres_position=1) == ids[2]
    recap = recapitulatif(session, cree.inventaire_id)
    assert [e.position for e in recap.pas_encore_extraites] == [2, 4, 5, 6]


def test_prochaine_a_relire_reprend_au_debut_et_attend_les_signalees(session, inventaire_id):
    ids = [b.id for b in charger_inventaire(session, inventaire_id).bouteilles]
    for bouteille_id in ids[2:]:
        valider(session, bouteille_id, EXPERT)
    signaler_paire(session, ids[1], EXPERT)
    etats = etats_de_relecture(session, inventaire_id)
    assert prochaine_a_relire(etats, apres_position=6) == ids[0]  # reprend au début
    valider(session, ids[0], EXPERT)
    assert prochaine_a_relire(etats_de_relecture(session, inventaire_id), apres_position=1) is None  # la n°2 attend
    recap = recapitulatif(session, inventaire_id)
    assert [e.position for e in recap.signalees] == [2] and not recap.termine


def test_le_filtre_ne_garde_que_les_bouteilles_a_verifier(session, propre):
    ids = [b.id for b in charger_inventaire(session, propre).bouteilles]
    corriger(session, ids[3], "millesime", "", EXPERT)  # la n°4 redevient douteuse
    etats = etats_de_relecture(session, propre)
    assert [e.a_verifier for e in etats] == [False, False, False, True, False, False]
    assert voisines(etats, ids[0], a_verifier_seulement=True) == (None, ids[3])
    assert prochaine_a_relire(etats, a_verifier_seulement=True) == ids[3]
    assert prochaine_a_relire(etats, apres_position=4, a_verifier_seulement=True) == ids[3]


def test_les_valeurs_calculees_en_bloc_sont_celles_de_chaque_bouteille(session, nom_maison, dossier_photos, stockage):
    """`valeurs_courantes_de_l_inventaire` (rapide) = `valeurs_courantes` (une à une) :
    corrections, bouteille en erreur, séparée, en attente de réanalyse."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Mélange", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario({3: "passagere", 5: "illisible"}), stockage)
    b = charger_inventaire(session, cree.inventaire_id).bouteilles
    corriger(session, b[0].id, "millesime", "2001", EXPERT)
    corriger(session, b[0].id, "quantite", 4, EXPERT)
    separer(session, b[0].id, 1, EXPERT)
    corriger(session, b[1].id, "etat_etiquette", "tachee", EXPERT)
    reanalyser(session, b[3].id, EXPERT)
    en_bloc = valeurs_courantes_de_l_inventaire(session, cree.inventaire_id)
    for une in charger_inventaire(session, cree.inventaire_id).bouteilles:
        assert en_bloc[une.id].as_dict() == valeurs_courantes(session, une.id).as_dict(), une.position


# --- photos : préparées une fois, toujours sans métadonnées ------------------------------------


def test_la_version_d_affichage_est_preparee_une_fois_et_sans_metadonnees(session, inventaire_id, stockage):
    import io

    from PIL import Image

    from src.services.envoi import photo_a_servir

    photo = bouteille(session, inventaire_id).photos[0]
    premiere = photo_a_servir(session, stockage, inventaire_id, photo.id, "reduite")
    cache = stockage / "reduites" / f"{photo.empreinte}.jpg"
    instant = cache.stat().st_mtime_ns
    assert photo_a_servir(session, stockage, inventaire_id, photo.id, "reduite") == premiere
    assert cache.stat().st_mtime_ns == instant  # servie telle quelle, pas réencodée
    assert not Image.open(io.BytesIO(premiere)).getexif()  # aucune métadonnée (GPS de la cave)
    assert not list((stockage / "reduites").glob("*.partiel"))


# --- l'historique des événements ne se réécrit pas -------------------------------------------


def test_un_evenement_ne_se_modifie_ni_ne_se_supprime(session, inventaire_id):
    cible = bouteille(session, inventaire_id)
    signaler_paire(session, cible.id, EXPERT)
    evenement = session.scalar(select(EvenementBouteille))
    evenement.auteur = "quelqu'un d'autre"
    with pytest.raises(EnregistrementImmuable):
        session.commit()
    session.rollback()
    session.delete(session.scalar(select(EvenementBouteille)))
    with pytest.raises(EnregistrementImmuable):
        session.commit()
    session.rollback()
    assert session.scalar(select(func.count()).select_from(Correction).where(Correction.champ != "statut")) == 0
