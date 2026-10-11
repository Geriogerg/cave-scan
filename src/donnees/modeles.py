"""Modèle de données de la bibliothèque (guide de session 2 ; decisions.md 0072-0075).

Une seule règle domine ce fichier : **on ne perd jamais la sortie du modèle**.
La réponse brute d'une extraction est stockée telle que reçue, et le modèle de
données lui-même refuse qu'on la modifie ou qu'on la supprime ; une correction
de l'expert est un enregistrement à part, lui aussi intouchable une fois écrit.

Le schéma n'est jamais créé à partir d'ici (`create_all`) : il l'est par les
migrations Alembic de `migrations/` (decisions.md 0075). Un test vérifie que les
migrations et ces classes décrivent exactement le même schéma.

Les images ne sont jamais dans la base : seulement leur chemin dans le
stockage géré et leur empreinte (decisions.md 0074).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    event,
    false,
    inspect,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STATUTS_BOUTEILLE = ("a_extraire", "en_cours", "extraite", "erreur", "validee")
# « brouillon » : photos en cours de dépôt, pas encore de bouteilles (decisions.md 0126).
STATUTS_INVENTAIRE = ("brouillon", "ouvert", "valide")
# Où en est l'extraction d'un inventaire : le worker ne réserve que dans un
# inventaire « lancee » (decisions.md 0111).
ETATS_EXTRACTION = ("non_lancee", "lancee", "annulee", "arretee")
# Ce que l'expert fait à une bouteille pendant la relecture, hors valeurs de
# champ (celles-là sont des corrections) — decisions.md 0139.
TYPES_EVENEMENT = (
    "reanalyse", "inversion_photos", "signalement_paire", "signalement_leve", "separation",
    "retrait", "remise",  # retirer une bouteille de l'inventaire, l'y remettre (decisions.md 0168)
)
# Ce que l'expert fait à un inventaire (decisions.md 0168).
TYPES_EVENEMENT_INVENTAIRE = (
    "renommage", "archivage", "desarchivage", "suppression", "restauration", "cloture", "reouverture",
)

# Noms de contraintes déterministes : Alembic ne sait modifier sous SQLite que
# des contraintes nommées (mode « batch »). Sans cette convention, la première
# évolution du schéma pendant le pilote bloquerait.
CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def maintenant() -> datetime:
    """L'instant présent, en UTC sans fuseau : SQLite ne stocke pas de fuseau,
    la convention est donc « toute date en base est en UTC » (decisions.md 0086)."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENTION)


class Maison(Base):
    __tablename__ = "maison"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(200), unique=True)


class ConfigVersion(Base):
    """Copie figée d'une config de maison (decisions.md 0073).

    Un inventaire pointe vers UNE version : modifier le fichier JSON ensuite ne
    change jamais son export.
    """

    __tablename__ = "config_version"
    __table_args__ = (
        UniqueConstraint("maison_id", "empreinte"),
        UniqueConstraint("maison_id", "numero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    maison_id: Mapped[int] = mapped_column(ForeignKey("maison.id"))
    numero: Mapped[int]  # compteur propre à la maison : 1, 2, 3…
    version_declaree: Mapped[int]  # le « version » écrit dans le JSON
    contenu: Mapped[str] = mapped_column(Text)  # le fichier, tel quel
    empreinte: Mapped[str] = mapped_column(String(64))  # SHA-256 du JSON canonique
    fichier_source: Mapped[str] = mapped_column(String(255))
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)

    maison: Mapped[Maison] = relationship()


class Inventaire(Base):
    __tablename__ = "inventaire"
    __table_args__ = (
        CheckConstraint(
            "statut IN ('" + "', '".join(STATUTS_INVENTAIRE) + "')", name="statut"
        ),
        CheckConstraint(
            "extraction IN ('" + "', '".join(ETATS_EXTRACTION) + "')", name="extraction"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    maison_id: Mapped[int] = mapped_column(ForeignKey("maison.id"))
    config_version_id: Mapped[int] = mapped_column(ForeignKey("config_version.id"))
    nom: Mapped[str] = mapped_column(String(200))
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    statut: Mapped[str] = mapped_column(String(20), default="ouvert")
    dossier_source: Mapped[str | None] = mapped_column(Text)
    extraction: Mapped[str] = mapped_column(
        String(20), default="non_lancee", server_default="non_lancee"
    )
    extraction_lancee_le: Mapped[datetime | None] = mapped_column(DateTime)
    motif_arret: Mapped[str | None] = mapped_column(Text)  # panne systématique
    # Cycle de vie (decisions.md 0168) : rien ne se supprime vraiment.
    archive_le: Mapped[datetime | None] = mapped_column(DateTime)
    supprime_le: Mapped[datetime | None] = mapped_column(DateTime)  # à la corbeille, restaurable
    clos_le: Mapped[datetime | None] = mapped_column(DateTime)  # lecture seule

    maison: Mapped[Maison] = relationship()
    config_version: Mapped[ConfigVersion] = relationship()
    # Les bouteilles de l'inventaire : les retirées n'en font plus partie
    # (relecture, export, comptes, file d'attente) mais restent en base.
    bouteilles: Mapped[list[FicheBouteille]] = relationship(
        primaryjoin="and_(Inventaire.id == FicheBouteille.inventaire_id, FicheBouteille.retiree == false())",
        order_by="FicheBouteille.position",
        viewonly=True,
    )
    toutes_les_bouteilles: Mapped[list[FicheBouteille]] = relationship(
        back_populates="inventaire", order_by="FicheBouteille.position"
    )
    photos: Mapped[list[Photo]] = relationship(order_by="Photo.ordre")
    groupes: Mapped[list[GroupePhotos]] = relationship(order_by="GroupePhotos.numero, GroupePhotos.id")


class GroupePhotos(Base):
    """Les photos d'UNE bouteille, telles que l'expert les a prises (decisions.md
    0166) : 1 à N photos ordonnées, la quantité saisie à la capture (« × N »).

    Créé au dépôt, avant la bouteille : tant qu'aucune bouteille n'y pointe, il
    est « en attente » (photos encore en cours d'ajout). Une bouteille née
    d'une séparation partage le groupe de sa source.
    """

    __tablename__ = "groupe_photos"
    __table_args__ = (
        UniqueConstraint("inventaire_id", "cle"),
        CheckConstraint("quantite >= 1", name="quantite"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventaire_id: Mapped[int] = mapped_column(ForeignKey("inventaire.id"))
    # Ordre de prise de vue : les bouteilles suivent cet ordre dans l'inventaire.
    numero: Mapped[int]
    # Clé donnée par l'appareil qui photographie : les photos d'une même
    # bouteille la portent, même si elles arrivent dans le désordre.
    cle: Mapped[str | None] = mapped_column(String(64))
    quantite: Mapped[int] = mapped_column(default=1)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)

    photos: Mapped[list[Photo]] = relationship(back_populates="groupe", order_by="Photo.rang")


class Photo(Base):
    """Une photo déposée. Le fichier est dans le stockage, pas dans la base."""

    __tablename__ = "photo"
    __table_args__ = (
        UniqueConstraint("inventaire_id", "empreinte"),  # même photo deux fois : refusée
        UniqueConstraint("inventaire_id", "ordre"),
        UniqueConstraint("groupe_id", "rang"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventaire_id: Mapped[int] = mapped_column(ForeignKey("inventaire.id"))
    chemin: Mapped[str] = mapped_column(String(255))  # relatif au stockage
    empreinte: Mapped[str] = mapped_column(String(64))  # SHA-256 du contenu
    nom_origine: Mapped[str] = mapped_column(String(255))
    prise_de_vue: Mapped[datetime | None] = mapped_column(DateTime)  # information seulement (0166)
    ordre: Mapped[int]  # ordre d'arrivée dans l'inventaire
    # Signature du fichier d'ORIGINE (nom, taille, date) fournie par le navigateur :
    # ne pas renvoyer une photo déjà reçue après une coupure (decisions.md 0127).
    signature_envoi: Mapped[str | None] = mapped_column(String(300))
    groupe_id: Mapped[int] = mapped_column(ForeignKey("groupe_photos.id"))
    rang: Mapped[int]  # place dans le groupe : « Photo 1 sur 3 » pour le modèle

    groupe: Mapped[GroupePhotos] = relationship(back_populates="photos")


class FicheBouteille(Base):
    """Une bouteille physique de l'inventaire, avec son cycle de vie.

    Nommée `FicheBouteille` pour ne pas se confondre avec `Bouteille`, le
    contrat des VALEURS (src/extract/schema.py) : ici le statut, la position,
    les photos ; là, ce qui a été lu.
    """

    __tablename__ = "bouteille"
    __table_args__ = (
        UniqueConstraint("inventaire_id", "identifiant"),
        UniqueConstraint("inventaire_id", "position"),
        CheckConstraint(
            "statut IN ('" + "', '".join(STATUTS_BOUTEILLE) + "')", name="statut"
        ),
        CheckConstraint("quantite >= 1", name="quantite"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventaire_id: Mapped[int] = mapped_column(ForeignKey("inventaire.id"))
    identifiant: Mapped[str] = mapped_column(String(20))  # « B-… », decisions.md 0065
    # Ses photos (decisions.md 0166) ; partagé avec les bouteilles nées d'une séparation.
    groupe_id: Mapped[int] = mapped_column(ForeignKey("groupe_photos.id"))
    position: Mapped[int]
    quantite: Mapped[int] = mapped_column(default=1)
    statut: Mapped[str] = mapped_column(String(20), default="a_extraire")
    # Réservation VIVANTE pendant « en_cours » (decisions.md 0109, 0110) : qui,
    # depuis quand, et le dernier signe de vie du worker qui la traite.
    reservee_par: Mapped[str | None] = mapped_column(String(100))
    reservee_le: Mapped[datetime | None] = mapped_column(DateTime)
    vu_le: Mapped[datetime | None] = mapped_column(DateTime)
    # Relecture (session 5, decisions.md 0139) : paire de photos signalée par
    # l'expert (la bouteille ne peut plus être validée), bouteille née d'une
    # séparation (elle lit la réponse du modèle de sa source tant qu'elle n'a
    # pas la sienne), temps de relecture cumulé, absences longues exclues.
    paire_signalee: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    separee_de_id: Mapped[int | None] = mapped_column(ForeignKey("bouteille.id"))
    temps_relecture_ms: Mapped[int] = mapped_column(default=0, server_default="0")
    # Retirée de l'inventaire (decisions.md 0168) : plus de relecture, d'export ni
    # de compte, mais rien n'est effacé, et elle peut être remise.
    retiree: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    inventaire: Mapped[Inventaire] = relationship(back_populates="toutes_les_bouteilles")
    groupe: Mapped[GroupePhotos] = relationship()
    extractions: Mapped[list[Extraction]] = relationship(order_by="Extraction.id")
    corrections: Mapped[list[Correction]] = relationship(order_by="Correction.id")
    evenements: Mapped[list[EvenementBouteille]] = relationship(order_by="EvenementBouteille.id")

    @property
    def photos(self) -> list[Photo]:
        """Ses photos, dans l'ordre où l'expert les a prises."""
        return list(self.groupe.photos)


class LimiteDebit(Base):
    """Limite de débit d'un modèle, PARTAGÉE par tous les workers (decisions.md 0114).

    `prochain_appel` espace les appels ; `pause_jusqu_a` suspend tout le monde
    après une limite de débit atteinte. En base, pas en mémoire : un
    redémarrage la respecte.
    """

    __tablename__ = "limite_debit"

    modele: Mapped[str] = mapped_column(String(100), primary_key=True)
    prochain_appel: Mapped[datetime | None] = mapped_column(DateTime)
    pause_jusqu_a: Mapped[datetime | None] = mapped_column(DateTime)


class Extraction(Base):
    """Un appel au modèle, et sa réponse brute — immuable (decisions.md 0072, 0076).

    Une bouteille peut en avoir plusieurs (relance) : la dernière réussie fait foi.
    """

    __tablename__ = "extraction"

    id: Mapped[int] = mapped_column(primary_key=True)
    bouteille_id: Mapped[int] = mapped_column(ForeignKey("bouteille.id"))
    # Ce que le modèle a répondu, tel quel : objet (appel d'outil), texte (JSON pas
    # encore interprété), ou NULL s'il n'a rien renvoyé.
    sortie_brute: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)
    modele: Mapped[str] = mapped_column(String(100))
    version_prompt: Mapped[str] = mapped_column(String(32))
    tokens_entree: Mapped[int | None]
    tokens_sortie: Mapped[int | None]
    duree_ms: Mapped[int]
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    erreur: Mapped[str | None] = mapped_column(Text)


class Correction(Base):
    """Une action de l'expert sur une bouteille — jamais modifiée ni supprimée.

    Une correction de valeur, ou un changement de statut (validation, remise à
    relire) sous le champ « statut » (decisions.md 0083).
    """

    __tablename__ = "correction"

    id: Mapped[int] = mapped_column(primary_key=True)
    bouteille_id: Mapped[int] = mapped_column(ForeignKey("bouteille.id"))
    champ: Mapped[str] = mapped_column(String(100))
    ancienne_valeur: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)
    nouvelle_valeur: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)
    auteur: Mapped[str] = mapped_column(String(200))
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)


class EvenementBouteille(Base):
    """Une action de l'expert qui n'est pas une valeur de champ : réanalyse,
    inversion des photos, signalement de paire (et sa levée), séparation
    (decisions.md 0139). Comme l'historique des corrections : jamais modifié ni
    supprimé."""

    __tablename__ = "evenement_bouteille"
    __table_args__ = (
        CheckConstraint("type IN ('" + "', '".join(TYPES_EVENEMENT) + "')", name="type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bouteille_id: Mapped[int] = mapped_column(ForeignKey("bouteille.id"))
    type: Mapped[str] = mapped_column(String(30))
    auteur: Mapped[str] = mapped_column(String(200))
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    detail: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)


class EvenementInventaire(Base):
    """Ce que l'expert fait à un inventaire : renommer, archiver, mettre à la
    corbeille, restaurer, clore, rouvrir (decisions.md 0168). Jamais modifié ni
    supprimé."""

    __tablename__ = "evenement_inventaire"
    __table_args__ = (
        CheckConstraint("type IN ('" + "', '".join(TYPES_EVENEMENT_INVENTAIRE) + "')", name="type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventaire_id: Mapped[int] = mapped_column(ForeignKey("inventaire.id"))
    type: Mapped[str] = mapped_column(String(30))
    auteur: Mapped[str] = mapped_column(String(200))
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    detail: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)


# --- garde-fous : la sortie du modèle et l'historique ne bougent jamais ---------------


class EnregistrementImmuable(Exception):
    """Tentative de modifier ou de supprimer ce qui ne doit jamais l'être."""


@event.listens_for(Extraction, "before_update")
def _sortie_brute_immuable(_mapper: Any, _connexion: Any, extraction: Extraction) -> None:
    # Seule `erreur` peut être complétée après coup (interprétation impossible,
    # decisions.md 0078) ; la réponse du modèle, jamais.
    etat = inspect(extraction)
    for champ in ("sortie_brute", "modele", "version_prompt", "tokens_entree", "tokens_sortie", "bouteille_id"):
        if etat.attrs[champ].history.has_changes():
            raise EnregistrementImmuable(
                f"Extraction n°{extraction.id} : « {champ} » ne se modifie jamais — "
                f"la sortie du modèle est immuable (decisions.md 0072)."
            )


@event.listens_for(Extraction, "before_delete")
def _extraction_jamais_supprimee(_mapper: Any, _connexion: Any, extraction: Extraction) -> None:
    raise EnregistrementImmuable(
        f"Extraction n°{extraction.id} : une extraction ne se supprime jamais (decisions.md 0072)."
    )


@event.listens_for(Correction, "before_update")
def _correction_immuable(_mapper: Any, _connexion: Any, correction: Correction) -> None:
    raise EnregistrementImmuable(
        f"Correction n°{correction.id} : l'historique ne se réécrit pas — une nouvelle "
        f"correction s'ajoute, l'ancienne reste (decisions.md 0072)."
    )


@event.listens_for(Correction, "before_delete")
def _correction_jamais_supprimee(_mapper: Any, _connexion: Any, correction: Correction) -> None:
    raise EnregistrementImmuable(
        f"Correction n°{correction.id} : l'historique ne se supprime pas (decisions.md 0072)."
    )


@event.listens_for(EvenementBouteille, "before_update")
def _evenement_immuable(_mapper: Any, _connexion: Any, evenement: EvenementBouteille) -> None:
    raise EnregistrementImmuable(
        f"Événement n°{evenement.id} : l'historique ne se réécrit pas (decisions.md 0139)."
    )


@event.listens_for(EvenementBouteille, "before_delete")
def _evenement_jamais_supprime(_mapper: Any, _connexion: Any, evenement: EvenementBouteille) -> None:
    raise EnregistrementImmuable(
        f"Événement n°{evenement.id} : l'historique ne se supprime pas (decisions.md 0139)."
    )


@event.listens_for(EvenementInventaire, "before_update")
def _evenement_inventaire_immuable(_mapper: Any, _connexion: Any, evenement: EvenementInventaire) -> None:
    raise EnregistrementImmuable(
        f"Événement d'inventaire n°{evenement.id} : l'historique ne se réécrit pas (decisions.md 0168)."
    )


@event.listens_for(EvenementInventaire, "before_delete")
def _evenement_inventaire_jamais_supprime(_mapper: Any, _connexion: Any, evenement: EvenementInventaire) -> None:
    raise EnregistrementImmuable(
        f"Événement d'inventaire n°{evenement.id} : l'historique ne se supprime pas (decisions.md 0168)."
    )
