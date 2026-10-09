"""File d'attente en base : réservation atomique, signes de vie, reprise
(decisions.md 0109-0113)."""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.donnees.modeles import Extraction, FicheBouteille, maintenant
from src.services.extraction import (
    BouteilleOccupee,
    ExtractionArretee,
    conclure_sans_appel,
    extraire_bouteille,
    traiter_reservee,
)
from src.services.file_attente import (
    liberer,
    reprendre_les_abandonnees,
    reserver_bouteille,
    signe_de_vie,
)
from src.services.inventaires import charger_inventaire, creer_inventaire
from src.services.pilotage import lancer, relancer_erreurs
from tests.conftest import CONFIG_TEST
from tests.test_extraction import ExtracteurScenario


@pytest.fixture
def inventaire_id(session, nom_maison, dossier_photos, stockage):
    return creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage).inventaire_id


def statuts(session, inventaire_id):
    session.expire_all()
    return [b.statut for b in charger_inventaire(session, inventaire_id).bouteilles]


def nb_extractions(session, bouteille_id):
    return session.scalar(select(func.count()).select_from(Extraction).where(Extraction.bouteille_id == bouteille_id))


# --- réserver -------------------------------------------------------------------------------


def test_rien_n_est_reserve_dans_un_inventaire_non_lance(session, inventaire_id):
    assert reserver_bouteille(session, "w1") is None
    lancer(session, inventaire_id)
    assert reserver_bouteille(session, "w1") is not None


def test_les_reservations_suivent_l_ordre_et_ne_se_repetent_jamais(session, inventaire_id):
    lancer(session, inventaire_id)
    ids = [reserver_bouteille(session, f"w{n}") for n in range(7)]
    attendus = [b.id for b in charger_inventaire(session, inventaire_id).bouteilles]
    assert ids == attendus + [None]
    assert statuts(session, inventaire_id) == ["en_cours"] * 6


def test_des_workers_concurrents_ne_reservent_jamais_la_meme_bouteille(session, inventaire_id):
    """8 threads, chacun avec sa propre session, réservent jusqu'à épuisement."""
    lancer(session, inventaire_id)
    moteur = session.get_bind()
    obtenues: list[int] = []
    verrou = threading.Lock()
    depart = threading.Barrier(8)

    def worker(nom):
        with Session(moteur) as propre:
            depart.wait()
            while (bouteille_id := reserver_bouteille(propre, nom)) is not None:
                with verrou:
                    obtenues.append(bouteille_id)

    threads = [threading.Thread(target=worker, args=(f"w{n}",)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert sorted(obtenues) == sorted(b.id for b in charger_inventaire(session, inventaire_id).bouteilles)


def test_la_base_est_en_mode_wal(session):
    assert session.connection().exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"


def test_une_bouteille_traitee_ailleurs_est_refusee(session, inventaire_id, stockage):
    lancer(session, inventaire_id)
    bouteille_id = reserver_bouteille(session, "autre-worker")
    with pytest.raises(BouteilleOccupee):
        extraire_bouteille(session, bouteille_id, ExtracteurScenario(), stockage)
    assert nb_extractions(session, bouteille_id) == 0


# --- signes de vie et reprise ------------------------------------------------------------------


def vieillir(session, bouteille_id, heures=1):
    """Simule un worker mort : son dernier signe de vie date d'il y a longtemps."""
    bouteille = session.get(FicheBouteille, bouteille_id)
    bouteille.reservee_le = bouteille.vu_le = maintenant() - timedelta(hours=heures)
    session.commit()


def test_signe_de_vie_rafraichit_les_seules_reservations_du_worker(session, inventaire_id):
    lancer(session, inventaire_id)
    mienne, autre = reserver_bouteille(session, "moi"), reserver_bouteille(session, "autre")
    vieillir(session, mienne)
    vieillir(session, autre)
    assert signe_de_vie(session, "moi") == 1
    reprises = reprendre_les_abandonnees(session, "reprise", delai=timedelta(minutes=2))
    assert reprises.remises_a_extraire == [autre]


def test_une_bouteille_abandonnee_retourne_a_la_file(session, inventaire_id):
    lancer(session, inventaire_id)
    abandonnee = reserver_bouteille(session, "mort")
    vivante = reserver_bouteille(session, "vivant")
    vieillir(session, abandonnee)

    reprises = reprendre_les_abandonnees(session, "reprise")

    assert reprises.remises_a_extraire == [abandonnee] and reprises.a_conclure == []
    assert statuts(session, inventaire_id)[:2] == ["a_extraire", "en_cours"]
    assert reserver_bouteille(session, "suivant") == abandonnee  # reprise en premier
    assert session.get(FicheBouteille, vivante).reservee_par == "vivant"


def test_reponse_deja_recue_conclue_sans_nouvel_appel(session, inventaire_id, stockage):
    """Arrêt brutal ENTRE l'enregistrement de la réponse et le statut : la reprise
    termine la bouteille sans rappeler le modèle — jamais un appel payé deux fois."""
    lancer(session, inventaire_id)
    bouteille_id = reserver_bouteille(session, "mort")
    bouteille = session.get(FicheBouteille, bouteille_id)
    bouteille.extractions.append(  # ce que traiter_reservee a écrit avant de mourir
        Extraction(sortie_brute={"appellation": "Pommard"}, modele="m", version_prompt="v", duree_ms=1)
    )
    session.commit()
    vieillir(session, bouteille_id)
    session.execute(  # la réponse est postérieure à la réservation
        Extraction.__table__.update().where(Extraction.bouteille_id == bouteille_id).values(cree_le=maintenant())
    )
    session.commit()

    reprises = reprendre_les_abandonnees(session, "reprise")
    assert reprises.a_conclure == [bouteille_id]
    conclure_sans_appel(session, bouteille_id)

    assert statuts(session, inventaire_id)[0] == "extraite"
    assert nb_extractions(session, bouteille_id) == 1


def test_deux_reprises_simultanees_ne_reprennent_qu_une_fois(session, inventaire_id):
    lancer(session, inventaire_id)
    bouteille_id = reserver_bouteille(session, "mort")
    vieillir(session, bouteille_id)
    with Session(session.get_bind()) as autre:
        premiere = reprendre_les_abandonnees(session, "r1")
        seconde = reprendre_les_abandonnees(autre, "r2")
    assert premiere.remises_a_extraire + seconde.remises_a_extraire == [bouteille_id]


def test_un_ctrl_c_rend_la_bouteille_a_la_file(session, inventaire_id, stockage):
    class Interrompu(ExtracteurScenario):
        def extraire_brut(self, etiquette, contre_etiquette=None, autres=None):
            raise KeyboardInterrupt

    lancer(session, inventaire_id)
    bouteille_id = reserver_bouteille(session, "cli")
    with pytest.raises(KeyboardInterrupt):
        traiter_reservee(session, bouteille_id, Interrompu(), stockage, "cli")
    assert statuts(session, inventaire_id)[0] == "a_extraire"
    assert nb_extractions(session, bouteille_id) == 0


def test_liberer_ne_touche_pas_la_reservation_d_un_autre(session, inventaire_id):
    lancer(session, inventaire_id)
    bouteille_id = reserver_bouteille(session, "proprietaire")
    liberer(session, bouteille_id, "intrus")
    assert statuts(session, inventaire_id)[0] == "en_cours"


# --- panne systématique : l'inventaire s'arrête -------------------------------------------------


def test_une_panne_systematique_arrete_l_inventaire(session, inventaire_id, stockage):
    lancer(session, inventaire_id)
    bouteille_id = reserver_bouteille(session, "w")
    with pytest.raises(ExtractionArretee):
        traiter_reservee(session, bouteille_id, ExtracteurScenario({1: "systematique"}), stockage, "w")

    inventaire = charger_inventaire(session, inventaire_id)
    assert inventaire.extraction == "arretee"
    assert "clé API invalide" in inventaire.motif_arret
    assert reserver_bouteille(session, "w") is None  # plus rien n'est servi
    assert statuts(session, inventaire_id) == ["erreur"] + ["a_extraire"] * 5

    assert relancer_erreurs(session, inventaire_id) == 1
    assert lancer(session, inventaire_id) is True
    assert inventaire.motif_arret is None
    assert reserver_bouteille(session, "w") == bouteille_id


def test_lancer_est_idempotent(session, inventaire_id):
    assert lancer(session, inventaire_id) is True
    assert lancer(session, inventaire_id) is False
