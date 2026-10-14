"""Inventaires : création, config figée (guide de session 2).

Un inventaire, c'est une maison, une version FIGÉE de sa config, des photos
copiées dans le stockage, et les bouteilles qu'elles forment : une bouteille =
un groupe de photos (decisions.md 0166). Garde-fous : format illisible, photos
rangées trop profond, trop de photos pour une bouteille (plafond de la maison),
la même photo déposée deux fois (decisions.md 0074). Rien n'est écrit tant que
tout n'a pas été vérifié.
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
from src.donnees.modeles import ConfigVersion, FicheBouteille, GroupePhotos, Inventaire, Maison, Photo
from src.donnees.stockage import chemin_stocke, empreinte_fichier, stocker
from src.io.photos import PhotosBouteille, PhotosInvalides, Regroupement, grouper_photos, identifiant_de


class InventaireIntrouvable(LookupError):
    pass


class InventaireClos(ValueError):
    """L'inventaire est clos : lecture seule tant qu'il n'est pas rouvert (0168)."""


@dataclass(frozen=True)
class InventaireCree:
    """Ce que la création a fait — de quoi l'annoncer à l'utilisateur."""

    inventaire_id: int
    nb_bouteilles: int
    config_numero: int
    nouvelle_config: bool
    avertissements: list[str] = field(default_factory=list)


def creer_inventaire(
    session: Session,
    maison: str,
    config_path: str | Path,
    dossier_photos: str | Path,
    nom: str,
    stockage: Path,
    limite: int | None = None,
) -> InventaireCree:
    """Enregistre la config (nouvelle version si son contenu a changé), copie les
    photos dans le stockage et forme les bouteilles : une par photo posée à la
    racine du dossier, une par sous-dossier (decisions.md 0166).

    `limite` ne garde que les N premières bouteilles (decisions.md 0084) — les
    contrôles portent quand même sur tout le dossier.
    """
    lire_config_de_la_maison(maison, config_path)  # une config invalide s'arrête avant les photos
    regroupement = grouper_photos(dossier_photos)  # formats, HEIC illisible, trop profond : refus
    return creer_inventaire_depuis_groupes(
        session, maison, config_path, regroupement, nom, stockage, limite, str(Path(dossier_photos).resolve())
    )


def lire_config_de_la_maison(maison: str, config_path: str | Path) -> tuple[ConfigMaison, str]:
    config, texte = lire_config(config_path)
    if plier(config.maison) != plier(maison):
        raise ValueError(
            f"La config {Path(config_path).name} décrit « {config.maison} », pas « {maison} »."
        )
    return config, texte


def creer_inventaire_depuis_groupes(
    session: Session,
    maison: str,
    config_path: str | Path,
    regroupement: Regroupement,
    nom: str,
    stockage: Path,
    limite: int | None = None,
    dossier_source: str | None = None,
) -> InventaireCree:
    """Les bouteilles déjà formées (un dossier regroupé, ou les photos envoyées
    d'un coup à l'API) deviennent un inventaire. Tout est vérifié avant
    d'écrire."""
    config, texte = lire_config_de_la_maison(maison, config_path)
    refuser_les_groupes_trop_grands(regroupement.bouteilles, config.photos_max_par_bouteille)
    bouteilles = regroupement.bouteilles[:limite] if limite else regroupement.bouteilles
    images = [photo for vues in bouteilles for photo in vues.photos]
    empreintes = {image: empreinte_fichier(image) for image in images}
    _refuser_les_photos_en_double(images, empreintes)

    # Tout est vérifié : on peut écrire.
    maison_bd = _maison(session, config.maison)
    version, nouvelle, avertissements = _version_de_config(
        session, maison_bd, config, texte, Path(config_path).name
    )
    inventaire = Inventaire(maison=maison_bd, config_version=version, nom=nom, dossier_source=dossier_source)
    session.add(inventaire)
    session.flush()

    ordre = 0
    for position, vues in enumerate(bouteilles, start=1):
        groupe = GroupePhotos(inventaire_id=inventaire.id, numero=position)
        session.add(groupe)
        for rang, image in enumerate(vues.photos, start=1):
            ordre += 1
            session.add(
                Photo(
                    inventaire_id=inventaire.id,
                    chemin=stocker(image, stockage, empreintes[image]),
                    empreinte=empreintes[image],
                    nom_origine=image.name,
                    prise_de_vue=regroupement.dates.get(image),
                    ordre=ordre,
                    groupe=groupe,
                    rang=rang,
                )
            )
        session.add(
            FicheBouteille(inventaire_id=inventaire.id, identifiant=vues.identifiant, groupe=groupe, position=position)
        )
    session.commit()

    return InventaireCree(
        inventaire_id=inventaire.id,
        nb_bouteilles=len(bouteilles),
        config_numero=version.numero,
        nouvelle_config=nouvelle,
        avertissements=[*config.avertissements, *avertissements],
    )


def refuser_les_groupes_trop_grands(bouteilles: list[PhotosBouteille], maximum: int) -> None:
    """Chaque photo envoyée au modèle se paie : au-delà du plafond de la maison,
    on s'arrête AVANT tout appel (decisions.md 0159)."""
    trop = [vues for vues in bouteilles if len(vues.photos) > maximum]
    if trop:
        detail = " ; ".join(f"{vues.nom} : {len(vues.photos)} photos" for vues in trop[:5])
        raise PhotosInvalides(
            f"{len(trop)} bouteille(s) dépassent le plafond de {maximum} photos par bouteille fixé par la "
            f"configuration ({detail}). Retirer les photos en trop, ou relever le plafond dans la configuration."
        )


def bouteille_du_groupe(groupe: GroupePhotos, position: int, stockage: Path) -> FicheBouteille:
    """La bouteille que forme un groupe de photos déposé : identifiant calculé sur
    le CONTENU de ses photos, comme en ligne de commande (decisions.md 0065), et
    la quantité saisie à la capture."""
    chemins = [chemin_stocke(stockage, photo.chemin) for photo in groupe.photos]
    return FicheBouteille(
        inventaire_id=groupe.inventaire_id,
        identifiant=identifiant_de(chemins),
        groupe=groupe,
        position=position,
        quantite=groupe.quantite,
    )


def charger_inventaire(session: Session, inventaire_id: int, corbeille: bool = False) -> Inventaire:
    """L'inventaire demandé. Un inventaire à la corbeille n'est plus ouvert par
    aucun écran ni aucune route — seulement restauré (`corbeille=True`)."""
    inventaire = session.get(Inventaire, inventaire_id)
    if inventaire is None:
        raise InventaireIntrouvable(f"Aucun inventaire n°{inventaire_id}.")
    if inventaire.supprime_le is not None and not corbeille:
        raise InventaireIntrouvable(
            f"L'inventaire n°{inventaire_id} est dans la corbeille : restaurez-le depuis l'accueil pour l'ouvrir."
        )
    return inventaire


def verifier_modifiable(inventaire: Inventaire) -> None:
    """Un inventaire clos est en lecture seule : ni correction, ni validation,
    ni ajout ou retrait de bouteille, ni nouvelle analyse (decisions.md 0168).
    L'export reste possible."""
    if inventaire.clos_le is not None:
        raise InventaireClos(
            f"L'inventaire « {inventaire.nom} » est clos : il est en lecture seule. "
            f"Rouvrez-le (écran de suivi) pour le modifier."
        )


def actualiser_statut(inventaire: Inventaire) -> None:
    """`valide` quand TOUTES les bouteilles le sont, `ouvert` sinon (decisions.md 0169).

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
    """Une photo copiée deux fois mêlerait deux bouteilles."""
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
            + ". Retirer la copie puis relancer : une photo ne peut appartenir qu'à "
            "une bouteille."
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


NOM_MAX = 200  # caractères, comme le champ de l'écran


def nom_de_vente(nom: str | None, refus: type[Exception]) -> str:
    """Le nom d'une vente tel qu'il sera enregistré : caractères de contrôle
    remplacés par une espace, jamais vide, 200 caractères au plus — côté serveur
    aussi, pas seulement dans le navigateur (T5-B10)."""
    nom = "".join(c if c.isprintable() else " " for c in (nom or "")).strip()
    if not nom:
        raise refus("Donnez un nom à la vente : il ne peut pas rester vide.")
    if len(nom) > NOM_MAX:
        raise refus(f"Nom trop long : {NOM_MAX} caractères au plus.")
    return nom


def lister_inventaires(session: Session, corbeille: bool = False) -> list[Inventaire]:
    """Les inventaires, hors corbeille ; ou ceux de la corbeille."""
    condition = Inventaire.supprime_le.is_not(None) if corbeille else Inventaire.supprime_le.is_(None)
    return list(session.scalars(select(Inventaire).where(condition).order_by(Inventaire.id)))

