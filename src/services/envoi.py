"""Photos par l'API : réception d'un envoi, diffusion sans métadonnées.

Réception (decisions.md 0116, 0166) : chaque fichier est réellement OUVERT pour
vérifier que c'est une image, sa taille et le nombre de fichiers sont bornés,
son nom est nettoyé ; les photos forment des bouteilles dans l'ORDRE D'ENVOI —
une par photo, ou selon `photos_par_bouteille` (« 2,2,1 ») — et l'inventaire est
créé par les mêmes garde-fous qu'en ligne de commande (plafond de photos,
doublons), mêmes messages.

Diffusion (0117) : une photo n'est servie que si elle appartient à
l'inventaire demandé, rotation EXIF appliquée, et toujours RÉENCODÉE sans
aucune métadonnée — l'EXIF peut porter la position GPS de la cave du client.
Le fichier stocké, lui, reste intact.
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.maison import ConfigInvalide, empreinte_config, lire_config, plier
from src.io import heic  # noqa: F401 — rend le HEIC d'iPhone lisible par Pillow (0158)
from src.donnees.modeles import ConfigVersion, Maison, Photo
from src.donnees.stockage import chemin_stocke
from src.io.photos import PhotosBouteille, Regroupement, date_de_prise_de_vue
from src.services.inventaires import InventaireCree, charger_inventaire, creer_inventaire_depuis_groupes

TAILLE_MAX_OCTETS = 30 * 1024 * 1024  # par photo : large pour un téléphone récent
NOMBRE_MAX = 800  # par inventaire : au moins 600 photos = 300 bouteilles (guide)
# Format lu par Pillow -> extension du fichier stocké. MPO : JPEG de certains
# téléphones ; HEIF : HEIC d'iPhone, stocké tel quel (decisions.md 0158).
FORMATS_ACCEPTES = {"JPEG": ".jpg", "MPO": ".jpg", "PNG": ".png", "HEIF": ".heic"}
# Extension d'un nom de fichier -> extension correspondant à son contenu.
FAMILLES = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".heic": ".heic", ".heif": ".heic"}
TAILLE_REDUITE = 1600  # côté le plus long, pour l'affichage


class EnvoiRefuse(ValueError):
    """L'envoi ne peut pas être accepté. Le message dit pourquoi, pour l'expert."""


class PhotoIntrouvable(LookupError):
    pass


# --- maisons et configs disponibles ---------------------------------------------------------


@dataclass(frozen=True)
class ConfigDisponible:
    maison: str
    fichier: str
    version_declaree: int | None
    config_numero: int | None  # version enregistrée en base qui a ce contenu ; None = jamais utilisée
    erreur: str | None = None


def configs_disponibles(session: Session, dossier_configs: Path) -> list[ConfigDisponible]:
    """Les maisons qu'on peut choisir pour un nouvel inventaire, avec la version de
    leur config ACTIVE : celle du fichier aujourd'hui."""
    disponibles = []
    for fichier in sorted(Path(dossier_configs).glob("*.json")):
        try:
            config, texte = lire_config(fichier)
        except ConfigInvalide as erreur:
            disponibles.append(ConfigDisponible("?", fichier.name, None, None, str(erreur)))
            continue
        numero = session.scalar(
            select(ConfigVersion.numero)
            .join(Maison, Maison.id == ConfigVersion.maison_id)
            .where(Maison.nom == config.maison, ConfigVersion.empreinte == empreinte_config(texte))
        )
        disponibles.append(ConfigDisponible(config.maison, fichier.name, config.version, numero))
    return disponibles


def config_de_la_maison(dossier_configs: Path, maison: str) -> Path:
    for fichier in sorted(Path(dossier_configs).glob("*.json")):
        try:
            config, _ = lire_config(fichier)
        except ConfigInvalide:
            continue
        if plier(config.maison) == plier(maison):
            return fichier
    raise EnvoiRefuse(f"Aucune config pour la maison « {maison} » : ajouter son fichier dans config/maisons/.")


# --- réception -----------------------------------------------------------------------------


def creer_inventaire_depuis_envoi(
    session: Session,
    maison: str,
    nom: str,
    fichiers: Iterable[tuple[str, BinaryIO]],
    stockage: Path,
    dossier_configs: Path,
    photos_par_bouteille: str | None = None,
    taille_max: int | None = None,
    nombre_max: int | None = None,
) -> InventaireCree:
    """Crée un inventaire à partir de fichiers envoyés (nom d'origine, contenu),
    dans l'ordre d'envoi. `photos_par_bouteille` : « 2,2,1 » = les deux premières
    photos forment la bouteille 1, les deux suivantes la bouteille 2, la
    dernière la bouteille 3 ; sans lui, une photo par bouteille."""
    taille_max = taille_max or TAILLE_MAX_OCTETS
    nombre_max = nombre_max or NOMBRE_MAX
    if not nom.strip():
        raise EnvoiRefuse("Donnez un nom à la vente : il ne peut pas rester vide.")
    fichiers = list(fichiers)
    if not fichiers:
        raise EnvoiRefuse("Aucune photo envoyée.")
    if len(fichiers) > nombre_max:
        raise EnvoiRefuse(f"{len(fichiers)} photos envoyées : {nombre_max} au maximum par inventaire.")
    tailles = _tailles_des_bouteilles(photos_par_bouteille, len(fichiers))
    config_path = config_de_la_maison(dossier_configs, maison)

    with tempfile.TemporaryDirectory(prefix="cave-scan-envoi-") as temporaire:
        recus = []
        for rang, (nom_origine, flux) in enumerate(fichiers, start=1):
            dossier = Path(temporaire) / f"{rang:04d}"  # un dossier par photo : deux « image.jpg » cohabitent
            dossier.mkdir()
            cible = dossier / _nom_sur(nom_origine)
            _copier_borne(flux, cible, taille_max, nom_origine)
            recus.append(_verifier_image(cible, nom_origine))
        bouteilles, debut = [], 0
        for taille in tailles:
            photos = tuple(recus[debut : debut + taille])
            bouteilles.append(PhotosBouteille(photos=photos, nom=" + ".join(p.name for p in photos)))
            debut += taille
        regroupement = Regroupement(bouteilles=bouteilles, dates={p: date_de_prise_de_vue(p) for p in recus})
        return creer_inventaire_depuis_groupes(session, maison, config_path, regroupement, nom.strip(), stockage)


def _tailles_des_bouteilles(photos_par_bouteille: str | None, nombre: int) -> list[int]:
    """« 2,2,1 » -> [2, 2, 1] ; vide : une photo par bouteille. La somme doit être
    exactement le nombre de photos envoyées : on ne devine jamais."""
    if not (photos_par_bouteille or "").strip():
        return [1] * nombre
    try:
        tailles = [int(morceau) for morceau in photos_par_bouteille.split(",")]
    except ValueError:
        raise EnvoiRefuse(
            f"« photos_par_bouteille » : des nombres séparés par des virgules sont attendus (reçu « {photos_par_bouteille} »)."
        ) from None
    if any(taille < 1 for taille in tailles) or sum(tailles) != nombre:
        raise EnvoiRefuse(
            f"« photos_par_bouteille » ({photos_par_bouteille}) ne correspond pas aux {nombre} photos envoyées : "
            f"chaque bouteille a au moins une photo, et le total doit être {nombre}."
        )
    return tailles


def _nom_sur(nom_origine: str) -> str:
    """Le nom du fichier sans aucun chemin ni caractère exotique."""
    nom = Path(str(nom_origine).replace("\\", "/")).name
    return re.sub(r"[^\w .()\-]", "_", nom).strip(" .") or "photo"


def _copier_borne(flux: BinaryIO, cible: Path, taille_max: int, nom_origine: str) -> None:
    copie = 0
    with open(cible, "wb") as sortie:
        while bloc := flux.read(1024 * 1024):
            copie += len(bloc)
            if copie > taille_max:
                raise EnvoiRefuse(
                    f"« {nom_origine} » dépasse {taille_max // (1024 * 1024)} Mo : trop lourde pour une photo d'étiquette."
                )
            sortie.write(bloc)


def _verifier_image(chemin: Path, nom_origine: str) -> Path:
    """L'image vérifiée, sous une extension qui correspond à son contenu."""
    attendue = verifier_image(chemin, nom_origine)
    if FAMILLES.get(chemin.suffix.lower()) != attendue:
        # Extension absente ou trompeuse : on la corrige ; l'envoi au modèle se
        # fie à l'extension pour convertir un HEIC.
        corrige = chemin.with_name(chemin.name + attendue)
        shutil.move(chemin, corrige)
        return corrige
    return chemin


def verifier_image(chemin: Path, nom_origine: str) -> str:
    """Le fichier est-il vraiment une image JPEG, PNG ou HEIC ? On l'OUVRE pour le
    savoir. Renvoie l'extension qui correspond à son contenu (« .jpg », « .png »
    ou « .heic »)."""
    try:
        with Image.open(chemin) as image:
            format_lu = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise EnvoiRefuse(f"« {nom_origine} » n'est pas une image lisible (JPEG, PNG ou HEIC attendu).") from None
    if format_lu not in FORMATS_ACCEPTES:
        raise EnvoiRefuse(f"« {nom_origine} » est au format {format_lu} : JPEG, PNG ou HEIC attendu.")
    return FORMATS_ACCEPTES[format_lu]


# --- diffusion ----------------------------------------------------------------------------


TAILLES = ("miniature", "reduite", "originale")


def photo_a_servir(
    session: Session, stockage: Path, inventaire_id: int, photo_id: int, taille: str = "reduite"
) -> bytes:
    """La photo en JPEG, rotation appliquée, SANS aucune métadonnée : miniature
    (préparée à la réception), réduite pour l'affichage, ou pleine taille."""
    if taille not in TAILLES:
        raise ValueError(f"taille inconnue : {taille}")
    charger_inventaire(session, inventaire_id)
    photo = session.get(Photo, photo_id)
    if photo is None or photo.inventaire_id != inventaire_id:
        raise PhotoIntrouvable(f"Aucune photo n°{photo_id} dans l'inventaire n°{inventaire_id}.")
    if taille == "miniature":
        return miniature(stockage, photo.chemin, photo.empreinte).read_bytes()
    if taille == "reduite":
        return reduite(stockage, photo.chemin, photo.empreinte).read_bytes()
    return _sans_metadonnees(chemin_stocke(stockage, photo.chemin), None)


TAILLE_MINIATURE = 480


def miniature(stockage: Path, relatif: str, empreinte: str) -> Path:
    """La miniature d'une photo stockée, créée au besoin (decisions.md 0133) :
    préparée une fois, à la réception, puis servie telle quelle."""
    return _derivee(stockage, relatif, empreinte, "miniatures", TAILLE_MINIATURE, 80)


def reduite(stockage: Path, relatif: str, empreinte: str) -> Path:
    """La version d'affichage (relecture), préparée à la première demande puis
    servie telle quelle : passer à la bouteille suivante ne réencode rien
    (decisions.md 0148)."""
    return _derivee(stockage, relatif, empreinte, "reduites", TAILLE_REDUITE, 85)


def _derivee(stockage: Path, relatif: str, empreinte: str, dossier: str, cote_max: int, qualite: int) -> Path:
    """Une version dérivée, SANS métadonnées, écrite une fois. Deux demandes
    simultanées (préchargement et affichage) écrivent chacune leur fichier
    partiel ; la première arrivée gagne, rien n'est jamais servi à moitié."""
    chemin = Path(stockage) / dossier / f"{empreinte}.jpg"
    if not chemin.exists():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        partiel = chemin.with_name(f"{empreinte}.{uuid.uuid4().hex}.partiel")
        partiel.write_bytes(_sans_metadonnees(chemin_stocke(stockage, relatif), cote_max, qualite=qualite))
        try:
            partiel.replace(chemin)
        except OSError:  # Windows : la version déjà écrite par l'autre demande est en cours de lecture
            partiel.unlink(missing_ok=True)
            if not chemin.exists():
                raise
    return chemin


def _sans_metadonnees(source: Path, cote_max: int | None, qualite: int | None = None) -> bytes:
    with Image.open(source) as originale:
        image = ImageOps.exif_transpose(originale).convert("RGB")
    if cote_max:
        image.thumbnail((cote_max, cote_max))
    sortie = io.BytesIO()
    # Ni `exif=` ni `icc_profile=` ni XMP : Pillow n'écrit alors aucune métadonnée.
    image.save(sortie, "JPEG", quality=qualite or (85 if cote_max else 95))
    return sortie.getvalue()
