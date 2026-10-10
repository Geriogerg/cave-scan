"""Dépôt des photos d'un inventaire en BROUILLON, une par une (decisions.md 0126-0134).

Le parcours de l'expert : créer le brouillon (nom, maison), envoyer les photos —
en plusieurs fois, sur un réseau qui coupe —, vérifier et corriger l'ordre des
paires, puis FINALISER : les paires deviennent des bouteilles et l'extraction
démarre. Ensuite, plus aucune photo ne bouge.

Fonctions de service, utilisées à la fois par les pages et par l'API JSON. Tout
garde-fou est vérifié ICI, côté serveur, même si le navigateur l'affiche aussi.

Concurrence : chaque modification commence par prendre le verrou d'écriture sur
la ligne de l'inventaire (`_verrouiller`), pour que deux photos arrivant en même
temps reçoivent deux positions distinctes (0134).
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.config.maison import lire_config, plier
from src.donnees.modeles import FicheBouteille, Inventaire, Photo, maintenant
from src.donnees.stockage import chemin_stocke, empreinte_fichier, stocker
from src.io.photos import PhotosBouteille, cle_naturelle, date_de_prise_de_vue
from src.services import envoi
from src.services.envoi import EnvoiRefuse, verifier_image
from src.services.inventaires import _maison, _version_de_config, charger_inventaire
from src.services.pilotage import LancementRefuse

TRI_DATE = "date de prise de vue"
TRI_NOM = "nom de fichier"
TRI_MANUEL = "ordre corrigé à la main"


class DepotFerme(ValueError):
    """L'inventaire n'est plus un brouillon : ses photos ne bougent plus."""


class ModificationRefusee(ValueError):
    """Déplacement ou inversion impossible (position hors liste, paire incomplète…)."""


# --- créer le brouillon --------------------------------------------------------------------------


@dataclass(frozen=True)
class BrouillonCree:
    inventaire_id: int
    config_numero: int
    nouvelle_config: bool
    avertissements: list[str] = field(default_factory=list)


def creer_brouillon(
    session: Session, maison: str, config_path: str | Path, nom: str, sans_contre: bool = False
) -> BrouillonCree:
    """Un inventaire vide en brouillon. La config de la maison est figée dès
    maintenant, comme pour un inventaire créé d'un coup (decisions.md 0073)."""
    if not nom.strip():
        raise EnvoiRefuse("Donner un nom à l'inventaire.")
    config, texte = lire_config(config_path)
    if plier(config.maison) != plier(maison):
        raise EnvoiRefuse(f"La config {Path(config_path).name} décrit « {config.maison} », pas « {maison} ».")
    maison_bd = _maison(session, config.maison)
    version, nouvelle, avertissements = _version_de_config(
        session, maison_bd, config, texte, Path(config_path).name
    )
    inventaire = Inventaire(
        maison=maison_bd, config_version=version, nom=nom.strip(), statut="brouillon", sans_contre=sans_contre
    )
    session.add(inventaire)
    session.commit()
    return BrouillonCree(inventaire.id, version.numero, nouvelle, [*config.avertissements, *avertissements])


# --- recevoir une photo ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PhotoRecue:
    photo_id: int
    position: int
    nom: str
    deja_recue: bool  # même contenu ou même fichier d'origine : rien n'a été ajouté
    prise_de_vue: datetime | None


def ajouter_photo(
    session: Session,
    inventaire_id: int,
    flux: BinaryIO,
    nom_origine: str,
    stockage: Path,
    prise_de_vue: datetime | None = None,
    signature: str | None = None,
) -> PhotoRecue:
    """Ajoute UNE photo au brouillon. Idempotent : une photo déjà reçue (même
    contenu, ou même fichier d'origine) n'est jamais enregistrée deux fois.

    `prise_de_vue` : la date lue par le navigateur AVANT toute réduction
    (decisions.md 0129) ; à défaut, celle du fichier reçu. Refus avec une raison
    claire : pas une image, HEIC, trop lourde, trop de photos, plus un brouillon.
    """
    _brouillon(session, inventaire_id)  # refuser tôt, avant de lire le fichier
    nom_origine = Path(str(nom_origine or "photo").replace("\\", "/")).name or "photo"

    with tempfile.TemporaryDirectory(prefix="cave-scan-depot-") as temporaire:
        brut = Path(temporaire) / f"recue{Path(nom_origine).suffix.lower()}"
        envoi._copier_borne(flux, brut, envoi.TAILLE_MAX_OCTETS, nom_origine)
        extension = verifier_image(brut, nom_origine)
        fichier = brut.rename(brut.with_suffix(extension))
        empreinte = empreinte_fichier(fichier)
        date = prise_de_vue or date_de_prise_de_vue(fichier)
        relatif = stocker(fichier, stockage, empreinte)
    envoi.miniature(stockage, relatif, empreinte)

    inventaire = _verrouiller(session, inventaire_id)
    deja = session.scalar(
        select(Photo).where(Photo.inventaire_id == inventaire_id, Photo.empreinte == empreinte)
    ) or (
        session.scalar(select(Photo).where(Photo.inventaire_id == inventaire_id, Photo.signature_envoi == signature))
        if signature
        else None
    )
    if deja is not None:
        session.commit()
        return PhotoRecue(deja.id, deja.ordre, deja.nom_origine, True, deja.prise_de_vue)

    photos = _photos(session, inventaire_id)
    if len(photos) >= envoi.NOMBRE_MAX:
        session.rollback()
        raise EnvoiRefuse(f"Cet inventaire a déjà {len(photos)} photos : {envoi.NOMBRE_MAX} au maximum.")
    photo = Photo(
        inventaire_id=inventaire_id,
        chemin=relatif,
        empreinte=empreinte,
        nom_origine=nom_origine[:255],
        prise_de_vue=date,
        ordre=len(photos) + 1,  # à la fin ; le tri automatique la replace
        signature_envoi=(signature or None) and signature[:300],
    )
    session.add(photo)
    session.flush()
    if not inventaire.ordre_manuel:
        _renumeroter(session, _ordre_automatique([*photos, photo]))
    session.commit()
    return PhotoRecue(photo.id, photo.ordre, photo.nom_origine, False, photo.prise_de_vue)


def signatures_deja_recues(session: Session, inventaire_id: int, signatures: Sequence[str]) -> list[str]:
    """Parmi ces fichiers d'origine, ceux qui sont déjà arrivés : le navigateur ne
    les renvoie pas (reprise après une coupure, decisions.md 0127)."""
    charger_inventaire(session, inventaire_id)
    recues = set(
        session.scalars(
            select(Photo.signature_envoi).where(
                Photo.inventaire_id == inventaire_id, Photo.signature_envoi.in_(list(signatures))
            )
        )
    )
    return [signature for signature in signatures if signature in recues]


# --- corriger l'ordre ----------------------------------------------------------------------------


def supprimer_photo(session: Session, inventaire_id: int, photo_id: int) -> None:
    """Retire une photo du brouillon. Son fichier reste dans le stockage (0133)."""
    _verrouiller(session, inventaire_id)
    photo = _photo_du_brouillon(session, inventaire_id, photo_id)
    session.delete(photo)
    session.flush()
    _renumeroter(session, _photos(session, inventaire_id))
    session.commit()


def deplacer_photo(session: Session, inventaire_id: int, photo_id: int, position: int) -> None:
    """Place la photo à `position` (1 = la première) ; les autres suivent."""
    inventaire = _verrouiller(session, inventaire_id)
    photo = _photo_du_brouillon(session, inventaire_id, photo_id)
    photos = _photos(session, inventaire_id)
    if not 1 <= position <= len(photos):
        session.rollback()
        raise ModificationRefusee(f"Position {position} impossible : choisir entre 1 et {len(photos)}.")
    photos.remove(photo)
    photos.insert(position - 1, photo)
    inventaire.ordre_manuel = True
    _renumeroter(session, photos)
    session.commit()


def inverser_paire(session: Session, inventaire_id: int, numero: int) -> None:
    """Échange l'étiquette et la contre-étiquette de la paire n° `numero`."""
    inventaire = _verrouiller(session, inventaire_id)
    if inventaire.sans_contre:
        session.rollback()
        raise ModificationRefusee("Cet inventaire n'a que des étiquettes : il n'y a pas de paire à inverser.")
    photos = _photos(session, inventaire_id)
    rang = 2 * (numero - 1)
    if numero < 1 or rang + 1 >= len(photos):
        session.rollback()
        raise ModificationRefusee(f"La paire n°{numero} n'existe pas ou n'a qu'une photo.")
    photos[rang], photos[rang + 1] = photos[rang + 1], photos[rang]
    inventaire.ordre_manuel = True
    _renumeroter(session, photos)
    session.commit()


def retrier(session: Session, inventaire_id: int) -> None:
    """Revient à l'ordre automatique (date de prise de vue, nom, arrivée)."""
    inventaire = _verrouiller(session, inventaire_id)
    inventaire.ordre_manuel = False
    _renumeroter(session, _ordre_automatique(_photos(session, inventaire_id)))
    session.commit()


# --- voir les paires ------------------------------------------------------------------------


@dataclass(frozen=True)
class Paire:
    numero: int
    etiquette: Photo
    contre_etiquette: Photo | None  # None : étiquettes seules, ou photo sans sa paire


@dataclass(frozen=True)
class Apercu:
    inventaire: Inventaire
    photos: list[Photo]
    paires: list[Paire]
    tri: str
    anomalies: list[str]
    peut_lancer: bool


def apercu(session: Session, inventaire_id: int) -> Apercu:
    """Les paires telles qu'elles deviendront des bouteilles, et ce qui cloche."""
    session.expire_all()
    inventaire = charger_inventaire(session, inventaire_id)
    photos = _photos(session, inventaire_id)
    pas = 1 if inventaire.sans_contre else 2
    paires = [
        Paire(rang // pas + 1, photos[rang], photos[rang + 1] if pas == 2 and rang + 1 < len(photos) else None)
        for rang in range(0, len(photos), pas)
    ]
    sans_date = [p for p in photos if p.prise_de_vue is None]
    tri = TRI_MANUEL if inventaire.ordre_manuel else (TRI_NOM if sans_date else TRI_DATE)

    anomalies = []
    if not photos:
        anomalies.append("Aucune photo pour l'instant.")
    if photos and not inventaire.sans_contre and len(photos) % 2:
        anomalies.append(_message_impair(len(photos)))
    if sans_date and len(photos) > 1:
        anomalies.append(
            f"{len(sans_date)} photo(s) sans date de prise de vue : les photos sont rangées par nom "
            f"de fichier. Vérifiez bien l'ordre des paires."
        )
    if inventaire.ordre_manuel:
        anomalies.append(
            "Ordre corrigé à la main : les photos ajoutées depuis sont placées à la fin. "
            "« Retrier automatiquement » revient au classement par date."
        )
    return Apercu(
        inventaire=inventaire,
        photos=photos,
        paires=paires,
        tri=tri,
        anomalies=anomalies,
        peut_lancer=inventaire.statut == "brouillon"
        and bool(photos)
        and (inventaire.sans_contre or len(photos) % 2 == 0),
    )


# --- finaliser -------------------------------------------------------------------------------


def finaliser(session: Session, inventaire_id: int, stockage: Path) -> int:
    """Vérifie les garde-fous, forme les bouteilles et lance l'extraction.
    Renvoie le nombre de bouteilles. Ensuite, le brouillon est fermé."""
    inventaire = _verrouiller(session, inventaire_id)
    photos = _photos(session, inventaire_id)
    if not photos:
        session.rollback()
        raise LancementRefuse("Aucune photo : ajoutez les photos des bouteilles avant de lancer l'analyse.")
    if not inventaire.sans_contre and len(photos) % 2:
        session.rollback()
        raise LancementRefuse(_message_impair(len(photos)))

    pas = 1 if inventaire.sans_contre else 2
    groupes = [photos[rang : rang + pas] for rang in range(0, len(photos), pas)]
    for position, groupe in enumerate(groupes, start=1):
        etiquette, contre = groupe[0], (groupe[1] if len(groupe) > 1 else None)
        vues = PhotosBouteille(
            etiquette=chemin_stocke(stockage, etiquette.chemin),
            contre_etiquette=chemin_stocke(stockage, contre.chemin) if contre else None,
        )
        session.add(
            FicheBouteille(
                inventaire_id=inventaire_id,
                identifiant=vues.identifiant,  # même calcul qu'en ligne de commande (0065)
                photo_etiquette_id=etiquette.id,
                photo_contre_id=contre.id if contre else None,
                position=position,
            )
        )
    inventaire.statut = "ouvert"
    inventaire.extraction = "lancee"
    inventaire.extraction_lancee_le = maintenant()
    session.commit()
    return len(groupes)


# --- outils ------------------------------------------------------------------------------


def _message_impair(nombre: int) -> str:
    return (
        f"Nombre impair de photos ({nombre}) : chaque bouteille demande une étiquette ET une "
        f"contre-étiquette. Supprimez la photo en trop ou ajoutez celle qui manque, puis "
        f"lancez l'analyse."
    )


def _brouillon(session: Session, inventaire_id: int) -> Inventaire:
    inventaire = charger_inventaire(session, inventaire_id)
    if inventaire.statut != "brouillon":
        raise DepotFerme(
            "L'analyse de cet inventaire est lancée : ses photos ne peuvent plus être modifiées."
        )
    return inventaire


def _verrouiller(session: Session, inventaire_id: int) -> Inventaire:
    """Prend le verrou d'écriture AVANT toute lecture (decisions.md 0134) : une
    écriture ouvre la transaction, les autres envois attendent leur tour."""
    session.commit()
    session.execute(
        update(Inventaire).where(Inventaire.id == inventaire_id).values(id=Inventaire.id)
        .execution_options(synchronize_session=False)
    )
    session.expire_all()
    try:
        return _brouillon(session, inventaire_id)
    except Exception:
        session.rollback()
        raise


def _photos(session: Session, inventaire_id: int) -> list[Photo]:
    return list(session.scalars(select(Photo).where(Photo.inventaire_id == inventaire_id).order_by(Photo.ordre)))


def _photo_du_brouillon(session: Session, inventaire_id: int, photo_id: int) -> Photo:
    photo = session.get(Photo, photo_id)
    if photo is None or photo.inventaire_id != inventaire_id:
        session.rollback()
        raise envoi.PhotoIntrouvable(f"Aucune photo n°{photo_id} dans l'inventaire n°{inventaire_id}.")
    return photo


def _ordre_automatique(photos: list[Photo]) -> list[Photo]:
    """Date de prise de vue, puis nom, puis ordre d'arrivée — ou, si une seule
    photo n'a pas de date, nom puis arrivée pour toutes (decisions.md 0068, 0128)."""
    if all(photo.prise_de_vue is not None for photo in photos):
        return sorted(photos, key=lambda p: (p.prise_de_vue, cle_naturelle(p.nom_origine), p.id))
    return sorted(photos, key=lambda p: (cle_naturelle(p.nom_origine), p.id))


def _renumeroter(session: Session, photos: list[Photo]) -> None:
    """Positions 1..n dans l'ordre donné. En deux temps : la contrainte d'unicité
    (inventaire, ordre) refuserait un échange direct de deux positions."""
    for rang, photo in enumerate(photos, start=1):
        photo.ordre = -rang
    session.flush()
    for rang, photo in enumerate(photos, start=1):
        photo.ordre = rang
    session.flush()
