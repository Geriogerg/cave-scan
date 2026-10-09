"""Inventaires : création, config figée (guide de session 2).

Un inventaire, c'est une maison, une version FIGÉE de sa config, des photos
copiées dans le stockage, et les bouteilles qu'elles forment par paires.
Mêmes garde-fous qu'en session 1 — nombre impair, format illisible, photos en
sous-dossier — plus un : la même photo déposée deux fois (decisions.md 0074).
Rien n'est écrit tant que tout n'a pas été vérifié.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.maison import (
    ConfigMaison,
    config_depuis_texte,
    empreinte_config,
    lire_config,
    plier,
)
from src.donnees.modeles import ConfigVersion, FicheBouteille, Inventaire, Maison, Photo
from src.donnees.stockage import empreinte_fichier, stocker
from src.io.photos import PhotosInvalides, apparier_photos


class InventaireIntrouvable(LookupError):
    pass


@dataclass(frozen=True)
class InventaireCree:
    """Ce que la création a fait — de quoi l'annoncer à l'utilisateur."""

    inventaire_id: int
    nb_bouteilles: int
    config_numero: int
    nouvelle_config: bool
    tri: str
    sans_date: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


def creer_inventaire(
    session: Session,
    maison: str,
    config_path: str | Path,
    dossier_photos: str | Path,
    nom: str,
    stockage: Path,
    limite: int | None = None,
    sans_contre: bool = False,
) -> InventaireCree:
    """Enregistre la config (nouvelle version si son contenu a changé), copie les
    photos dans le stockage et forme les bouteilles par paires.

    `limite` ne garde que les N premières bouteilles (decisions.md 0084) — le
    contrôle du nombre impair porte quand même sur tout le dossier.
    `sans_contre` : une photo par bouteille, sans contre-étiquette (0108).
    """
    config, texte = lire_config(config_path)
    if plier(config.maison) != plier(maison):
        raise ValueError(
            f"La config {Path(config_path).name} décrit « {config.maison} », pas « {maison} »."
        )

    appariement = apparier_photos(dossier_photos, sans_contre)  # impair, HEIC, sous-dossier : refus
    paires = appariement.bouteilles[:limite] if limite else appariement.bouteilles
    images = [
        photo for vues in paires for photo in (vues.etiquette, vues.contre_etiquette) if photo is not None
    ]
    empreintes = {image: empreinte_fichier(image) for image in images}
    _refuser_les_photos_en_double(images, empreintes)

    # Tout est vérifié : on peut écrire.
    maison_bd = _maison(session, config.maison)
    version, nouvelle, avertissements = _version_de_config(
        session, maison_bd, config, texte, Path(config_path).name
    )
    inventaire = Inventaire(
        maison=maison_bd,
        config_version=version,
        nom=nom,
        dossier_source=str(Path(dossier_photos).resolve()),
    )
    session.add(inventaire)
    session.flush()

    photos: dict[Path, Photo] = {}
    for ordre, image in enumerate(images, start=1):
        photos[image] = Photo(
            inventaire_id=inventaire.id,
            chemin=stocker(image, stockage, empreintes[image]),
            empreinte=empreintes[image],
            nom_origine=image.name,
            prise_de_vue=appariement.dates.get(image),
            ordre=ordre,
        )
    session.add_all(photos.values())
    session.flush()

    session.add_all(
        FicheBouteille(
            inventaire_id=inventaire.id,
            identifiant=vues.identifiant,
            photo_etiquette_id=photos[vues.etiquette].id,
            photo_contre_id=photos[vues.contre_etiquette].id if vues.contre_etiquette else None,
            position=position,
        )
        for position, vues in enumerate(paires, start=1)
    )
    session.commit()

    return InventaireCree(
        inventaire_id=inventaire.id,
        nb_bouteilles=len(paires),
        config_numero=version.numero,
        nouvelle_config=nouvelle,
        tri=appariement.tri,
        sans_date=appariement.sans_date,
        avertissements=[*config.avertissements, *avertissements],
    )


def charger_inventaire(session: Session, inventaire_id: int) -> Inventaire:
    inventaire = session.get(Inventaire, inventaire_id)
    if inventaire is None:
        raise InventaireIntrouvable(f"Aucun inventaire n°{inventaire_id}.")
    return inventaire


def actualiser_statut(inventaire: Inventaire) -> None:
    """`valide` quand TOUTES les bouteilles le sont, `ouvert` sinon (decisions.md 0083).

    Une bouteille en erreur ne pouvant pas être validée, un inventaire qui en
    contient une ne passe jamais à `valide`.
    """
    toutes_validees = bool(inventaire.bouteilles) and all(
        bouteille.statut == "validee" for bouteille in inventaire.bouteilles
    )
    inventaire.statut = "valide" if toutes_validees else "ouvert"


def config_figee(inventaire: Inventaire) -> ConfigMaison:
    """La config de l'inventaire, telle qu'à sa création — jamais le fichier actuel
    (decisions.md 0073)."""
    version = inventaire.config_version
    return config_depuis_texte(version.contenu, version.fichier_source)


def _refuser_les_photos_en_double(images: list[Path], empreintes: dict[Path, str]) -> None:
    """Une photo copiée deux fois décalerait toutes les paires suivantes."""
    vues: dict[str, Path] = {}
    doublons = []
    for image in images:
        premiere = vues.setdefault(empreintes[image], image)
        if premiere is not image:
            doublons.append(f"{premiere.name} et {image.name}")
    if doublons:
        raise PhotosInvalides(
            "La même photo est déposée deux fois (contenu identique) : "
            + " ; ".join(doublons)
            + ". Retirer la copie puis relancer : sinon toutes les paires suivantes "
            "seraient décalées."
        )


def _maison(session: Session, nom: str) -> Maison:
    existante = session.scalar(select(Maison).where(Maison.nom == nom))
    if existante is not None:
        return existante
    maison = Maison(nom=nom)
    session.add(maison)
    return maison


def _version_de_config(
    session: Session, maison: Maison, config: ConfigMaison, texte: str, fichier_source: str
) -> tuple[ConfigVersion, bool, list[str]]:
    """La version figée correspondant à ce contenu, créée si elle n'existe pas."""
    empreinte = empreinte_config(texte)
    if maison.id is not None:
        existante = session.scalar(
            select(ConfigVersion).where(
                ConfigVersion.maison_id == maison.id, ConfigVersion.empreinte == empreinte
            )
        )
        if existante is not None:
            return existante, False, []
        derniere = session.scalar(
            select(ConfigVersion)
            .where(ConfigVersion.maison_id == maison.id)
            .order_by(ConfigVersion.numero.desc())
            .limit(1)
        )
    else:
        derniere = None

    numero = derniere.numero + 1 if derniere else 1
    avertissements = []
    if derniere is not None and derniere.version_declaree == config.version:
        avertissements.append(
            f"La config a changé mais son numéro « version » est resté {config.version} : "
            f"elle est enregistrée comme version n°{numero}, pensez à incrémenter le "
            f"numéro dans {fichier_source} (decisions.md 0073)."
        )
    version = ConfigVersion(
        maison=maison,
        numero=numero,
        version_declaree=config.version,
        contenu=texte,
        empreinte=empreinte,
        fichier_source=fichier_source,
    )
    session.add(version)
    return version, True, avertissements


def lister_inventaires(session: Session) -> list[Inventaire]:
    return list(session.scalars(select(Inventaire).order_by(Inventaire.id)))

