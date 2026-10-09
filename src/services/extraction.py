"""Extraction en base : un appel tracé par bouteille, réponse brute conservée.

Trois règles (decisions.md 0072, 0078, 0079) :

1. La réponse du modèle est ENREGISTRÉE (et validée en base) AVANT d'être
   interprétée : si l'interprétation échoue, ce qu'il a répondu reste, et
   l'erreur est notée à côté. Un appel payé n'est jamais perdu.
2. Panne PASSAGÈRE ou réponse inexploitable : erreur sur LA bouteille, les
   autres continuent. Panne SYSTÉMATIQUE : enregistrée, puis l'inventaire
   s'arrête — la répéter sur 300 bouteilles ne servirait à rien.
3. Idempotence : une bouteille déjà extraite n'est jamais refaite, sauf
   relance forcée. Reprendre un inventaire arrêté ne refait donc que ce qui
   reste (à extraire, interrompu, en erreur).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from src.donnees.modeles import Correction, Extraction, FicheBouteille
from src.donnees.stockage import chemin_stocke
from src.extract.base import Extractor, interpreter
from src.services.inventaires import actualiser_statut, charger_inventaire, config_figee

# Ce qui reste à faire quand on (re)lance un inventaire : `en_cours` est une
# extraction interrompue (coupure, arrêt), `erreur` mérite une nouvelle chance.
STATUTS_A_EXTRAIRE = ("a_extraire", "en_cours", "erreur")

Progression = Callable[[int, int, FicheBouteille], None]


class BouteilleIntrouvable(LookupError):
    pass


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
) -> Extraction | None:
    """Extrait une bouteille. Idempotente : déjà extraite (ou validée), elle n'est
    pas refaite — sauf `forcer`, qui crée une NOUVELLE extraction (l'ancienne
    reste en base ; la dernière réussie fait foi).

    Lève `ExtractionArretee` sur panne systématique, après l'avoir enregistrée.
    """
    bouteille = charger_bouteille(session, bouteille_id)
    if bouteille.statut in ("extraite", "validee") and not forcer:
        return derniere_extraction_reussie(bouteille)

    etait_validee = bouteille.statut == "validee"
    bouteille.statut = "en_cours"
    session.commit()

    debut = time.monotonic()
    try:
        sortie = extracteur.extraire_brut(
            etiquette=chemin_stocke(stockage, bouteille.photo_etiquette.chemin),
            contre_etiquette=chemin_stocke(stockage, bouteille.photo_contre.chemin),
        )
    except Exception as erreur:  # `extraire_brut` ne lève que pour une panne systématique
        bouteille.extractions.append(
            Extraction(
                sortie_brute=None,
                modele=getattr(extracteur, "modele", "inconnu"),
                version_prompt=getattr(extracteur, "version_prompt", "inconnue"),
                duree_ms=_millisecondes(debut),
                erreur=f"panne systématique — {type(erreur).__name__} : {erreur}",
            )
        )
        bouteille.statut = "erreur"
        session.commit()
        raise ExtractionArretee(bouteille, erreur) from erreur

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

    # 2. Puis l'interprétation : si elle échoue, la réponse reste ; seule
    #    l'erreur est notée à côté (decisions.md 0078).
    if extraction.erreur is None:
        try:
            interpreter(extraction.sortie_brute, config_figee(bouteille.inventaire))
        except Exception as erreur:
            extraction.erreur = f"réponse inexploitable — {erreur}"

    bouteille.statut = "erreur" if extraction.erreur else "extraite"
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
    return extraction


def extraire_inventaire(
    session: Session,
    inventaire_id: int,
    extracteur: Extractor,
    stockage: Path,
    progression: Progression | None = None,
) -> BilanExtraction:
    """Enchaîne les bouteilles qui restent à faire, dans l'ordre (séquentiel).

    Les bouteilles déjà extraites ne sont jamais refaites : après un arrêt,
    relancer reprend là où l'on s'était arrêté (decisions.md 0079).
    """
    inventaire = charger_inventaire(session, inventaire_id)
    a_faire = [b for b in inventaire.bouteilles if b.statut in STATUTS_A_EXTRAIRE]
    extraites = en_erreur = 0
    for rang, bouteille in enumerate(a_faire, start=1):
        if progression is not None:
            progression(rang, len(a_faire), bouteille)
        extraction = extraire_bouteille(session, bouteille.id, extracteur, stockage)
        if extraction is not None and extraction.erreur is None:
            extraites += 1
        else:
            en_erreur += 1
    return BilanExtraction(
        extraites=extraites,
        en_erreur=en_erreur,
        deja_faites=len(inventaire.bouteilles) - len(a_faire),
    )


def reste_a_extraire(session: Session, inventaire_id: int) -> int:
    """Combien de bouteilles une relance traiterait — sans créer de client."""
    inventaire = charger_inventaire(session, inventaire_id)
    return sum(1 for b in inventaire.bouteilles if b.statut in STATUTS_A_EXTRAIRE)


def _millisecondes(debut: float) -> int:
    return round((time.monotonic() - debut) * 1000)
