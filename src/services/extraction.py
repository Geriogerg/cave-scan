"""Extraction en base : un appel tracé par bouteille, réponse brute conservée.

Trois règles (decisions.md 0072, 0078, 0079) :

1. La réponse du modèle est ENREGISTRÉE (et validée en base) AVANT d'être
   interprétée : si l'interprétation échoue, ce qu'il a répondu reste, et
   l'erreur est notée à côté. Un appel payé n'est jamais perdu.
2. Panne PASSAGÈRE ou réponse inexploitable : erreur sur LA bouteille, les
   autres continuent. Panne SYSTÉMATIQUE : enregistrée, puis l'inventaire
   s'arrête — la répéter sur 300 bouteilles ne servirait à rien.
3. Idempotence : une bouteille déjà extraite n'est jamais refaite, sauf
   relance forcée.

Session 3 : une bouteille n'est traitée qu'une fois RÉSERVÉE de façon atomique
dans la file d'attente en base (`file_attente`, decisions.md 0109) ; la ligne de
commande et le worker passent par le même `traiter_reservee`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from src.config.maison import ConfigMaison
from src.donnees.modeles import Correction, Extraction, FicheBouteille
from src.donnees.stockage import chemin_stocke
from src.extract.base import Extractor, interpreter
from src.services.file_attente import (
    identite_worker,
    liberer,
    reprendre_les_abandonnees,
    reserver_bouteille,
    reserver_cette_bouteille,
    signes_de_vie,
)
from src.services.inventaires import actualiser_statut, charger_inventaire, config_figee
from src.services.pilotage import lancer, relancer_erreurs

# Ce qui reste à faire quand la ligne de commande reprend un inventaire : à
# extraire, réservé (vivant ou abandonné), en erreur (relancé d'office, 0112).
STATUTS_A_EXTRAIRE = ("a_extraire", "en_cours", "erreur")

Progression = Callable[[int, int, FicheBouteille], None]


class BouteilleIntrouvable(LookupError):
    pass


class BouteilleOccupee(RuntimeError):
    """La bouteille est en cours de traitement par un autre worker."""


class ExtractionArretee(RuntimeError):
    """Panne systématique : enregistrée sur la bouteille, l'inventaire s'arrête là.

    Après correction de la cause (clé, modèle…), relancer l'inventaire reprend
    exactement à cette bouteille.
    """

    def __init__(self, bouteille: FicheBouteille, cause: BaseException) -> None:
        self.bouteille_id = bouteille.id
        self.identifiant = bouteille.identifiant
        self.position = bouteille.position
        self.cause = cause
        super().__init__(
            f"Extraction arrêtée à la bouteille n°{bouteille.position} ({bouteille.identifiant}) : "
            f"{type(cause).__name__} : {cause}"
        )


@dataclass(frozen=True)
class BilanExtraction:
    extraites: int = 0
    en_erreur: int = 0
    deja_faites: int = 0


def derniere_extraction_reussie(bouteille: FicheBouteille) -> Extraction | None:
    """La dernière extraction sans erreur : c'est elle qui fait foi.

    Lue par une requête, jamais par une liste chargée plus tôt dans la session :
    une extraction ajoutée depuis doit compter (decisions.md 0095).
    """
    return object_session(bouteille).scalars(
        select(Extraction)
        .where(Extraction.bouteille_id == bouteille.id, Extraction.erreur.is_(None))
        .order_by(Extraction.id.desc())
        .limit(1)
    ).first()


def extractions_de(bouteille: FicheBouteille) -> list[Extraction]:
    """Toutes les extractions de la bouteille, de la plus ancienne à la plus récente."""
    return list(
        object_session(bouteille).scalars(
            select(Extraction).where(Extraction.bouteille_id == bouteille.id).order_by(Extraction.id)
        )
    )


def charger_bouteille(session: Session, bouteille_id: int) -> FicheBouteille:
    bouteille = session.get(FicheBouteille, bouteille_id)
    if bouteille is None:
        raise BouteilleIntrouvable(f"Aucune bouteille n°{bouteille_id}.")
    return bouteille


def extraire_bouteille(
    session: Session,
    bouteille_id: int,
    extracteur: Extractor,
    stockage: Path,
    forcer: bool = False,
    worker: str | None = None,
) -> Extraction | None:
    """Extrait une bouteille. Idempotente : déjà extraite (ou validée), elle n'est
    pas refaite — sauf `forcer`, qui crée une NOUVELLE extraction (l'ancienne
    reste en base ; la dernière réussie fait foi).

    La bouteille est d'abord réservée de façon atomique ; si un autre worker la
    traite, `BouteilleOccupee`. Lève `ExtractionArretee` sur panne systématique,
    après l'avoir enregistrée.
    """
    bouteille = charger_bouteille(session, bouteille_id)
    if bouteille.statut in ("extraite", "validee") and not forcer:
        return derniere_extraction_reussie(bouteille)

    etait_validee = bouteille.statut == "validee"
    worker = worker or identite_worker("direct")
    permis = ("a_extraire", "erreur") + (("extraite", "validee") if forcer else ())
    if not reserver_cette_bouteille(session, bouteille_id, worker, permis):
        raise BouteilleOccupee(
            f"Bouteille n°{bouteille.position} ({bouteille.identifiant}) en cours de "
            f"traitement par un autre worker."
        )
    return traiter_reservee(session, bouteille_id, extracteur, stockage, worker, etait_validee)


def traiter_reservee(
    session: Session,
    bouteille_id: int,
    extracteur: Extractor,
    stockage: Path,
    worker: str,
    etait_validee: bool = False,
) -> Extraction:
    """Extrait une bouteille RÉSERVÉE par `worker` — le seul chemin d'extraction,
    pour la ligne de commande comme pour le worker.

    Tout ce que l'appel demande est lu AVANT lui : aucune transaction ne reste
    ouverte pendant l'appel au modèle (decisions.md 0113).
    """
    bouteille = charger_bouteille(session, bouteille_id)
    # Toutes ses photos, dans l'ordre de l'expert (decisions.md 0164, 0166).
    photos = [chemin_stocke(stockage, photo.chemin) for photo in bouteille.photos]
    config = config_figee(bouteille.inventaire)
    session.commit()

    debut = time.monotonic()
    try:
        sortie = extracteur.extraire_brut(photos)
    except Exception as erreur:  # `extraire_brut` ne lève que pour une panne systématique
        motif = f"panne systématique — {type(erreur).__name__} : {erreur}"
        bouteille.extractions.append(
            Extraction(
                sortie_brute=None,
                modele=getattr(extracteur, "modele", "inconnu"),
                version_prompt=getattr(extracteur, "version_prompt", "inconnue"),
                duree_ms=_millisecondes(debut),
                erreur=motif,
            )
        )
        _fin_de_reservation(bouteille, "erreur")
        # L'inventaire s'arrête : aucun autre worker ne le continue (0111).
        bouteille.inventaire.extraction = "arretee"
        bouteille.inventaire.motif_arret = (
            f"bouteille n°{bouteille.position} ({bouteille.identifiant}) : {motif}"
        )
        session.commit()
        raise ExtractionArretee(bouteille, erreur) from erreur
    except BaseException:  # Ctrl-C, arrêt demandé : la bouteille retourne à la file
        liberer(session, bouteille_id, worker)
        raise

    # 1. La réponse d'abord : en base, validée, avant toute interprétation.
    extraction = Extraction(
        sortie_brute=sortie.brut,
        modele=sortie.modele,
        version_prompt=sortie.version_prompt,
        tokens_entree=sortie.tokens_entree,
        tokens_sortie=sortie.tokens_sortie,
        duree_ms=_millisecondes(debut),
        erreur=sortie.erreur,
    )
    bouteille.extractions.append(extraction)
    session.commit()

    # 2. Puis l'interprétation et le statut.
    conclure(session, bouteille, extraction, config, etait_validee)
    return extraction


def conclure(
    session: Session,
    bouteille: FicheBouteille,
    extraction: Extraction,
    config: ConfigMaison | None = None,
    etait_validee: bool = False,
) -> None:
    """Interprète une réponse déjà ENREGISTRÉE et fixe le statut de la bouteille.

    Si l'interprétation échoue, la réponse reste ; seule l'erreur est notée à
    côté (decisions.md 0078). Sert aussi à terminer, sans nouvel appel, une
    bouteille dont le worker est mort juste après avoir reçu la réponse (0110).
    """
    if extraction.erreur is None:
        try:
            interpreter(extraction.sortie_brute, config or config_figee(bouteille.inventaire))
        except Exception as erreur:
            extraction.erreur = f"réponse inexploitable — {erreur}"

    _fin_de_reservation(bouteille, "erreur" if extraction.erreur else "extraite")
    if etait_validee:
        # Relance forcée d'une bouteille validée : elle est à relire (0083).
        bouteille.corrections.append(
            Correction(
                champ="statut",
                ancienne_valeur="validee",
                nouvelle_valeur=bouteille.statut,
                auteur=f"relance forcée ({extraction.modele})",
            )
        )
    actualiser_statut(bouteille.inventaire)
    session.commit()


def conclure_sans_appel(session: Session, bouteille_id: int) -> Extraction | None:
    """Termine une bouteille reprise dont la réponse est déjà en base."""
    bouteille = charger_bouteille(session, bouteille_id)
    extraction = derniere_extraction_reussie(bouteille)
    if extraction is None:  # pragma: no cover — la reprise l'a vérifié
        return None
    conclure(session, bouteille, extraction)
    return extraction


def _fin_de_reservation(bouteille: FicheBouteille, statut: str) -> None:
    bouteille.statut = statut
    bouteille.reservee_par = bouteille.reservee_le = bouteille.vu_le = None


def extraire_inventaire(
    session: Session,
    inventaire_id: int,
    extracteur: Extractor,
    stockage: Path,
    progression: Progression | None = None,
) -> BilanExtraction:
    """Extraction AU PREMIER PLAN (ligne de commande) : relance les erreurs, lance
    l'inventaire, reprend ses bouteilles abandonnées, puis traite la file de cet
    inventaire dans l'ordre, une bouteille à la fois.

    Mêmes réservations que le worker : les deux peuvent tourner ensemble sans
    jamais extraire deux fois la même bouteille (decisions.md 0112).
    """
    inventaire = charger_inventaire(session, inventaire_id)
    worker = identite_worker("ligne-de-commande")
    relancer_erreurs(session, inventaire_id)
    lancer(session, inventaire_id)
    reprises = reprendre_les_abandonnees(session, worker, inventaire_id=inventaire_id)
    for bouteille_id in reprises.a_conclure:
        conclure_sans_appel(session, bouteille_id)

    for bouteille in inventaire.bouteilles:
        session.refresh(bouteille)
    a_faire = sum(1 for b in inventaire.bouteilles if b.statut == "a_extraire")
    deja_faites = sum(1 for b in inventaire.bouteilles if b.statut in ("extraite", "validee"))
    extraites = en_erreur = 0
    with signes_de_vie(session.get_bind(), worker):
        rang = 0
        while (bouteille_id := reserver_bouteille(session, worker, inventaire_id)) is not None:
            rang += 1
            if progression is not None:
                progression(rang, a_faire, charger_bouteille(session, bouteille_id))
            extraction = traiter_reservee(session, bouteille_id, extracteur, stockage, worker)
            if extraction.erreur is None:
                extraites += 1
            else:
                en_erreur += 1
    return BilanExtraction(extraites=extraites, en_erreur=en_erreur, deja_faites=deja_faites)


def reste_a_extraire(session: Session, inventaire_id: int) -> int:
    """Combien de bouteilles une relance traiterait — sans créer de client."""
    inventaire = charger_inventaire(session, inventaire_id)
    return sum(1 for b in inventaire.bouteilles if b.statut in STATUTS_A_EXTRAIRE)


def _millisecondes(debut: float) -> int:
    return round((time.monotonic() - debut) * 1000)
