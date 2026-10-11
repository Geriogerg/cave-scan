"""Ce que reçoit le modèle pour UNE bouteille (decisions.md 0164, 0165) : toutes
ses photos dans le même appel, numérotées, sans rôle imposé ; au-delà de la
limite du fournisseur, seules les plus lourdes sont réduites, pour cet appel
seulement."""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from src.extract import gemini_extract, vision_extract
from src.extract.consignes import LimitesEnvoi, preparer_photos


def photo(chemin, cote=400, bruit=True):
    """Une photo JPEG ; avec du bruit, elle pèse lourd et se réduit bien."""
    image = Image.frombytes("RGB", (cote, cote), os.urandom(cote * cote * 3)) if bruit else Image.new("RGB", (cote, cote))
    image.save(chemin, "JPEG", quality=95)
    return chemin


def test_sous_la_limite_les_photos_partent_telles_quelles(tmp_path):
    photos = [photo(tmp_path / f"{i}.jpg", 100) for i in range(3)]
    contenus = preparer_photos(photos, LimitesEnvoi(octets_total=10_000_000))
    assert contenus == [(p.read_bytes(), "image/jpeg") for p in photos]


def test_au_dela_seules_les_plus_lourdes_sont_reduites(tmp_path):
    grande = photo(tmp_path / "grande.jpg", 3600)
    petite = photo(tmp_path / "petite.jpg", 200)
    avant = grande.read_bytes()
    limite = len(avant) // 2 + len(petite.read_bytes())
    contenus = preparer_photos([grande, petite], LimitesEnvoi(octets_total=limite))

    assert sum(len(octets) for octets, _ in contenus) <= limite
    assert contenus[1] == (petite.read_bytes(), "image/jpeg")  # la petite part telle quelle
    with Image.open(io.BytesIO(contenus[0][0])) as reduite:
        assert max(reduite.size) < 3600 and dict(reduite.getexif()) == {}
    assert grande.read_bytes() == avant  # le fichier stocké ne change jamais


def test_limite_par_photo(tmp_path):
    lourde = photo(tmp_path / "lourde.jpg", 2400)
    limite = len(lourde.read_bytes()) // 3
    (octets, type_mime), = preparer_photos([lourde], LimitesEnvoi(octets_total=10**9, octets_par_photo=limite))
    assert len(octets) <= limite and type_mime == "image/jpeg"


def test_l_ordre_des_photos_est_garde(tmp_path):
    photos = [photo(tmp_path / f"{i}.jpg", 60 + 40 * i, bruit=False) for i in range(4)]
    contenus = preparer_photos(photos, LimitesEnvoi(octets_total=10**9))
    assert [Image.open(io.BytesIO(o)).size[0] for o, _ in contenus] == [60, 100, 140, 180]


@pytest.mark.parametrize("module", [gemini_extract, vision_extract])
def test_les_limites_des_fournisseurs_laissent_la_marge_du_base64(module):
    """Gemini : 20 Mo par requête ; Anthropic : 5 Mo par image, 32 Mo par requête —
    base64 compris, qui ajoute un tiers."""
    limites = module.LIMITES_ENVOI
    plafond_requete = 20 if module is gemini_extract else 32
    assert limites.octets_total * 4 / 3 < plafond_requete * 1024 * 1024
    if module is vision_extract:
        assert limites.octets_par_photo * 4 / 3 < 5 * 1024 * 1024


def test_toutes_les_photos_d_une_bouteille_dans_le_meme_appel_numerotees(tmp_path):
    photos = [photo(tmp_path / f"{i}.jpg", 50, bruit=False) for i in range(4)]
    textes = [b for b in gemini_extract.construire_contenu(photos) if isinstance(b, str)]
    assert textes[:4] == ["Photo 1 sur 4 :", "Photo 2 sur 4 :", "Photo 3 sur 4 :", "Photo 4 sur 4 :"]
    assert "regroupées par l'expert" in textes[-1]


def test_une_bouteille_sans_photo_est_refusee():
    with pytest.raises(ValueError, match="Aucune photo"):
        gemini_extract.construire_contenu([])
