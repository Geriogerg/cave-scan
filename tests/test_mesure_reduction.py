"""L'outil de mesure de la réduction (decisions.md 0130) — vérifié hors ligne."""

from __future__ import annotations

import io

from PIL import Image

import mesurer_reduction
from src.config.maison import charger_config
from src.extract.base import SortieModele
from src.extract.factice import ExtracteurFactice
from src.mesure.reduction import formater, mesurer, reduire
from tests.conftest import CONFIG_TEST


def photo(chemin, taille=(3000, 4000), orientation=None):
    image = Image.new("RGB", taille, (120, 30, 60))
    exif = Image.Exif()
    exif[0x0132] = "2026:09:17 15:56:53"
    if orientation:
        exif[0x0112] = orientation
    image.save(chemin, "JPEG", exif=exif.tobytes())
    return chemin


def test_reduire_comme_le_navigateur(tmp_path):
    reduite = Image.open(io.BytesIO(reduire(photo(tmp_path / "a.jpg"), 2500)))
    assert reduite.size == (1875, 2500)  # côté long ramené, proportions gardées
    assert dict(reduite.getexif()) == {}  # comme le navigateur : plus d'EXIF
    tournee = Image.open(io.BytesIO(reduire(photo(tmp_path / "b.jpg", (4000, 3000), orientation=6), 2500)))
    assert tournee.size == (1875, 2500)  # rotation appliquée
    petite = Image.open(io.BytesIO(reduire(photo(tmp_path / "c.jpg", (800, 600)), 2500)))
    assert petite.size == (800, 600)  # jamais agrandie


class LitMoinsBienEnPetit(ExtracteurFactice):
    """Simule un millésime qui devient illisible sous 2000 px."""

    def extraire_brut(self, photos):
        cote = max(Image.open(photos[0]).size)
        millesime = "2015" if cote >= 2000 else "non_lisible"
        return SortieModele(brut={"domaine": "Domaine X", "millesime": millesime}, modele="m", version_prompt="v",
                            tokens_entree=cote, tokens_sortie=10)


def test_la_mesure_detecte_une_lecture_perdue(tmp_path):
    config = charger_config(CONFIG_TEST)
    photos = [photo(tmp_path / f"p{n}.jpg") for n in range(3)]
    mesure = mesurer(photos, [1600, 2500], lambda: LitMoinsBienEnPetit(config), config, tmp_path / "travail")

    original, petite, grande = mesure.resultats
    assert petite.perdues["millesime"] == 3 and grande.perdues["millesime"] == 0
    assert grande.identiques["domaine"] == 3
    assert petite.tokens_entree < original.tokens_entree  # plus petit : moins cher en entrée
    tableau = formater(mesure)
    assert "1600 px" in tableau and "millesime (3 perdu(s)" in tableau


def test_le_script_a_blanc_sans_appel_reel(tmp_path, capsys):
    dossier = tmp_path / "photos"
    dossier.mkdir()
    for n in range(2):
        photo(dossier / f"p{n}.jpg", (2400, 3200))
    assert mesurer_reduction.main(["--photos", str(dossier), "--backend", "factice", "--tailles", "2000"]) == 0
    sortie = capsys.readouterr().out
    assert "2 photo(s) × 2 version(s) = 4 appel(s)" in sortie and "2000 px" in sortie
