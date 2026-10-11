"""Photos HEIC d'iPhone (decisions.md 0158) : lues au dépôt, stockées telles
quelles, affichées et envoyées au modèle en JPEG, sans aucune métadonnée."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from src.extract.consignes import lire_photo
from src.io.heic import en_jpeg
from src.services.envoi import EnvoiRefuse, photo_a_servir, verifier_image

GPS_IFD = 0x8825


def heic(chemin: Path, couleur=(180, 20, 40), avec_gps: bool = True) -> Path:
    """Une vraie photo HEIC, avec un EXIF qui porte une position GPS."""
    image = Image.new("RGB", (40, 30), couleur)
    exif = Image.Exif()
    exif[0x010F] = "Apple"  # fabricant
    if avec_gps:
        exif.get_ifd(GPS_IFD)[2] = (48.0, 51.0, 24.0)  # latitude de la cave
    image.save(chemin, format="HEIF", exif=exif.tobytes())
    return chemin


def test_verifier_image_reconnait_le_heic_par_son_contenu(tmp_path):
    assert verifier_image(heic(tmp_path / "IMG_0001.HEIC"), "IMG_0001.HEIC") == ".heic"
    # Même nommée .jpg, une photo HEIC est reconnue pour ce qu'elle est.
    assert verifier_image(heic(tmp_path / "trompeuse.jpg"), "trompeuse.jpg") == ".heic"


def test_un_heic_illisible_est_refuse_avec_sa_raison(tmp_path):
    abime = tmp_path / "IMG_0002.HEIC"
    abime.write_bytes(b"\x00\x00\x00\x18ftypheic tronque")
    with pytest.raises(EnvoiRefuse, match="n'est pas une image lisible"):
        verifier_image(abime, "IMG_0002.HEIC")


def test_le_modele_recoit_un_jpeg_sans_metadonnees(tmp_path):
    """Les deux fournisseurs reçoivent la même image ; l'un n'accepte pas le HEIC.
    Et la position GPS de la cave ne part jamais chez un fournisseur."""
    source = heic(tmp_path / "IMG_0003.HEIC")
    octets, type_mime = lire_photo(source)
    assert type_mime == "image/jpeg"
    with Image.open(io.BytesIO(octets)) as envoyee:
        assert envoyee.format == "JPEG" and envoyee.size == (40, 30)
        assert dict(envoyee.getexif()) == {}
    assert source.read_bytes()[4:12] == b"ftypheic"  # le fichier stocké n'a pas changé


def test_une_photo_jpeg_part_telle_quelle(tmp_path):
    jpeg = tmp_path / "a.jpg"
    Image.new("RGB", (8, 8), "white").save(jpeg, "JPEG")
    assert lire_photo(jpeg) == (jpeg.read_bytes(), "image/jpeg")


def test_conversion_orientee_comme_a_l_ecran(tmp_path):
    """Une photo prise téléphone tourné : l'orientation EXIF est appliquée."""
    image = Image.new("RGB", (40, 20), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotation de 90° à l'affichage
    chemin = tmp_path / "IMG_0004.HEIC"
    image.save(chemin, format="HEIF", exif=exif.tobytes())
    with Image.open(io.BytesIO(en_jpeg(chemin))) as convertie:
        assert convertie.size == (20, 40)


def test_le_depot_stocke_le_heic_et_l_affiche_en_jpeg(session, stockage, nom_maison, tmp_path):
    from src.donnees.modeles import Photo
    from src.services.depot import ajouter_photo, creer_brouillon
    from tests.conftest import CONFIG_TEST

    inventaire_id = creer_brouillon(session, nom_maison, CONFIG_TEST, "iPhone").inventaire_id
    source = heic(tmp_path / "IMG_0005.HEIC")
    recue = ajouter_photo(
        session, inventaire_id, io.BytesIO(source.read_bytes()), "IMG_0005.HEIC", stockage, bouteille="b1", numero=1
    )
    photo = session.get(Photo, recue.photo_id)
    assert photo.chemin.endswith(".heic")
    assert (stockage / photo.chemin).read_bytes() == source.read_bytes()  # stockée telle quelle
    for taille in ("miniature", "reduite", "originale"):
        with Image.open(io.BytesIO(photo_a_servir(session, stockage, inventaire_id, photo.id, taille))) as servie:
            assert servie.format == "JPEG" and dict(servie.getexif()) == {}
