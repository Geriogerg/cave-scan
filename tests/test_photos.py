"""Appariement des photos par ordre (guide, étape 4.4 ; decisions.md 0023, 0068).

Critères d'acceptation : nombre de photos impair refusé, aucun appariement
silencieux. Et le cas HEIC : une photo d'iPhone illisible est signalée
clairement, jamais ignorée en silence.
"""

from __future__ import annotations

import pytest
from PIL import Image

from src.export.excel_writer import a_relire
from src.extract.consignes import INSTRUCTION_FINALE
from src.extract.schema import (
    DOUTE_PAIRE_PHOTOS,
    PHOTOS_MEME_BOUTEILLE,
    from_tool_input,
    tool_schema,
)
from src.io.photos import (
    TRI_EXIF,
    TRI_NOM,
    PhotosInvalides,
    apparier_photos,
    grouper_photos,
)


def photo(dossier, nom, date=None):
    """Une vraie petite image JPEG, avec ou sans date de prise de vue EXIF."""
    image = Image.new("RGB", (8, 8), "white")
    exif = Image.Exif()
    if date:
        exif[0x0132] = date  # DateTime
    chemin = dossier / nom
    image.save(chemin, "JPEG", exif=exif.tobytes())
    return chemin


def noms(appariement):
    return [(b.etiquette.name, b.contre_etiquette.name) for b in appariement.bouteilles]


# --- ordre et paires -------------------------------------------------------------


def test_paires_consecutives_dans_l_ordre_des_noms(tmp_path):
    for i in (4, 1, 3, 2):
        photo(tmp_path, f"IMG_000{i}.jpg")
    appariement = apparier_photos(tmp_path)
    assert appariement.tri == TRI_NOM
    assert noms(appariement) == [("IMG_0001.jpg", "IMG_0002.jpg"), ("IMG_0003.jpg", "IMG_0004.jpg")]


def test_tri_naturel_photo_2_avant_photo_10(tmp_path):
    for i in (10, 1, 2, 11):
        photo(tmp_path, f"photo {i}.jpg")
    assert noms(apparier_photos(tmp_path)) == [("photo 1.jpg", "photo 2.jpg"), ("photo 10.jpg", "photo 11.jpg")]


def test_tri_par_date_exif_quand_toutes_les_photos_en_ont_une(tmp_path):
    """Les noms disent l'inverse des dates : c'est la date de prise de vue qui fait foi."""
    photo(tmp_path, "d.jpg", "2026:10:09 10:00:00")
    photo(tmp_path, "c.jpg", "2026:10:09 10:00:05")
    photo(tmp_path, "b.jpg", "2026:10:09 10:01:00")
    photo(tmp_path, "a.jpg", "2026:10:09 10:01:05")
    appariement = apparier_photos(tmp_path)
    assert appariement.tri == TRI_EXIF
    assert noms(appariement) == [("d.jpg", "c.jpg"), ("b.jpg", "a.jpg")]


def test_une_photo_sans_date_fait_tout_trier_par_nom_et_le_dit(tmp_path):
    """Pas de tri mixte : il intercalerait les photos au hasard."""
    photo(tmp_path, "b.jpg", "2026:10:09 10:00:00")
    photo(tmp_path, "a.jpg")  # sans date
    appariement = apparier_photos(tmp_path)
    assert appariement.tri == TRI_NOM
    assert appariement.sans_date == ["a.jpg"]
    assert noms(appariement) == [("a.jpg", "b.jpg")]


# --- refus explicites : jamais d'appariement silencieux -----------------------------


def test_nombre_impair_refuse(tmp_path):
    """Critère d'acceptation : on ne devine pas quelle photo manque."""
    for i in range(3):
        photo(tmp_path, f"IMG_{i}.jpg")
    with pytest.raises(PhotosInvalides, match="IMPAIR"):
        apparier_photos(tmp_path)


def test_heic_signale_clairement_jamais_ignore(tmp_path):
    """Photos d'iPhone : sans conversion, la chaîne ne les lit pas — on s'arrête,
    on dit pourquoi et comment faire. Les ignorer décalerait toutes les paires."""
    photo(tmp_path, "IMG_0001.jpg")
    photo(tmp_path, "IMG_0002.jpg")
    (tmp_path / "IMG_0003.HEIC").write_bytes(b"ftypheic")
    with pytest.raises(PhotosInvalides) as capture:
        apparier_photos(tmp_path)
    message = str(capture.value)
    assert "IMG_0003.HEIC" in message
    assert "iPhone" in message and "Le plus compatible" in message
    assert "pas ignorées en silence" in message


@pytest.mark.parametrize("extension", [".tiff", ".dng", ".heif"])
def test_autres_formats_non_lus_signales(tmp_path, extension):
    photo(tmp_path, "a.jpg")
    photo(tmp_path, "b.jpg")
    (tmp_path / f"c{extension}").write_bytes(b"x")
    with pytest.raises(PhotosInvalides, match="format non lu"):
        apparier_photos(tmp_path)


def test_photos_dans_un_sous_dossier_refusees(tmp_path):
    """L'ancienne convention : elles ne seraient jamais lues, on le dit."""
    photo(tmp_path, "a.jpg")
    photo(tmp_path, "b.jpg")
    (tmp_path / "bouteille_03").mkdir()
    photo(tmp_path / "bouteille_03", "etiquette.jpg")
    with pytest.raises(PhotosInvalides, match="sous-dossier"):
        apparier_photos(tmp_path)


def test_les_fichiers_qui_ne_sont_pas_des_photos_sont_ignores(tmp_path):
    photo(tmp_path, "a.jpg")
    photo(tmp_path, "b.jpg")
    (tmp_path / "notes.txt").write_text("liste de cave", encoding="utf-8")
    (tmp_path / "vide").mkdir()  # sous-dossier sans photo : sans conséquence
    assert len(grouper_photos(tmp_path)) == 1


def test_dossier_introuvable(tmp_path):
    with pytest.raises(NotADirectoryError):
        apparier_photos(tmp_path / "absent")


# --- paire incohérente selon le modèle -> à vérifier --------------------------------


def test_le_schema_demande_si_c_est_la_meme_bouteille():
    schema = tool_schema()["input_schema"]
    assert PHOTOS_MEME_BOUTEILLE in schema["properties"]
    assert PHOTOS_MEME_BOUTEILLE in schema["required"]


def test_la_consigne_ne_presuppose_plus_la_meme_bouteille():
    """L'affirmer aurait dissuadé le modèle de signaler une erreur d'appariement."""
    assert "censées" in INSTRUCTION_FINALE
    assert PHOTOS_MEME_BOUTEILLE in INSTRUCTION_FINALE


def test_paire_incoherente_signalee_dans_a_verifier():
    bouteille = from_tool_input({"appellation": "Pommard", PHOTOS_MEME_BOUTEILLE: "non"})
    assert DOUTE_PAIRE_PHOTOS in bouteille.champs_a_verifier
    assert "appariement" in bouteille.notes


@pytest.mark.parametrize("reponse", ["oui", "non_determinable", None])
def test_paire_coherente_ou_indeterminee_rien_signale(reponse):
    bouteille = from_tool_input({"appellation": "Pommard", PHOTOS_MEME_BOUTEILLE: reponse})
    assert DOUTE_PAIRE_PHOTOS not in bouteille.champs_a_verifier


def test_une_paire_incoherente_surligne_la_ligne():
    """C'est un doute précis, pas un champ best effort : la ligne est à relire."""
    from src.config.maison import charger_config
    from tests.conftest import RACINE

    config = charger_config(RACINE / "config" / "maisons" / "maison_test.json")
    charge = {PHOTOS_MEME_BOUTEILLE: "non"}
    for colonne in config.colonnes_modele:
        if colonne.type == "liste":
            charge[colonne.cle] = colonne.codes[0]
        elif colonne.type == "nombre":
            charge[colonne.cle] = 1
        else:
            charge[colonne.cle] = "Texte lu"
    assert a_relire(from_tool_input(charge, config), config)


# --- étiquettes seules (decisions.md 0108) ----------------------------------------


def test_sans_contre_chaque_photo_est_une_bouteille(tmp_path):
    from src.extract.fixture_extract import generer_photos_fictives

    dossier = generer_photos_fictives(tmp_path / "photos", 2)
    (dossier / "bouteille_02_contre.jpg").unlink()  # 3 photos : impair, accepté ici

    appariement = apparier_photos(dossier, sans_contre=True)

    assert [vues.contre_etiquette for vues in appariement.bouteilles] == [None, None, None]
    assert [vues.etiquette.name for vues in appariement.bouteilles] == [
        "bouteille_01_etiquette.jpg", "bouteille_01_contre.jpg", "bouteille_02_etiquette.jpg",
    ]


def test_un_nombre_impair_suggere_sans_contre(tmp_path):
    from src.extract.fixture_extract import generer_photos_fictives

    dossier = generer_photos_fictives(tmp_path / "photos", 2)
    (dossier / "bouteille_02_contre.jpg").unlink()
    with pytest.raises(PhotosInvalides, match="--sans-contre"):
        apparier_photos(dossier)
