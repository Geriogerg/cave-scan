"""Les photos d'un dossier, regroupées par bouteille (decisions.md 0166).

Une bouteille = un groupe de photos, tel que l'expert l'a constitué — l'outil ne
devine jamais quelle photo va avec quelle autre :

- une photo posée à la racine du dossier = une bouteille d'une seule photo ;
- un sous-dossier = une bouteille, avec toutes les photos qu'il contient
  (étiquette, contre-étiquette, capsule, bouteille entière…), dans l'ordre
  naturel de leurs noms (« photo 2 » avant « photo 10 ») ;
- les bouteilles suivent l'ordre naturel des noms, photos et sous-dossiers
  mêlés ;
- photo dans un format que la chaîne ne lit pas (TIFF, RAW…), photo HEIC
  illisible, photo rangée deux niveaux plus bas -> arrêt, avec un message
  explicite : jamais ignorée en silence. Le HEIC d'iPhone est lu (0158).

Les fichiers qui ne sont pas des photos (notes, fichiers système) et les
sous-dossiers sans photo sont ignorés.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.io.heic import EXTENSIONS_HEIC, est_heic

EXTENSIONS_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif", *EXTENSIONS_HEIC}

# Formats photo courants que la chaîne ne lit pas : signalés, jamais ignorés.
EXTENSIONS_NON_LUES = {
    ".avif", ".tif", ".tiff", ".bmp",
    ".dng", ".raw", ".cr2", ".cr3", ".nef", ".arw",
}

# Étiquettes EXIF : date de prise de vue, sinon date de l'image.
_EXIF_IFD, _DATE_ORIGINALE, _DATE = 0x8769, 0x9003, 0x0132


class PhotosInvalides(ValueError):
    """Le dossier de photos ne permet pas de former les bouteilles sans deviner.
    Le message dit pourquoi."""


def identifiant_de(photos: Sequence[str | Path]) -> str:
    """Identifiant stable d'une bouteille : empreinte du CONTENU de ses photos,
    dans leur ordre (decisions.md 0016, 0065).

    Le même d'un run à l'autre, insensible au renommage des fichiers. Une photo
    absente du disque (dry-run sur fixtures) contribue par son chemin. Pour une
    bouteille étiquette + contre-étiquette, c'est l'identifiant d'avant les
    groupes : les inventaires existants gardent les leurs.
    """
    empreinte = hashlib.sha256()
    for chemin in photos:
        chemin = Path(chemin)
        empreinte.update(chemin.read_bytes() if chemin.is_file() else str(chemin).encode())
        empreinte.update(b"\0")
    return f"B-{empreinte.hexdigest()[:10].upper()}"


@dataclass(frozen=True)
class PhotosBouteille:
    """Les photos d'UNE bouteille, dans l'ordre de l'expert."""

    photos: tuple[Path, ...]
    nom: str  # le nom de la photo seule, ou du sous-dossier

    @property
    def identifiant(self) -> str:
        return identifiant_de(self.photos)


@dataclass(frozen=True)
class Regroupement:
    """Les bouteilles d'un dossier, et la date de prise de vue de chaque photo
    (gardée pour information : elle ne décide plus de rien)."""

    bouteilles: list[PhotosBouteille]
    dates: dict[Path, datetime | None] = field(default_factory=dict)


def grouper_photos(racine: str | Path) -> Regroupement:
    """Les bouteilles d'un dossier : une par photo à la racine, une par
    sous-dossier. Lève `PhotosInvalides` plutôt que de deviner."""
    racine = Path(racine)
    if not racine.is_dir():
        raise NotADirectoryError(f"Dossier de photos introuvable : {racine}")

    entrees = sorted(racine.iterdir(), key=lambda chemin: _cle_naturelle(chemin.name))
    _refuser_les_formats_non_lus(racine, [c for c in entrees if c.is_file()])
    bouteilles: list[PhotosBouteille] = []
    for entree in entrees:
        if entree.is_file() and entree.suffix.lower() in EXTENSIONS_IMAGE:
            bouteilles.append(PhotosBouteille(photos=(entree,), nom=entree.name))
        elif entree.is_dir():
            photos = _photos_du_sous_dossier(entree)
            if photos:
                bouteilles.append(PhotosBouteille(photos=tuple(photos), nom=f"{entree.name}/"))

    if not bouteilles:
        raise PhotosInvalides(
            f"Aucune photo exploitable sous {racine} (extensions reconnues : "
            f"{', '.join(sorted(EXTENSIONS_IMAGE))}). Une photo à la racine = une bouteille ; "
            f"un sous-dossier = une bouteille et toutes ses photos."
        )
    toutes = [photo for bouteille in bouteilles for photo in bouteille.photos]
    _refuser_les_heic_illisibles(toutes)
    return Regroupement(bouteilles=bouteilles, dates={photo: _date_de_prise_de_vue(photo) for photo in toutes})


def _photos_du_sous_dossier(dossier: Path) -> list[Path]:
    """Les photos d'un sous-dossier (= une bouteille), dans l'ordre naturel."""
    for profond in sorted(c for c in dossier.iterdir() if c.is_dir()):
        perdues = [c.name for c in profond.rglob("*") if c.suffix.lower() in EXTENSIONS_IMAGE | EXTENSIONS_NON_LUES]
        if perdues:
            raise PhotosInvalides(
                f"Photos rangées trop profond ({dossier.name}/{profond.name}/ : {len(perdues)} photo(s)). "
                f"Un sous-dossier par bouteille, ses photos directement dedans : sinon elles ne "
                f"seraient jamais lues."
            )
    fichiers = [c for c in dossier.iterdir() if c.is_file()]
    _refuser_les_formats_non_lus(dossier, fichiers)
    return sorted(
        (c for c in fichiers if c.suffix.lower() in EXTENSIONS_IMAGE), key=lambda c: _cle_naturelle(c.name)
    )


def _refuser_les_formats_non_lus(dossier: Path, fichiers: list[Path]) -> None:
    non_lues = sorted(c.name for c in fichiers if c.suffix.lower() in EXTENSIONS_NON_LUES)
    if not non_lues:
        return
    apercu = ", ".join(non_lues[:5]) + (f" (+{len(non_lues) - 5})" if len(non_lues) > 5 else "")
    raise PhotosInvalides(
        f"{len(non_lues)} photo(s) dans un format non lu par la chaîne ({dossier.name}) : {apercu}. "
        f"Formats lus : {', '.join(sorted(EXTENSIONS_IMAGE))}. Elles ne sont pas ignorées en "
        f"silence : une bouteille perdrait une photo. Les convertir en JPEG ou PNG."
    )


def _refuser_les_heic_illisibles(images: list[Path]) -> None:
    """Une photo HEIC est convertie en JPEG pour le modèle : elle doit pouvoir être
    décodée. Vérifié AVANT tout appel, comme le reste du dossier."""
    from PIL import Image, UnidentifiedImageError

    illisibles = []
    for image in images:
        if not est_heic(image):
            continue
        try:
            with Image.open(image) as ouverte:
                ouverte.verify()
        except (OSError, UnidentifiedImageError, ValueError, SyntaxError):
            illisibles.append(image.name)
    if illisibles:
        raise PhotosInvalides(
            f"{len(illisibles)} photo(s) HEIC illisible(s) : {', '.join(illisibles[:5])}. "
            f"Fichier abîmé ou incomplet : la recopier depuis le téléphone, ou l'exporter en JPEG."
        )


def _cle_naturelle(nom: str) -> list[object]:
    """« photo 2 » avant « photo 10 » : les nombres se comparent comme des nombres."""
    return [int(morceau) if morceau.isdigit() else morceau.casefold() for morceau in re.split(r"(\d+)", nom)]


def _date_de_prise_de_vue(chemin: Path) -> datetime | None:
    """Date EXIF de prise de vue, ou None si absente ou illisible. Information
    seulement : l'ordre des bouteilles ne dépend plus des dates (0166)."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(chemin) as image:
            exif = image.getexif()
            brute = exif.get_ifd(_EXIF_IFD).get(_DATE_ORIGINALE) or exif.get(_DATE)
    except (OSError, UnidentifiedImageError, ValueError):
        return None
    if not brute:
        return None
    try:
        return datetime.strptime(str(brute).strip().rstrip("\x00"), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


# Publics pour le dépôt par l'application web : même lecture de date et même
# ordre naturel que le regroupement d'un dossier.
date_de_prise_de_vue = _date_de_prise_de_vue
cle_naturelle = _cle_naturelle
