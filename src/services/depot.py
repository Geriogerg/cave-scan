"""Dépôt des photos, bouteille par bouteille (decisions.md 0126, 0127, 0134, 0166, 0167).

Le parcours de l'expert : créer l'inventaire en brouillon (nom, maison), puis
envoyer ses photos — en plusieurs fois, sur un réseau qui coupe —, chacune
rattachée à SA bouteille :

- mode appareil photo : la bouteille en cours, ses photos à la suite, sa
  quantité (« × N »), puis « Bouteille suivante » ;
- mode galerie ou ordinateur : « Bouteille 1 → ses photos », « Bouteille 2 → … ».

Tant qu'elle n'est pas lancée, une bouteille est un GROUPE de photos en attente,
désigné par une clé que donne l'appareil (les photos d'une même bouteille
arrivent parfois dans le désordre) et numéroté dans l'ordre de prise de vue. On
peut encore retirer une photo, couper un groupe en deux, rattacher un groupe au
précédent, en supprimer un, changer sa quantité.

« Lancer l'analyse » forme une bouteille par groupe en attente et lance
l'extraction. Après le lancement, on peut AJOUTER des bouteilles par les mêmes
écrans : elles prennent place à la fin. Les photos d'une bouteille formée ne
bougent plus.

Fonctions de service, utilisées à la fois par les pages et par l'API JSON. Tout
garde-fou est vérifié ICI, côté serveur, même si le navigateur l'affiche aussi.
Concurrence : chaque modification commence par prendre le verrou d'écriture sur
la ligne de l'inventaire (`_verrouiller`, 0134).
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from src.config.maison import QUANTITE_MAX, lire_config, plier
from src.donnees.modeles import FicheBouteille, GroupePhotos, Inventaire, Photo, maintenant
from src.donnees.stockage import empreinte_fichier, stocker
from src.io.photos import date_de_prise_de_vue
from src.services import envoi
from src.services.envoi import EnvoiRefuse, verifier_image
from src.services.inventaires import (
    _maison,
    _version_de_config,
    actualiser_statut,
    bouteille_du_groupe,
    charger_inventaire,
    config_figee,
    verifier_modifiable,
)
from src.services.pilotage import LancementRefuse

MOTIF_CLE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class DepotFerme(ValueError):
    """Le dépôt n'est pas possible : bouteille déjà formée, inventaire fermé."""


class ModificationRefusee(ValueError):
    """Coupure, rattachement ou retrait impossible (photo ou bouteille absente…)."""


# --- créer le brouillon --------------------------------------------------------------------------


@dataclass(frozen=True)
class BrouillonCree:
    inventaire_id: int
    config_numero: int
    nouvelle_config: bool
    avertissements: list[str] = field(default_factory=list)


def creer_brouillon(session: Session, maison: str, config_path: str | Path, nom: str) -> BrouillonCree:
    """Un inventaire vide en brouillon. La config de la maison est figée dès
    maintenant, comme pour un inventaire créé d'un coup (decisions.md 0073)."""
    if not nom.strip():
        raise EnvoiRefuse("Donnez un nom à la vente : il ne peut pas rester vide.")
    config, texte = lire_config(config_path)
    if plier(config.maison) != plier(maison):
        raise EnvoiRefuse(f"La config {Path(config_path).name} décrit « {config.maison} », pas « {maison} ».")
    maison_bd = _maison(session, config.maison)
    version, nouvelle, avertissements = _version_de_config(
        session, maison_bd, config, texte, Path(config_path).name
    )
    inventaire = Inventaire(maison=maison_bd, config_version=version, nom=nom.strip(), statut="brouillon")
    session.add(inventaire)
    session.commit()
    return BrouillonCree(inventaire.id, version.numero, nouvelle, [*config.avertissements, *avertissements])


# --- recevoir une photo ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PhotoRecue:
    photo_id: int
    bouteille: str  # la clé du groupe (de la bouteille) qui l'a reçue
    numero: int  # le numéro de cette bouteille dans le dépôt
    rang: int  # sa place parmi les photos de la bouteille
    nom: str
    deja_recue: bool  # même contenu ou même fichier d'origine : rien n'a été ajouté


def ajouter_photo(
    session: Session,
    inventaire_id: int,
    flux: BinaryIO,
    nom_origine: str,
    stockage: Path,
    bouteille: str,
    numero: int,
    quantite: int | None = None,
    prise_de_vue: datetime | None = None,
    signature: str | None = None,
) -> PhotoRecue:
    """Ajoute UNE photo à la bouteille `bouteille` (sa clé), créée au besoin avec
    le numéro `numero`. Idempotent : une photo déjà reçue (même contenu, ou même
    fichier d'origine) n'est jamais enregistrée deux fois.

    Refus avec une raison claire : pas une image, trop lourde, trop de photos
    pour une bouteille (plafond de la maison), bouteille déjà analysée.
    """
    cle = _cle_valide(bouteille)
    if numero < 1:
        raise EnvoiRefuse("Numéro de bouteille invalide.")
    _depot_ouvert(charger_inventaire(session, inventaire_id))  # refuser tôt, avant de lire le fichier
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
        return PhotoRecue(deja.id, deja.groupe.cle or "", deja.groupe.numero, deja.rang, deja.nom_origine, True)

    groupe = session.scalar(select(GroupePhotos).where(GroupePhotos.inventaire_id == inventaire_id, GroupePhotos.cle == cle))
    if groupe is None:
        groupe = GroupePhotos(inventaire_id=inventaire_id, cle=cle, numero=numero, quantite=_quantite(quantite) or 1)
        session.add(groupe)
        session.flush()
    elif _formee(session, groupe):
        session.rollback()
        raise DepotFerme(
            f"La bouteille n°{groupe.numero} est déjà analysée : ses photos ne changent plus. "
            f"Ajoutez cette photo à une nouvelle bouteille."
        )
    plafond = config_figee(inventaire).photos_max_par_bouteille
    if len(groupe.photos) >= plafond:
        session.rollback()
        raise EnvoiRefuse(
            f"Bouteille n°{groupe.numero} : {plafond} photos au plus (plafond de la maison). "
            f"Commencez une nouvelle bouteille, ou retirez une photo."
        )
    if quantite is not None:
        groupe.quantite = _quantite(quantite)
    ordre = (session.scalar(select(func.max(Photo.ordre)).where(Photo.inventaire_id == inventaire_id)) or 0) + 1
    photo = Photo(
        inventaire_id=inventaire_id,
        chemin=relatif,
        empreinte=empreinte,
        nom_origine=nom_origine[:255],
        prise_de_vue=date,
        ordre=ordre,  # ordre d'arrivée
        signature_envoi=(signature or None) and signature[:300],
        groupe=groupe,
        rang=len(groupe.photos) + 1,
    )
    session.add(photo)
    session.commit()
    return PhotoRecue(photo.id, cle, groupe.numero, photo.rang, photo.nom_origine, False)


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


def definir_quantite(session: Session, inventaire_id: int, bouteille: str, quantite: int) -> None:
    """« × N » d'une bouteille en attente (mode appareil photo : saisie sur place)."""
    _verrouiller(session, inventaire_id)
    groupe = _groupe_en_attente(session, inventaire_id, cle=_cle_valide(bouteille))
    groupe.quantite = _quantite(quantite)
    session.commit()


# --- corriger les bouteilles en attente ------------------------------------------------------------


def supprimer_photo(session: Session, inventaire_id: int, photo_id: int) -> None:
    """Retire une photo d'une bouteille en attente ; une bouteille qui n'a plus de
    photo disparaît. Le fichier reste dans le stockage (0133)."""
    _verrouiller(session, inventaire_id)
    photo = _photo_en_attente(session, inventaire_id, photo_id)
    groupe = photo.groupe
    groupe.photos.remove(photo)
    session.delete(photo)
    session.flush()
    if groupe.photos:
        _renumeroter(session, groupe, list(groupe.photos))
    else:
        session.delete(groupe)
    session.commit()


def couper(session: Session, inventaire_id: int, photo_id: int) -> None:
    """« Nouvelle bouteille à partir de cette photo » : la photo et celles qui la
    suivent forment une bouteille à part, juste après (l'expert avait oublié
    « Bouteille suivante »)."""
    _verrouiller(session, inventaire_id)
    photo = _photo_en_attente(session, inventaire_id, photo_id)
    groupe = photo.groupe
    photos = list(groupe.photos)
    index = photos.index(photo)
    if index == 0:
        session.rollback()
        raise ModificationRefusee("C'est déjà la première photo de sa bouteille : rien à couper.")
    attente = groupes_en_attente(session, inventaire_id)
    nouveau = GroupePhotos(inventaire_id=inventaire_id, numero=groupe.numero + 1, quantite=1)
    session.add(nouveau)
    # Les groupes suivants reculent d'un numéro : l'ordre de prise de vue est gardé.
    for suivant in attente[attente.index(groupe) + 1 :]:
        suivant.numero += 1
    session.flush()
    _deplacer(session, photos[index:], nouveau)
    _renumeroter(session, groupe, photos[:index])
    session.commit()


def rattacher(session: Session, inventaire_id: int, groupe_id: int) -> None:
    """« Rattacher à la bouteille précédente » (« Bouteille suivante » appuyé trop
    tôt) : ses photos passent à la fin de la bouteille en attente qui précède."""
    _verrouiller(session, inventaire_id)
    groupe = _groupe_en_attente(session, inventaire_id, groupe_id=groupe_id)
    attente = groupes_en_attente(session, inventaire_id)
    rang = attente.index(groupe)
    if rang == 0:
        session.rollback()
        raise ModificationRefusee("C'est la première bouteille en attente : aucune bouteille avant elle.")
    precedent = attente[rang - 1]
    plafond = config_figee(charger_inventaire(session, inventaire_id)).photos_max_par_bouteille
    if len(precedent.photos) + len(groupe.photos) > plafond:
        session.rollback()
        raise ModificationRefusee(
            f"Ensemble, ces deux bouteilles auraient {len(precedent.photos) + len(groupe.photos)} photos : "
            f"{plafond} au plus (plafond de la maison). Retirez d'abord des photos."
        )
    _deplacer(session, list(groupe.photos), precedent, a_la_suite=True)
    session.delete(groupe)
    session.commit()


def supprimer_groupe(session: Session, inventaire_id: int, groupe_id: int) -> None:
    """Supprime une bouteille en attente et ses photos (les fichiers restent dans
    le stockage, 0133). L'écran demande confirmation."""
    _verrouiller(session, inventaire_id)
    groupe = _groupe_en_attente(session, inventaire_id, groupe_id=groupe_id)
    for photo in list(groupe.photos):
        session.delete(photo)
    session.delete(groupe)
    session.commit()


def quantite_du_groupe(session: Session, inventaire_id: int, groupe_id: int, quantite: int) -> None:
    """La quantité d'une bouteille en attente, depuis l'écran de vérification."""
    _verrouiller(session, inventaire_id)
    _groupe_en_attente(session, inventaire_id, groupe_id=groupe_id).quantite = _quantite(quantite)
    session.commit()


# --- voir les bouteilles en attente ----------------------------------------------------------


@dataclass(frozen=True)
class BouteilleEnAttente:
    groupe: GroupePhotos
    numero: int  # sa future position dans l'inventaire
    photos: list[Photo]


@dataclass(frozen=True)
class Apercu:
    inventaire: Inventaire
    bouteilles: list[BouteilleEnAttente]  # en attente, dans l'ordre
    deja_formees: int  # bouteilles déjà dans l'inventaire (analysées ou en cours)
    nb_photos: int  # photos en attente
    photos_max: int  # plafond de la maison
    prochain_numero: int  # pour la prochaine bouteille de l'appareil
    peut_lancer: bool
    anomalies: list[str]


def apercu(session: Session, inventaire_id: int) -> Apercu:
    """Les bouteilles en attente telles qu'elles seront formées, et ce qui cloche."""
    session.expire_all()
    inventaire = charger_inventaire(session, inventaire_id)
    attente = groupes_en_attente(session, inventaire_id)
    formees = session.scalar(select(func.count(FicheBouteille.id)).where(FicheBouteille.inventaire_id == inventaire_id))
    bouteilles = [
        BouteilleEnAttente(groupe=g, numero=formees + rang, photos=list(g.photos))
        for rang, g in enumerate(attente, start=1)
    ]
    numero_max = session.scalar(select(func.max(GroupePhotos.numero)).where(GroupePhotos.inventaire_id == inventaire_id))
    anomalies = []
    if not bouteilles and inventaire.statut == "brouillon":
        anomalies.append("Aucune photo pour l'instant.")
    return Apercu(
        inventaire=inventaire,
        bouteilles=bouteilles,
        deja_formees=formees,
        nb_photos=sum(len(b.photos) for b in bouteilles),
        photos_max=config_figee(inventaire).photos_max_par_bouteille,
        prochain_numero=(numero_max or 0) + 1,
        peut_lancer=bool(bouteilles),
        anomalies=anomalies,
    )


def groupes_en_attente(session: Session, inventaire_id: int) -> list[GroupePhotos]:
    """Les groupes de photos qui ne sont pas encore des bouteilles, dans l'ordre
    de prise de vue."""
    formee = exists().where(FicheBouteille.groupe_id == GroupePhotos.id)
    return list(
        session.scalars(
            select(GroupePhotos)
            .where(GroupePhotos.inventaire_id == inventaire_id, ~formee)
            .order_by(GroupePhotos.numero, GroupePhotos.id)
        )
    )


# --- lancer ----------------------------------------------------------------------------------


def finaliser(session: Session, inventaire_id: int, stockage: Path) -> int:
    """Forme une bouteille par groupe en attente, à la fin de l'inventaire, et
    lance (ou relance) l'extraction. Renvoie le nombre de bouteilles formées.

    Premier lancement : le brouillon devient un inventaire ouvert. Ajout après
    le lancement : un inventaire validé redevient ouvert, et une analyse
    terminée, annulée ou arrêtée repart pour les nouvelles bouteilles.
    """
    inventaire = _verrouiller(session, inventaire_id)
    attente = groupes_en_attente(session, inventaire_id)
    if not attente:
        session.rollback()
        raise LancementRefuse("Aucune bouteille en attente : ajoutez des photos avant de lancer l'analyse.")
    bouteilles = list(inventaire.bouteilles)
    # Après la dernière, retirées comprises : elles gardent leur place (0168).
    position = max((b.position for b in inventaire.toutes_les_bouteilles), default=0)
    rien_en_cours = not any(b.statut in ("a_extraire", "en_cours") for b in bouteilles)
    for groupe in attente:
        position += 1
        session.add(bouteille_du_groupe(groupe, position, stockage))
    session.flush()
    if inventaire.statut == "brouillon" or inventaire.extraction != "lancee" or rien_en_cours:
        # Le temps restant estimé repart de ce lancement.
        inventaire.extraction_lancee_le = maintenant()
    inventaire.extraction = "lancee"
    inventaire.motif_arret = None
    inventaire.statut = "ouvert"
    session.expire(inventaire, ["bouteilles"])
    actualiser_statut(inventaire)
    session.commit()
    return len(attente)


# --- outils ------------------------------------------------------------------------------


def _depot_ouvert(inventaire: Inventaire) -> Inventaire:
    """On peut déposer dans un brouillon, et ajouter des bouteilles à un inventaire
    lancé (decisions.md 0167) — pas à un inventaire clos (0168)."""
    verifier_modifiable(inventaire)
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
        return _depot_ouvert(charger_inventaire(session, inventaire_id))
    except Exception:
        session.rollback()
        raise


def _cle_valide(cle: str) -> str:
    cle = (cle or "").strip()
    if not MOTIF_CLE.match(cle):
        raise EnvoiRefuse("Bouteille non reconnue : rechargez la page puis renvoyez la photo.")
    return cle


def _quantite(valeur: int | None) -> int | None:
    if valeur is None:
        return None
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < 1:
        raise EnvoiRefuse(f"Quantité invalide : « {valeur} » : indiquez un nombre de bouteilles (1 ou plus).")
    if valeur > QUANTITE_MAX:
        raise EnvoiRefuse(f"Quantité trop grande : « {valeur} » ({QUANTITE_MAX:,} au plus).".replace(",", " "))
    return valeur


def _formee(session: Session, groupe: GroupePhotos) -> bool:
    return session.scalar(select(exists().where(FicheBouteille.groupe_id == groupe.id)))


def _groupe_en_attente(
    session: Session, inventaire_id: int, cle: str | None = None, groupe_id: int | None = None
) -> GroupePhotos:
    if cle is not None:
        groupe = session.scalar(select(GroupePhotos).where(GroupePhotos.inventaire_id == inventaire_id, GroupePhotos.cle == cle))
    else:
        groupe = session.get(GroupePhotos, groupe_id)
    if groupe is None or groupe.inventaire_id != inventaire_id:
        session.rollback()
        raise ModificationRefusee("Cette bouteille n'existe pas (ou plus) dans cet inventaire.")
    if _formee(session, groupe):
        session.rollback()
        raise DepotFerme(f"La bouteille n°{groupe.numero} est déjà analysée : ses photos ne changent plus.")
    return groupe


def _photo_en_attente(session: Session, inventaire_id: int, photo_id: int) -> Photo:
    photo = session.get(Photo, photo_id)
    if photo is None or photo.inventaire_id != inventaire_id:
        session.rollback()
        raise envoi.PhotoIntrouvable(f"Aucune photo n°{photo_id} dans l'inventaire n°{inventaire_id}.")
    if _formee(session, photo.groupe):
        session.rollback()
        raise DepotFerme("Cette photo appartient à une bouteille déjà analysée : elle ne bouge plus.")
    return photo


def _deplacer(session: Session, photos: list[Photo], vers: GroupePhotos, a_la_suite: bool = False) -> None:
    """Change des photos de groupe, en deux temps : la contrainte d'unicité
    (groupe, rang) refuserait un échange direct."""
    depart = len(vers.photos) if a_la_suite else 0
    for i, photo in enumerate(photos, start=1):
        photo.rang = -i
    session.flush()
    for i, photo in enumerate(photos, start=1):
        photo.groupe = vers
        photo.rang = depart + i
    session.flush()


def _renumeroter(session: Session, groupe: GroupePhotos, photos: list[Photo]) -> None:
    """Rangs 1..n dans l'ordre donné, en deux temps (contrainte d'unicité)."""
    for i, photo in enumerate(photos, start=1):
        photo.rang = -i
    session.flush()
    for i, photo in enumerate(photos, start=1):
        photo.rang = i
    session.flush()
    session.expire(groupe, ["photos"])
