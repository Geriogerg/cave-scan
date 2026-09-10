"""Le pipeline doit tourner de bout en bout sans clé API ni réseau (0012)."""

from __future__ import annotations

import sys

import pytest

import run_v0
from src.extract.base import Extractor
from src.extract.fixture_extract import FixtureExtractor
from src.extract.schema import Bouteille, Couleur, Format
from src.io.photos import PhotosBouteille, grouper_photos
from src.normalize.normalize import REGLES, normalize
from tests.conftest import FIXTURES


# --- la couture Extractor -----------------------------------------------


def test_fixture_extractor_respecte_le_protocol():
    """run_v0 dépend du Protocol, pas d'une implémentation (decisions.md 0014)."""
    extracteur = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")
    assert isinstance(extracteur, Extractor)


def test_fixture_extractor_rejoue_dans_l_ordre():
    extracteur = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")
    assert len(extracteur) == 6
    premiere = extracteur.extract("photo.jpg")
    deuxieme = extracteur.extract("photo.jpg")
    assert premiere.domaine == "Domaine Rossignol-Trapet"
    assert deuxieme.domaine == "Château Margaux"


def test_fixture_extractor_signale_l_epuisement():
    extracteur = FixtureExtractor([{"appellation": "Pommard"}])
    extracteur.extract("photo.jpg")
    with pytest.raises(IndexError, match="Fixtures épuisées"):
        extracteur.extract("photo.jpg")


# --- normalisation identité (decisions.md 0007) -------------------------


def test_normalize_est_l_identite_en_v0():
    assert REGLES == [], "La v0 ne doit contenir AUCUNE règle de normalisation."
    bouteille = Bouteille(
        domaine="Domaine du Vieux Télégraphe",
        appellation="CHÂTEAUNEUF-DU-PAPE",
        couleur=Couleur.ROUGE,
        format=Format.MAGNUM,
        contenance_cl=150,
    )
    assert normalize(bouteille) == bouteille


# --- regroupement des photos --------------------------------------------


def test_un_sous_dossier_par_bouteille(tmp_path):
    for nom in ("b02", "b01"):
        dossier = tmp_path / nom
        dossier.mkdir()
        (dossier / "01_etiquette.jpg").touch()
        (dossier / "02_contre_etiquette.jpg").touch()
        (dossier / "03_capsule.jpg").touch()

    bouteilles = grouper_photos(tmp_path)
    assert [b.nom for b in bouteilles] == ["b01", "b02"]

    premiere = bouteilles[0]
    assert premiere.etiquette.name == "01_etiquette.jpg"
    assert premiere.contre_etiquette.name == "02_contre_etiquette.jpg"
    assert [a.name for a in premiere.autres] == ["03_capsule.jpg"]


def test_dossier_plat_une_image_par_bouteille(tmp_path):
    (tmp_path / "a.jpg").touch()
    (tmp_path / "b.png").touch()
    (tmp_path / "notes.txt").touch()

    bouteilles = grouper_photos(tmp_path)
    assert len(bouteilles) == 2
    assert all(b.contre_etiquette is None for b in bouteilles)


def test_dossier_sans_image_leve_une_erreur(tmp_path):
    (tmp_path / "notes.txt").touch()
    with pytest.raises(ValueError, match="Aucune photo exploitable"):
        grouper_photos(tmp_path)


# --- bout en bout --------------------------------------------------------


def test_dry_run_produit_excel_et_rapport(tmp_path, capsys):
    sortie = tmp_path / "listing.xlsx"
    code = run_v0.main(["--dry-run", "--sortie", str(sortie)])
    sortie_texte = capsys.readouterr().out

    assert code == 0
    assert sortie.exists() and sortie.stat().st_size > 0
    assert "DRY-RUN" in sortie_texte
    assert "Comparaison auto vs manuel — 6 bouteille(s)" in sortie_texte
    assert "accuracy" in sortie_texte
    assert "Désaccords à inspecter (3)" in sortie_texte


def test_dry_run_n_importe_pas_le_sdk_anthropic(tmp_path):
    """Aucune dépendance API sur le chemin hors ligne."""
    sys.modules.pop("src.extract.vision_extract", None)
    run_v0.main(["--dry-run", "--sortie", str(tmp_path / "l.xlsx")])
    assert "src.extract.vision_extract" not in sys.modules


def test_mode_reel_exige_photos_et_manual(tmp_path):
    with pytest.raises(SystemExit):
        run_v0.main(["--sortie", str(tmp_path / "l.xlsx")])
