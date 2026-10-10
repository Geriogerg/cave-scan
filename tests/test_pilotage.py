"""Pilotage d'un inventaire et limite de débit partagée (decisions.md 0111, 0114, 0138)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from google.genai import errors

from src.extract.gemini_extract import GeminiExtractor
from src.services.debit import LimiteDebitPartagee
from src.services.extraction import extraire_inventaire, traiter_reservee
from src.services.file_attente import reserver_bouteille
from src.services.inventaires import charger_inventaire, creer_inventaire
from src.services.pilotage import annuler, avancement, lancer
from src.services.relecture import ValidationRefusee, valider, valider_inventaire
from tests.conftest import CONFIG_TEST
from tests.test_extraction import ExtracteurScenario


@pytest.fixture
def inventaire_id(session, nom_maison, dossier_photos, stockage):
    return creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage).inventaire_id


# --- annuler -----------------------------------------------------------------------------------


def test_annuler_laisse_les_bouteilles_non_commencees_a_extraire(session, inventaire_id, stockage):
    lancer(session, inventaire_id)
    en_cours = reserver_bouteille(session, "w")  # commencée avant l'annulation
    assert annuler(session, inventaire_id) is True

    assert reserver_bouteille(session, "w") is None  # plus rien n'est servi
    traiter_reservee(session, en_cours, ExtracteurScenario(), stockage, "w")  # elle termine
    etat = avancement(session, inventaire_id)
    assert etat.par_statut["extraite"] == 1 and etat.par_statut["a_extraire"] == 5
    assert etat.extraction == "annulee"
    assert annuler(session, inventaire_id) is False


# --- avancement --------------------------------------------------------------------------------


def test_avancement_avant_et_apres_extraction(session, inventaire_id, stockage):
    etat = avancement(session, inventaire_id)
    assert (etat.total, etat.restantes, etat.extraction) == (6, 6, "non_lancee")
    assert etat.ecoule_s is None and etat.restant_estime_s is None

    extraire_inventaire(session, inventaire_id, ExtracteurScenario({2: "passagere"}), stockage)

    etat = avancement(session, inventaire_id)
    assert etat.terminee and etat.restant_estime_s == 0.0
    assert etat.par_statut["extraite"] == 5 and etat.par_statut["erreur"] == 1
    assert (etat.tokens_entree, etat.tokens_sortie) == (5 * 1000, 5 * 200)
    assert etat.ecoule_s >= 0


def test_le_temps_restant_suit_le_rythme_observe(session, inventaire_id, stockage):
    lancer(session, inventaire_id)
    for _ in range(2):
        traiter_reservee(session, reserver_bouteille(session, "w"), ExtracteurScenario(), stockage, "w")
    etat = avancement(session, inventaire_id)
    assert etat.restantes == 4
    assert etat.restant_estime_s == pytest.approx(etat.ecoule_s * 4 / 2, rel=0.05)


# --- valider l'inventaire ----------------------------------------------------------------------


def test_valider_l_inventaire_ne_valide_aucune_bouteille_a_la_place_de_l_expert(session, inventaire_id, stockage):
    """Pas de validation en masse (decisions.md 0138, qui remplace 0120) : tant
    qu'une bouteille n'a pas été validée une par une, c'est refusé, avec ce qui
    reste à faire ; une fois toutes validées, l'inventaire l'est."""
    extraire_inventaire(session, inventaire_id, ExtracteurScenario(), stockage)
    with pytest.raises(ValidationRefusee, match=r"6 bouteille\(s\) à relire"):
        valider_inventaire(session, inventaire_id, "expert")
    assert avancement(session, inventaire_id).par_statut["validee"] == 0  # rien validé à sa place

    for bouteille in charger_inventaire(session, inventaire_id).bouteilles:
        valider(session, bouteille.id, "expert")
    assert valider_inventaire(session, inventaire_id, "expert") == 6
    assert avancement(session, inventaire_id).par_statut["validee"] == 6
    assert charger_inventaire(session, inventaire_id).statut == "valide"


def test_valider_l_inventaire_refuse_avec_un_message_pour_l_expert(session, inventaire_id, stockage):
    extraire_inventaire(session, inventaire_id, ExtracteurScenario({4: "passagere"}), stockage)
    with pytest.raises(ValidationRefusee, match=r"1 bouteille\(s\) en erreur \(n°4\)"):
        valider_inventaire(session, inventaire_id, "expert")
    assert avancement(session, inventaire_id).par_statut["validee"] == 0  # rien de validé


# --- limite de débit partagée ------------------------------------------------------------------


class Horloge:
    """Temps simulé : attendre l'avance, sans jamais dormir."""

    def __init__(self):
        self.instant = datetime(2026, 1, 1, 12, 0, 0)
        self.attentes: list[float] = []

    def __call__(self) -> datetime:
        return self.instant

    def attendre(self, secondes: float) -> None:
        self.attentes.append(round(secondes, 3))
        self.instant += timedelta(seconds=secondes)


def limiteurs(session, horloge, nombre, espacement_s=2.0):
    return [
        LimiteDebitPartagee(session.get_bind(), "modele-x", espacement_s, horloge.attendre, horloge)
        for _ in range(nombre)
    ]


def test_l_espacement_est_partage_entre_workers(session):
    horloge = Horloge()
    premier, second = limiteurs(session, horloge, 2)
    premier.attendre_mon_tour()
    second.attendre_mon_tour()  # un autre worker : il attend le créneau suivant
    premier.attendre_mon_tour()
    assert horloge.attentes == [2.0, 2.0]


def test_une_limite_atteinte_ralentit_tout_le_monde(session):
    horloge = Horloge()
    premier, second = limiteurs(session, horloge, 2, espacement_s=0)
    premier.ralentir(30)
    second.attendre_mon_tour()
    assert horloge.attentes == [30.0]


def test_gemini_ralentit_via_le_limiteur_partage(monkeypatch, tmp_path):
    """Sur un 429, Gemini demande une pause commune au lieu de dormir seul."""
    dormi = []
    monkeypatch.setattr("src.extract.gemini_extract.time.sleep", dormi.append)
    photo = tmp_path / "e.jpg"
    photo.write_bytes(b"\xff\xd8")
    reponses = [
        errors.ClientError(429, {"error": {"message": "quota"}}, None),
        SimpleNamespace(text='{"appellation": "Pommard"}', candidates=[], prompt_feedback=None),
    ]

    class Client:
        def __init__(self):
            self.models = self

        def generate_content(self, **_):
            reponse = reponses.pop(0)
            if isinstance(reponse, Exception):
                raise reponse
            return reponse

    class Espion:
        def __init__(self):
            self.tours, self.pauses = 0, []

        def attendre_mon_tour(self):
            self.tours += 1

        def ralentir(self, pause_s):
            self.pauses.append(pause_s)

    limiteur = Espion()
    sortie = GeminiExtractor(client=Client(), pause_s=1, limiteur=limiteur).extraire_brut(photo)

    assert sortie.erreur is None
    assert (limiteur.tours, limiteur.pauses) == (2, [2])
    assert dormi == []
