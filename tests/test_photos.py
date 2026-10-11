"""Les photos d'un dossier, regroupées par bouteille (decisions.md 0166 ; avant :
appariement par ordre, 0023, 0068).

Une photo à la racine = une bouteille ; un sous-dossier = une bouteille et
toutes ses photos. Jamais de regroupement deviné, jamais de photo ignorée en
silence (format non lu, HEIC illisible, photo rangée trop profond).
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
from src.io.photos import PhotosInvalides, grouper_photos, identifiant_de


def photo(dossier, nom, date=None, couleur="white"):
    """Une vraie petite image JPEG, avec ou sans date de prise de vue EXIF."""
    dossier.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (8, 8), couleur)
    exif = Image.Exif()
    if date:
        exif[0x0132] = date  # DateTime
    chemin = dossier / nom
    image.save(chemin, "JPEG", exif=exif.tobytes())
    return chemin


def noms(regroupement):
    return [[p.name for p in b.photos] for b in regroupement.bouteilles]


# --- une bouteille = une photo à la racine, ou un sous-dossier --------------------------


def test_une_photo_a_la_racine_est_une_bouteille(tmp_path):
    for i in (3, 1, 2):
        photo(tmp_path, f"IMG_000{i}.jpg")
    assert noms(grouper_photos(tmp_path)) == [["IMG_0001.jpg"], ["IMG_0002.jpg"], ["IMG_0003.jpg"]]


def test_un_sous_dossier_est_une_bouteille_avec_toutes_ses_photos(tmp_path):
    for nom in ("3 capsule.jpg", "1 etiquette.jpg", "2 contre.jpg", "4 bouteille entiere.jpg"):
        photo(tmp_path / "bouteille_01", nom)
    photo(tmp_path / "bouteille_02", "etiquette.jpg")
    regroupement = grouper_photos(tmp_path)
    assert noms(regroupement) == [
        ["1 etiquette.jpg", "2 contre.jpg", "3 capsule.jpg", "4 bouteille entiere.jpg"],
        ["etiquette.jpg"],
    ]
    assert [b.nom for b in regroupement.bouteilles] == ["bouteille_01/", "bouteille_02/"]


def test_tri_naturel_photos_et_sous_dossiers_meles(tmp_path):
    """« 2 » avant « 10 » ; photos et sous-dossiers suivent le même ordre."""
    photo(tmp_path, "10.jpg")
    photo(tmp_path / "2", "a.jpg")
    photo(tmp_path / "2", "b.jpg")
    photo(tmp_path, "1.jpg")
    assert noms(grouper_photos(tmp_path)) == [["1.jpg"], ["a.jpg", "b.jpg"], ["10.jpg"]]


def test_la_date_de_prise_de_vue_ne_decide_plus_de_l_ordre(tmp_path):
    """Les dates disent l'inverse des noms : c'est l'expert qui range, pas l'outil."""
    photo(tmp_path, "a.jpg", "2026:10:09 10:01:00")
    photo(tmp_path, "b.jpg", "2026:10:09 10:00:00")
    regroupement = grouper_photos(tmp_path)
    assert noms(regroupement) == [["a.jpg"], ["b.jpg"]]
    assert regroupement.dates[tmp_path / "a.jpg"] is not None  # gardée pour information


# --- refus explicites : jamais de photo perdue en silence --------------------------------


def test_heic_d_iphone_lu_comme_les_autres_photos(tmp_path):
    """Photos d'iPhone : lues (decisions.md 0158)."""
    photo(tmp_path / "bouteille", "IMG_0001.jpg")
    Image.new("RGB", (8, 8), "red").save(tmp_path / "bouteille" / "IMG_0002.HEIC", format="HEIF")
    assert noms(grouper_photos(tmp_path)) == [["IMG_0001.jpg", "IMG_0002.HEIC"]]


def test_heic_illisible_signale_jamais_ignore(tmp_path):
    """Un HEIC abîmé ne pourrait pas être converti pour le modèle : on s'arrête
    AVANT tout appel, on dit lequel."""
    photo(tmp_path, "IMG_0001.jpg")
    (tmp_path / "IMG_0002.HEIC").write_bytes(b"ftypheic")
    with pytest.raises(PhotosInvalides, match="HEIC illisible") as capture:
        grouper_photos(tmp_path)
    assert "IMG_0002.HEIC" in str(capture.value)


@pytest.mark.parametrize("extension", [".tiff", ".dng", ".avif"])
def test_autres_formats_non_lus_signales(tmp_path, extension):
    photo(tmp_path, "a.jpg")
    (tmp_path / f"c{extension}").write_bytes(b"x")
    with pytest.raises(PhotosInvalides, match="format non lu"):
        grouper_photos(tmp_path)


def test_un_format_non_lu_dans_un_sous_dossier_est_signale(tmp_path):
    photo(tmp_path / "bouteille_01", "etiquette.jpg")
    (tmp_path / "bouteille_01" / "capsule.dng").write_bytes(b"x")
    with pytest.raises(PhotosInvalides, match="bouteille_01"):
        grouper_photos(tmp_path)


def test_photos_rangees_trop_profond_refusees(tmp_path):
    """Elles ne seraient jamais lues : on le dit."""
    photo(tmp_path / "bouteille_01", "etiquette.jpg")
    photo(tmp_path / "bouteille_01" / "details", "capsule.jpg")
    with pytest.raises(PhotosInvalides, match="trop profond"):
        grouper_photos(tmp_path)


def test_les_fichiers_qui_ne_sont_pas_des_photos_sont_ignores(tmp_path):
    photo(tmp_path, "a.jpg")
    (tmp_path / "notes.txt").write_text("liste de cave", encoding="utf-8")
    (tmp_path / "vide").mkdir()  # sous-dossier sans photo : sans conséquence
    assert noms(grouper_photos(tmp_path)) == [["a.jpg"]]


def test_un_dossier_sans_photo_est_refuse(tmp_path):
    (tmp_path / "notes.txt").write_text("rien", encoding="utf-8")
    with pytest.raises(PhotosInvalides, match="Aucune photo"):
        grouper_photos(tmp_path)


def test_dossier_introuvable(tmp_path):
    with pytest.raises(NotADirectoryError):
        grouper_photos(tmp_path / "absent")


# --- identifiant stable (decisions.md 0065) ------------------------------------------------


def test_l_identifiant_suit_le_contenu_et_l_ordre_des_photos(tmp_path):
    a = photo(tmp_path, "a.jpg", couleur="red")
    b = photo(tmp_path, "b.jpg", couleur="blue")
    avant = identifiant_de([a, b])
    assert identifiant_de([b, a]) != avant  # l'ordre des photos compte
    renommee = a.rename(tmp_path / "renommee.jpg")
    assert identifiant_de([renommee, b]) == avant  # le nom des fichiers, non


# --- photos d'une autre bouteille selon le modèle -> à vérifier -------------------------------


def test_le_schema_demande_si_c_est_la_meme_bouteille():
    schema = tool_schema()["input_schema"]
    assert PHOTOS_MEME_BOUTEILLE in schema["properties"]
    assert PHOTOS_MEME_BOUTEILLE in schema["required"]


def test_la_consigne_ne_presuppose_plus_la_meme_bouteille():
    """L'affirmer aurait dissuadé le modèle de signaler une erreur de regroupement."""
    assert "censées" in INSTRUCTION_FINALE
    assert PHOTOS_MEME_BOUTEILLE in INSTRUCTION_FINALE


def test_paire_incoherente_signalee_dans_a_verifier():
    bouteille = from_tool_input({"appellation": "Pommard", PHOTOS_MEME_BOUTEILLE: "non"})
    assert DOUTE_PAIRE_PHOTOS in bouteille.champs_a_verifier
    assert "regroupement" in bouteille.notes


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


# --- les photos fictives du dry-run ------------------------------------------------------


def test_les_photos_fictives_forment_des_bouteilles_de_deux_photos(tmp_path):
    from src.extract.fixture_extract import generer_photos_fictives

    dossier = generer_photos_fictives(tmp_path / "photos", 3)
    assert noms(grouper_photos(dossier)) == [["1_etiquette.jpg", "2_contre.jpg"]] * 3
