"""Cycle de vie d'un inventaire (decisions.md 0168) : renommer, archiver, corbeille,
clore, rouvrir ; retirer et remettre une bouteille. Rien ne se supprime vraiment,
chaque geste est tracé, un inventaire clos est en lecture seule."""

from __future__ import annotations

import io
import json

import pytest
from sqlalchemy import func, select

from src.config.maison import charger_config
from src.donnees.modeles import Correction, EnregistrementImmuable, EvenementInventaire, Extraction, Photo
from src.extract.fixture_extract import FixtureExtractor
from src.services.cas_particuliers import reanalyser, separer, signaler_paire
from src.services.consultation import etats_de_relecture
from src.services.cycle_de_vie import (
    CycleRefuse,
    archiver,
    bilan,
    bouteilles_retirees,
    clore,
    desarchiver,
    evenements_d_inventaire,
    remettre_bouteille,
    renommer,
    restaurer,
    retirer_bouteille,
    rouvrir,
    supprimer,
)
from src.services.depot import ajouter_photo
from src.services.extraction import extraire_inventaire
from src.services.file_attente import reserver_bouteille
from src.services.inventaires import (
    InventaireClos,
    InventaireIntrouvable,
    charger_inventaire,
    creer_inventaire,
    lister_inventaires,
)
from src.services.pilotage import lancer, relancer_erreurs
from src.services.relecture import corriger, valider
from src.services.restitution import exporter
from tests.conftest import CONFIG_TEST, FIXTURES
from tests.test_depot import jpeg

EXPERT = "Prénom Nom"


@pytest.fixture
def extrait(session, nom_maison, dossier_photos, stockage):
    """6 bouteilles extraites sur les fixtures habituelles."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave Dupont", stockage)
    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))
    extraire_inventaire(session, cree.inventaire_id, FixtureExtractor(charges, charger_config(CONFIG_TEST)), stockage)
    return cree.inventaire_id


def bouteilles(session, inventaire_id):
    return list(charger_inventaire(session, inventaire_id).bouteilles)


def types(session, inventaire_id):
    return [e.type for e in evenements_d_inventaire(session, inventaire_id)]


def compter(session, modele):
    return session.scalar(select(func.count()).select_from(modele))


# --- renommer, archiver ------------------------------------------------------------------------


def test_renommer_est_trace(session, extrait):
    renommer(session, extrait, "  Vente du 12 décembre  ", EXPERT)
    assert charger_inventaire(session, extrait).nom == "Vente du 12 décembre"
    (evenement,) = evenements_d_inventaire(session, extrait)
    assert (evenement.type, evenement.auteur, evenement.detail["avant"]) == ("renommage", EXPERT, "Cave Dupont")
    with pytest.raises(CycleRefuse, match="Donnez un nom"):
        renommer(session, extrait, "   ", EXPERT)


def test_archiver_range_sans_rien_fermer(session, extrait):
    assert archiver(session, extrait, EXPERT) is True and archiver(session, extrait, EXPERT) is False
    inventaire = charger_inventaire(session, extrait)
    assert inventaire.archive_le is not None and inventaire in lister_inventaires(session)  # toujours ouvrable
    corriger(session, bouteilles(session, extrait)[0].id, "millesime", "2001", EXPERT)  # toujours modifiable
    assert desarchiver(session, extrait, EXPERT) is True
    assert types(session, extrait) == ["archivage", "desarchivage"]


# --- la corbeille ----------------------------------------------------------------------------


def test_supprimer_met_a_la_corbeille_sans_rien_effacer(session, extrait):
    avant = {modele: compter(session, modele) for modele in (Photo, Extraction, Correction)}
    lancer(session, extrait)
    supprimer(session, extrait, EXPERT)

    assert lister_inventaires(session) == [] and [i.id for i in lister_inventaires(session, corbeille=True)] == [extrait]
    with pytest.raises(InventaireIntrouvable, match="dans la corbeille"):
        charger_inventaire(session, extrait)
    assert {modele: compter(session, modele) for modele in avant} == avant  # rien n'est effacé
    # Analyse finie : rien à arrêter (T4-D1) ; le worker ignore de toute façon la
    # corbeille (test_le_worker_ne_traite_jamais_un_inventaire_a_la_corbeille).
    assert charger_inventaire(session, extrait, corbeille=True).extraction == "lancee"

    restaurer(session, extrait, EXPERT)
    assert [i.id for i in lister_inventaires(session)] == [extrait]
    assert types(session, extrait) == ["suppression", "restauration"]
    with pytest.raises(CycleRefuse, match="pas dans la corbeille"):
        restaurer(session, extrait, EXPERT)


def test_le_worker_ne_traite_jamais_un_inventaire_a_la_corbeille(session, nom_maison, dossier_photos, stockage):
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    lancer(session, cree.inventaire_id)
    supprimer(session, cree.inventaire_id, EXPERT)
    assert reserver_bouteille(session, "worker") is None


# --- clore, rouvrir ----------------------------------------------------------------------------


def test_clore_sans_tout_valider_est_permis_et_note_ce_qui_reste(session, extrait):
    """Valider bouteille par bouteille reste facultatif."""
    valider(session, bouteilles(session, extrait)[0].id, EXPERT)
    etat = clore(session, extrait, EXPERT)
    assert (etat.validees, etat.non_validees) == (1, 5)
    assert etat.ce_qui_n_est_pas_valide() == "5 bouteilles non validées"
    (evenement,) = evenements_d_inventaire(session, extrait)
    assert evenement.type == "cloture" and evenement.detail == {
        "bouteilles": 6, "validees": 1, "non_validees": 5, "en_erreur": 0,
    }


def test_clore_est_refuse_tant_qu_une_bouteille_n_a_pas_sa_ligne(session, nom_maison, dossier_photos, stockage):
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    with pytest.raises(CycleRefuse, match="6 bouteille.*en cours d'analyse"):
        clore(session, cree.inventaire_id, EXPERT)
    assert charger_inventaire(session, cree.inventaire_id).clos_le is None


def test_clore_est_refuse_si_des_bouteilles_ajoutees_ne_sont_pas_lancees(session, extrait, stockage):
    ajouter_photo(session, extrait, io.BytesIO(jpeg(42)), "ajout.jpg", stockage, bouteille="ajout", numero=7)
    with pytest.raises(CycleRefuse, match="1 bouteille.*pas encore lancée"):
        clore(session, extrait, EXPERT)


def test_un_inventaire_clos_est_en_lecture_seule(session, extrait, stockage, tmp_path):
    cible = bouteilles(session, extrait)[0]
    clore(session, extrait, EXPERT)
    for geste in (
        lambda: corriger(session, cible.id, "millesime", "2001", EXPERT),
        lambda: valider(session, cible.id, EXPERT),
        lambda: reanalyser(session, cible.id, EXPERT),
        lambda: signaler_paire(session, cible.id, EXPERT),
        lambda: separer(session, cible.id, 1, EXPERT),
        lambda: retirer_bouteille(session, cible.id, EXPERT),
        lambda: renommer(session, extrait, "Autre nom", EXPERT),
        lambda: relancer_erreurs(session, extrait),
        lambda: ajouter_photo(session, extrait, io.BytesIO(jpeg(42)), "a.jpg", stockage, bouteille="x", numero=9),
    ):
        with pytest.raises(InventaireClos, match="lecture seule"):
            geste()
    assert exporter(session, extrait, tmp_path / "clos.xlsx").exists()  # l'export reste possible
    with pytest.raises(CycleRefuse, match="déjà clos"):
        clore(session, extrait, EXPERT)


def test_rouvrir_est_trace_et_rend_modifiable(session, extrait):
    clore(session, extrait, EXPERT)
    rouvrir(session, extrait, EXPERT)
    corriger(session, bouteilles(session, extrait)[0].id, "millesime", "2001", EXPERT)
    assert types(session, extrait) == ["cloture", "reouverture"]
    with pytest.raises(CycleRefuse, match="n'est pas clos"):
        rouvrir(session, extrait, EXPERT)


def test_l_historique_de_l_inventaire_ne_se_reecrit_pas(session, extrait):
    renommer(session, extrait, "Autre", EXPERT)
    evenement = session.scalar(select(EvenementInventaire))
    evenement.auteur = "quelqu'un d'autre"
    with pytest.raises(EnregistrementImmuable):
        session.commit()
    session.rollback()
    session.delete(session.scalar(select(EvenementInventaire)))
    with pytest.raises(EnregistrementImmuable):
        session.commit()


# --- retirer, remettre une bouteille --------------------------------------------------------


def test_une_bouteille_retiree_sort_de_l_inventaire_sans_rien_perdre(session, extrait, tmp_path):
    from openpyxl import load_workbook

    deuxieme = bouteilles(session, extrait)[1]
    retirer_bouteille(session, deuxieme.id, EXPERT, "pas dans la vente")
    assert [b.position for b in bouteilles(session, extrait)] == [1, 3, 4, 5, 6]  # elle garde sa place
    assert deuxieme.id not in [e.id for e in etats_de_relecture(session, extrait)]  # plus en relecture
    feuille = load_workbook(exporter(session, extrait, tmp_path / "r.xlsx")).active
    assert feuille.max_row - 1 == 5  # plus à l'export
    assert bilan(session, extrait).retirees == 1 and bilan(session, extrait).total == 5
    assert [b.id for b in bouteilles_retirees(session, extrait)] == [deuxieme.id]
    assert compter(session, Extraction) == 6  # rien n'est effacé
    assert [e.type for e in deuxieme.evenements] == ["retrait"] and deuxieme.evenements[0].detail == {"motif": "pas dans la vente"}

    remettre_bouteille(session, deuxieme.id, EXPERT)
    assert [b.position for b in bouteilles(session, extrait)] == [1, 2, 3, 4, 5, 6]
    assert [e.type for e in deuxieme.evenements] == ["retrait", "remise"]


def test_une_bouteille_retiree_n_est_jamais_analysee(session, nom_maison, dossier_photos, stockage):
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    premiere = bouteilles(session, cree.inventaire_id)[0]
    retirer_bouteille(session, premiere.id, EXPERT)
    lancer(session, cree.inventaire_id)
    assert reserver_bouteille(session, "worker") == bouteilles(session, cree.inventaire_id)[0].id != premiere.id


def test_separer_apres_un_retrait_garde_des_places_distinctes(session, extrait):
    """La bouteille retirée garde sa place : la séparation décale aussi les retirées."""
    premiere, deuxieme = bouteilles(session, extrait)[:2]
    retirer_bouteille(session, deuxieme.id, EXPERT)
    corriger(session, premiere.id, "quantite", 2, EXPERT)
    nouvelle = separer(session, premiere.id, 1, EXPERT)
    assert nouvelle.position == 2 and deuxieme.position == 3


def test_retirer_la_seule_bouteille_non_validee_valide_l_inventaire(session, extrait):
    for b in bouteilles(session, extrait)[1:]:
        valider(session, b.id, EXPERT)
    assert charger_inventaire(session, extrait).statut == "ouvert"
    retirer_bouteille(session, bouteilles(session, extrait)[0].id, EXPERT)
    assert charger_inventaire(session, extrait).statut == "valide"


def test_retirer_deux_fois_ou_remettre_une_bouteille_presente_est_refuse(session, extrait):
    premiere = bouteilles(session, extrait)[0]
    with pytest.raises(CycleRefuse, match="n'est pas retirée"):
        remettre_bouteille(session, premiere.id, EXPERT)
    retirer_bouteille(session, premiere.id, EXPERT)
    with pytest.raises(CycleRefuse, match="déjà retirée"):
        retirer_bouteille(session, premiere.id, EXPERT)
