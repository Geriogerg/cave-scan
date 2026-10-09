"""Appariement des photos par ordre de prise de vue (decisions.md 0023).

En cave, l'expert photographie dans l'ordre — étiquette, contre-étiquette,
bouteille suivante — puis dépose tout, à plat, dans un dossier. Ce module
reconstitue les paires, et refuse de deviner (decisions.md 0068) :

- tri par date de prise de vue (EXIF) si TOUTES les photos en ont une, sinon
  par nom de fichier (tri naturel : « photo 2 » avant « photo 10 ») ;
- paires consécutives : 1re photo = étiquette, 2e = contre-étiquette ;
- nombre impair -> arrêt, avec un message explicite : aucun appariement
  silencieux, il faudrait deviner quelle photo manque ;
- photo dans un format que la chaîne ne lit pas (HEIC d'iPhone, TIFF, RAW...)
  -> arrêt, jamais ignorée en silence ;
- photo rangée dans un sous-dossier -> arrêt (l'ancienne convention « un
  sous-dossier par bouteille » est remplacée par 0023).

Les fichiers qui ne sont pas des photos (notes, fichiers système) sont ignorés.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

EXTENSIONS_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Formats photo courants que la chaîne ne lit pas : signalés, jamais ignorés.
EXTENSIONS_NON_LUES = {
    ".heic", ".heif", ".avif", ".tif", ".tiff", ".bmp",
    ".dng", ".raw", ".cr2", ".cr3", ".nef", ".arw",
}

TRI_EXIF = "date de prise de vue (EXIF)"
TRI_NOM = "nom de fichier"

# Étiquettes EXIF : date de prise de vue, sinon date de l'image.
_EXIF_IFD, _DATE_ORIGINALE, _DATE = 0x8769, 0x9003, 0x0132


class PhotosInvalides(ValueError):
    """Le dossier de photos ne permet pas un appariement sûr. Le message dit pourquoi."""


@dataclass(frozen=True)
class PhotosBouteille:
    """Les vues d'UNE bouteille."""

    etiquette: Path
    contre_etiquette: Path | None = None
    autres: list[Path] = field(default_factory=list)

    @property
    def nom(self) -> str:
        if self.contre_etiquette is None:
            return self.etiquette.name
        return f"{self.etiquette.name} + {self.contre_etiquette.name}"

    @property
    def identifiant(self) -> str:
        """Identifiant stable de la bouteille : empreinte du CONTENU de ses photos.

        Le même d'un run à l'autre, insensible au renommage des fichiers — c'est
        ce qui permet de reprendre une campagne ou de retrouver une bouteille
        (decisions.md 0016, 0065). Une photo absente du disque (dry-run sur
        fixtures) contribue par son chemin.
        """
        empreinte = hashlib.sha256()
        for chemin in (self.etiquette, self.contre_etiquette, *self.autres):
            if chemin is None:
                continue
            chemin = Path(chemin)
            empreinte.update(chemin.read_bytes() if chemin.is_file() else str(chemin).encode())
            empreinte.update(b"\0")
        return f"B-{empreinte.hexdigest()[:10].upper()}"


@dataclass(frozen=True)
class Appariement:
    """Les paires reconstituées, et comment elles l'ont été."""

    bouteilles: list[PhotosBouteille]
    tri: str  # TRI_EXIF ou TRI_NOM
    sans_date: list[str] = field(default_factory=list)  # pourquoi on a trié par nom
    dates: dict[Path, datetime | None] = field(default_factory=dict)  # prise de vue, par photo


def apparier_photos(racine: str | Path, sans_contre: bool = False) -> Appariement:
    """Reconstitue les paires étiquette / contre-étiquette d'un dossier à plat.

    `sans_contre` : le dossier ne contient que des étiquettes, une photo par
    bouteille (decisions.md 0108). C'est l'utilisateur qui le dit — l'outil ne
    devine jamais si une photo est une étiquette ou une contre-étiquette.
    """
    racine = Path(racine)
    if not racine.is_dir():
        raise NotADirectoryError(f"Dossier de photos introuvable : {racine}")

    _refuser_les_sous_dossiers(racine)

    fichiers = [chemin for chemin in racine.iterdir() if chemin.is_file()]
    _refuser_les_formats_non_lus(fichiers)

    images = [chemin for chemin in fichiers if chemin.suffix.lower() in EXTENSIONS_IMAGE]
    if not images:
        raise PhotosInvalides(
            f"Aucune photo exploitable sous {racine} "
            f"(extensions reconnues : {', '.join(sorted(EXTENSIONS_IMAGE))})."
        )

    dates = {image: _date_de_prise_de_vue(image) for image in images}
    images, tri, sans_date = _trier(images, dates)

    if sans_contre:
        return Appariement(
            bouteilles=[PhotosBouteille(etiquette=image) for image in images],
            tri=tri,
            sans_date=[c.name for c in sans_date],
            dates=dates,
        )

    if len(images) % 2:
        raise PhotosInvalides(
            f"{len(images)} photos dans {racine} : nombre IMPAIR. Chaque bouteille "
            f"demande une étiquette ET une contre-étiquette, prises dans l'ordre "
            f"(decisions.md 0023). Aucun appariement n'est tenté : il faudrait "
            f"deviner quelle photo manque ou est en trop. Ordre utilisé : {tri}. "
            f"Vérifier le dossier puis relancer — ou, s'il ne contient que des "
            f"étiquettes, relancer avec --sans-contre."
        )

    bouteilles = [
        PhotosBouteille(etiquette=images[rang], contre_etiquette=images[rang + 1])
        for rang in range(0, len(images), 2)
    ]
    return Appariement(
        bouteilles=bouteilles, tri=tri, sans_date=[c.name for c in sans_date], dates=dates
    )


def grouper_photos(racine: str | Path) -> list[PhotosBouteille]:
    """Les bouteilles d'un dossier de photos, dans l'ordre de prise de vue."""
    return apparier_photos(racine).bouteilles


def _refuser_les_sous_dossiers(racine: Path) -> None:
    for sous_dossier in sorted(c for c in racine.iterdir() if c.is_dir()):
        photos = [
            c.name for c in sous_dossier.rglob("*")
            if c.suffix.lower() in EXTENSIONS_IMAGE | EXTENSIONS_NON_LUES
        ]
        if photos:
            raise PhotosInvalides(
                f"Photos rangées dans un sous-dossier ({sous_dossier.name}/ : "
                f"{len(photos)} photo(s)). Les photos se déposent À PLAT dans "
                f"{racine}, dans l'ordre de prise de vue (decisions.md 0023) : "
                f"elles ne seraient sinon jamais lues."
            )


def _refuser_les_formats_non_lus(fichiers: list[Path]) -> None:
    non_lues = sorted(c.name for c in fichiers if c.suffix.lower() in EXTENSIONS_NON_LUES)
    if not non_lues:
        return
    apercu = ", ".join(non_lues[:5]) + (f" (+{len(non_lues) - 5})" if len(non_lues) > 5 else "")
    heic = any(nom.lower().endswith((".heic", ".heif")) for nom in non_lues)
    conseil = (
        " Photos d'iPhone : les exporter en JPEG, ou régler l'appareil sur "
        "Réglages > Appareil photo > Formats > « Le plus compatible »."
        if heic
        else " Les convertir en JPEG ou PNG."
    )
    raise PhotosInvalides(
        f"{len(non_lues)} photo(s) dans un format non lu par la chaîne : {apercu}. "
        f"Formats lus : {', '.join(sorted(EXTENSIONS_IMAGE))}. Elles ne sont pas "
        f"ignorées en silence : l'appariement par paires serait décalé.{conseil}"
    )


def _trier(
    images: list[Path], dates: dict[Path, datetime | None]
) -> tuple[list[Path], str, list[Path]]:
    """Par date EXIF si TOUTES les photos en ont une ; sinon toutes par nom.

    Un tri mixte (dates pour les unes, noms pour les autres) intercalerait les
    photos au hasard : c'est tout l'un ou tout l'autre.
    """
    sans_date = [image for image, date in dates.items() if date is None]
    if not sans_date:
        return (
            sorted(images, key=lambda image: (dates[image], _cle_naturelle(image.name))),
            TRI_EXIF,
            [],
        )
    return sorted(images, key=lambda image: _cle_naturelle(image.name)), TRI_NOM, sans_date


def _cle_naturelle(nom: str) -> list[object]:
    """« photo 2 » avant « photo 10 » : les nombres se comparent comme des nombres."""
    return [int(morceau) if morceau.isdigit() else morceau.casefold() for morceau in re.split(r"(\d+)", nom)]


def _date_de_prise_de_vue(chemin: Path) -> datetime | None:
    """Date EXIF de prise de vue, ou None si absente ou illisible.

    Une photo sans date n'est pas une erreur : elle fait seulement basculer
    TOUT le tri sur les noms de fichier, et le run le dit.
    """
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
