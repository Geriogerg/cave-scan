"""Le worker : parallèle, sans doublon, et sans rien perdre à un arrêt brutal.

Critères d'acceptation du guide de session 3, avec un extracteur FACTICE
(latence et erreurs simulées). Aucune pause fixe : chaque test attend une
CONDITION lue en base, avec une limite de temps (`attendre`).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.config.maison import charger_config
from src.donnees.base import creer_moteur, migrer, url_de_base
from src.donnees.modeles import Extraction, FicheBouteille, Inventaire
from src.extract.base import SortieModele
from src.extract.factice import ExtracteurFactice, appels_simultanes_sur_une_meme_photo
from src.extract.fixture_extract import generer_photos_fictives
from src.services.inventaires import creer_inventaire
from src.services.pilotage import annuler, lancer, relancer_erreurs
from src.worker import ReglagesWorker, Worker
from tests.conftest import CONFIG_TEST, RACINE

RAPIDE = ReglagesWorker(simultanees=4, periode_vie_s=0.2, attente_s=0.05)


def attendre(condition, limite_s=60.0, intervalle_s=0.05, message="condition"):
    """Attend une CONDITION, jamais une durée : rend dès qu'elle est vraie."""
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        if condition():
            return
        time.sleep(intervalle_s)
    raise AssertionError(f"{message} : pas atteinte en {limite_s} s")


@pytest.fixture
def base(tmp_path):
    chemin = tmp_path / "worker.db"
    migrer(url_de_base(chemin))
    moteur = creer_moteur(url_de_base(chemin))
    yield chemin, moteur
    moteur.dispose()


def creer(moteur, tmp_path, nom_maison, nombre, lance=True) -> int:
    """Un inventaire d'étiquettes seules : `nombre` photos = `nombre` bouteilles."""
    photos = generer_photos_fictives(tmp_path / f"photos{nombre}", (nombre + 1) // 2)
    if nombre % 2:
        sorted(photos.iterdir())[-1].unlink()
    with Session(moteur, expire_on_commit=False) as session:
        cree = creer_inventaire(
            session, nom_maison, CONFIG_TEST, photos, "Cave", tmp_path / "stockage", sans_contre=True
        )
        if lance:
            lancer(session, cree.inventaire_id)
    return cree.inventaire_id


def compter(moteur, statut=None, inventaire_id=None):
    with Session(moteur) as session:
        requete = select(func.count()).select_from(FicheBouteille)
        if statut:
            requete = requete.where(FicheBouteille.statut == statut)
        if inventaire_id:
            requete = requete.where(FicheBouteille.inventaire_id == inventaire_id)
        return session.scalar(requete)


def extractions_par_bouteille(moteur) -> dict[int, int]:
    with Session(moteur) as session:
        return dict(
            session.execute(
                select(Extraction.bouteille_id, func.count())
                .where(Extraction.erreur.is_(None))
                .group_by(Extraction.bouteille_id)
            ).all()
        )


def faire_tourner(worker, limite_s=120.0):
    """Le worker jusqu'à file vide, dans un thread surveillé : un blocage échoue
    proprement au lieu de figer la suite de tests."""
    erreurs = []

    def cible():
        try:
            worker.tourner(jusqu_a_vide=True)
        except BaseException as erreur:  # pragma: no cover — remonté ci-dessous
            erreurs.append(erreur)

    thread = threading.Thread(target=cible)
    thread.start()
    thread.join(limite_s)
    assert not thread.is_alive(), f"le worker tourne encore après {limite_s} s"
    assert not erreurs, erreurs


# --- 300 bouteilles, 4 à la fois ---------------------------------------------------------------


def test_300_bouteilles_4_simultanees_toutes_extraites_aucune_en_double(base, tmp_path, nom_maison):
    _, moteur = base
    creer(moteur, tmp_path, nom_maison, 300)
    journal = tmp_path / "appels.log"
    extracteur = ExtracteurFactice(charger_config(CONFIG_TEST), latence_s=0.005, variation_s=0.02, journal=journal)

    faire_tourner(Worker(moteur, tmp_path / "stockage", lambda config: extracteur, RAPIDE))

    assert compter(moteur, "extraite") == 300
    assert set(extractions_par_bouteille(moteur).values()) == {1}  # aucune en double
    assert len(extractions_par_bouteille(moteur)) == 300
    assert 2 <= extracteur.max_simultanes <= 4  # vraiment en parallèle, jamais plus de 4
    assert appels_simultanes_sur_une_meme_photo(journal) == []


def test_deux_workers_sur_le_meme_inventaire_ne_font_aucun_doublon(base, tmp_path, nom_maison):
    _, moteur = base
    creer(moteur, tmp_path, nom_maison, 60)
    journal = tmp_path / "appels.log"
    extracteur = ExtracteurFactice(latence_s=0.005, variation_s=0.01, journal=journal)
    workers = [Worker(moteur, tmp_path / "stockage", lambda config: extracteur, RAPIDE) for _ in range(2)]
    threads = [threading.Thread(target=w.tourner, kwargs={"jusqu_a_vide": True}) for w in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(120)

    assert compter(moteur, "extraite") == 60
    assert set(extractions_par_bouteille(moteur).values()) == {1}
    assert appels_simultanes_sur_une_meme_photo(journal) == []


def test_relancer_un_inventaire_deja_lance_ne_cree_aucun_doublon(base, tmp_path, nom_maison):
    _, moteur = base
    inventaire_id = creer(moteur, tmp_path, nom_maison, 12)
    with Session(moteur) as session:
        assert lancer(session, inventaire_id) is False  # déjà lancé : rien ne change
        assert relancer_erreurs(session, inventaire_id) == 0
    extracteur = ExtracteurFactice(latence_s=0.005)
    faire_tourner(Worker(moteur, tmp_path / "stockage", lambda config: extracteur, RAPIDE))
    with Session(moteur) as session:
        lancer(session, inventaire_id)  # relancé APRÈS la fin : rien à refaire
    faire_tourner(Worker(moteur, tmp_path / "stockage", lambda config: extracteur, RAPIDE))

    assert set(extractions_par_bouteille(moteur).values()) == {1}
    assert len(extractions_par_bouteille(moteur)) == 12


# --- erreurs ----------------------------------------------------------------------------------


class ExtracteurAPannes(ExtracteurFactice):
    """Panne choisie selon la photo : « systematique » lève, « passagere » rend
    une erreur comme le ferait un extracteur après ses nouvelles tentatives."""

    def __init__(self, pannes: dict[str, str], **options):
        super().__init__(**options)
        self.pannes = pannes

    def extraire_brut(self, photos):
        panne = self.pannes.get(Path(photos[0]).name)
        if panne == "systematique":
            raise PermissionError("clé API invalide")
        sortie = super().extraire_brut(photos)
        if panne == "passagere":
            return SortieModele(brut=None, modele=self.modele, version_prompt=self.version_prompt,
                                erreur="RateLimitError : quota dépassé")
        return sortie


def chemin_photo(moteur, inventaire_id, position) -> str:
    with Session(moteur) as session:
        bouteille = session.scalar(
            select(FicheBouteille).where(
                FicheBouteille.inventaire_id == inventaire_id, FicheBouteille.position == position
            )
        )
        return Path(bouteille.photo_etiquette.chemin).name


def test_erreur_passagere_erreur_sur_la_bouteille_seule(base, tmp_path, nom_maison):
    _, moteur = base
    inventaire_id = creer(moteur, tmp_path, nom_maison, 10)
    extracteur = ExtracteurAPannes({chemin_photo(moteur, inventaire_id, 3): "passagere"}, latence_s=0.005)

    faire_tourner(Worker(moteur, tmp_path / "stockage", lambda config: extracteur, RAPIDE))

    assert compter(moteur, "erreur") == 1
    assert compter(moteur, "extraite") == 9


def test_erreur_systematique_l_inventaire_s_arrete(base, tmp_path, nom_maison):
    """Un seul thread pour que « non traitées » soit exact : tout ce qui suit la
    bouteille en panne reste « à extraire »."""
    _, moteur = base
    inventaire_id = creer(moteur, tmp_path, nom_maison, 10)
    extracteur = ExtracteurAPannes({chemin_photo(moteur, inventaire_id, 4): "systematique"}, latence_s=0.005)
    reglages = ReglagesWorker(simultanees=1, periode_vie_s=0.2, attente_s=0.05)

    faire_tourner(Worker(moteur, tmp_path / "stockage", lambda config: extracteur, reglages))

    with Session(moteur) as session:
        inventaire = session.get(Inventaire, inventaire_id)
        assert inventaire.extraction == "arretee"
        assert "clé API invalide" in inventaire.motif_arret
    assert (compter(moteur, "extraite"), compter(moteur, "erreur"), compter(moteur, "a_extraire")) == (3, 1, 6)


# --- annulation ------------------------------------------------------------------------------


def test_annuler_les_bouteilles_non_commencees_ne_sont_pas_traitees(base, tmp_path, nom_maison):
    _, moteur = base
    inventaire_id = creer(moteur, tmp_path, nom_maison, 10)
    feu_vert = threading.Event()

    class Bloque(ExtracteurFactice):
        def extraire_brut(self, *arguments, **options):
            feu_vert.wait(60)
            return super().extraire_brut(*arguments, **options)

    extracteur = Bloque()
    reglages = ReglagesWorker(simultanees=2, periode_vie_s=0.2, attente_s=0.05)
    worker = Worker(moteur, tmp_path / "stockage", lambda config: extracteur, reglages)
    thread = threading.Thread(target=worker.tourner, kwargs={"jusqu_a_vide": True})
    thread.start()

    attendre(lambda: compter(moteur, "en_cours") == 2, message="2 bouteilles commencées")
    with Session(moteur) as session:
        annuler(session, inventaire_id)
    feu_vert.set()
    thread.join(60)

    assert not thread.is_alive()
    assert compter(moteur, "extraite") == 2  # les commencées ont terminé
    assert compter(moteur, "a_extraire") == 8  # les autres n'ont jamais été traitées
    assert len(extractions_par_bouteille(moteur)) == 2


# --- arrêt brutal du worker (un vrai processus, tué) ------------------------------------------


def lancer_worker(base_db: Path, journal: Path, stockage: Path, *options: str) -> subprocess.Popen:
    environnement = dict(os.environ, CAVE_SCAN_STOCKAGE=str(stockage), PYTHONIOENCODING="utf-8")
    for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        environnement.pop(variable, None)
    return subprocess.Popen(
        [
            sys.executable, str(RACINE / "worker.py"), "--base", str(base_db), "--backend", "factice",
            "--latence", "0.4", "--simultanees", "4", "--periode-vie", "0.2", "--delai-abandon", "1",
            "--attente", "0.05", "--journal-appels", str(journal), *options,
        ],
        cwd=RACINE, env=environnement, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


def test_arret_brutal_puis_redemarrage_aucune_perdue_aucune_en_double(base, tmp_path, nom_maison):
    base_db, moteur = base
    creer(moteur, tmp_path, nom_maison, 24)
    journal = tmp_path / "appels.log"

    premier = lancer_worker(base_db, journal, tmp_path / "stockage")
    try:
        attendre(
            lambda: compter(moteur, "extraite") >= 4 and compter(moteur, "en_cours") >= 2,
            message="extraction lancée, des bouteilles en cours",
        )
    finally:
        premier.kill()  # arrêt BRUTAL : aucun nettoyage, les réservations restent
        premier.wait(30)
    interrompues = compter(moteur, "en_cours")
    assert interrompues >= 1, "le worker tué n'a laissé aucune bouteille en cours"

    second = lancer_worker(base_db, journal, tmp_path / "stockage", "--jusqu-a-vide")
    _, erreurs = second.communicate(timeout=180)
    assert second.returncode == 0, erreurs.decode("utf-8", "replace")

    assert compter(moteur, "extraite") == 24  # aucune perdue
    assert set(extractions_par_bouteille(moteur).values()) == {1}  # aucune en double
    assert len(extractions_par_bouteille(moteur)) == 24
    # Jamais deux appels simultanés sur une même photo, y compris pendant la reprise.
    assert appels_simultanes_sur_une_meme_photo(journal, morts={premier.pid}) == []
