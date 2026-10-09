"""Relecture par l'expert : valeurs courantes, corrections, validation.

La sortie du modèle n'est JAMAIS modifiée (decisions.md 0072) :
- `valeurs_modele` : ce que le modèle a lu, et seulement ça — c'est ce que
  mesure la comparaison au listing de l'expert (0081) ;
- `valeurs_courantes` : la même chose, remplacée champ par champ par la
  dernière correction ; RECALCULÉE à chaque lecture, jamais stockée ;
- `corriger` : ajoute un enregistrement à l'historique, valide la saisie selon
  le type de la colonne (0082) ;
- `valider` : la bouteille est relue et approuvée (0083).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from src.config.maison import COLONNE_QUANTITE, CLES_RESERVEES_AU_PIPELINE, ConfigMaison
from src.donnees.modeles import Correction, FicheBouteille
from src.extract.base import interpreter
from src.extract.schema import (
    NATURE_DES_CHAMPS,
    Bouteille,
    Couleur,
    Effervescence,
    Format,
)
from src.services.extraction import (
    charger_bouteille,
    derniere_extraction_reussie,
    extractions_de,
)
from src.services.inventaires import actualiser_statut, config_figee

# Le changement de statut d'une bouteille (validation, remise à relire) est
# tracé dans l'historique sous ce nom (decisions.md 0083).
CHAMP_STATUT = "statut"

# Vocabulaire v0 des champs de liste qu'une config ne redéfinit pas.
VOCABULAIRE_V0: dict[str, type[StrEnum]] = {
    "couleur": Couleur,
    "effervescence": Effervescence,
    "format": Format,
}


class CorrectionRefusee(ValueError):
    """Champ inconnu, colonne non corrigeable, ou saisie invalide pour son type."""


class ValidationRefusee(ValueError):
    """La bouteille ne peut pas être validée dans son état actuel."""


# --- lire --------------------------------------------------------------------------------


def valeurs_modele(session: Session, bouteille_id: int) -> Bouteille:
    """Ce que le modèle a lu — sans aucune correction. C'est ce que la comparaison
    mesure : le score du MODÈLE (decisions.md 0081)."""
    return _valeurs_du_modele(charger_bouteille(session, bouteille_id))


def valeurs_courantes(session: Session, bouteille_id: int) -> Bouteille:
    """Modèle + dernière correction de chaque champ (decisions.md 0072).

    Les corrections s'appliquent dans l'ordre où elles ont été faites : pour un
    même champ, la dernière l'emporte, les précédentes restent dans l'historique.
    """
    bouteille = charger_bouteille(session, bouteille_id)
    valeurs = _valeurs_du_modele(bouteille)
    for correction in corrections_de(bouteille):
        if correction.champ != CHAMP_STATUT:
            _poser(valeurs, correction.champ, correction.nouvelle_valeur)
    return valeurs


def corrections_de(bouteille: FicheBouteille) -> list[Correction]:
    """L'historique de la bouteille, dans l'ordre — lu par une requête, jamais par
    une liste chargée plus tôt dans la session (decisions.md 0095)."""
    return list(
        object_session(bouteille).scalars(
            select(Correction).where(Correction.bouteille_id == bouteille.id).order_by(Correction.id)
        )
    )


def _valeurs_du_modele(bouteille: FicheBouteille) -> Bouteille:
    extraction = derniere_extraction_reussie(bouteille)
    if extraction is None:
        toutes = extractions_de(bouteille)
        derniere = toutes[-1] if toutes else None
        motif = derniere.erreur if derniere is not None else "pas encore extraite"
        valeurs = Bouteille(champs_a_verifier=["tous"], notes=f"Extraction sans résultat : {motif}.")
    else:
        try:
            valeurs = interpreter(extraction.sortie_brute, config_figee(bouteille.inventaire))
        except Exception as erreur:  # ne doit pas arriver : validée à l'extraction
            valeurs = Bouteille(
                champs_a_verifier=["tous"], notes=f"Réponse du modèle illisible : {erreur}."
            )
    valeurs.id = bouteille.identifiant
    valeurs.quantite = bouteille.quantite
    return valeurs


def _poser(valeurs: Bouteille, champ: str, valeur: Any) -> None:
    if champ == COLONNE_QUANTITE:
        valeurs.quantite = valeur
    elif champ in NATURE_DES_CHAMPS:
        setattr(valeurs, champ, valeur)
    else:  # colonne propre à la maison : best effort, ou saisie de l'expert
        valeurs.valeurs_maison[champ] = valeur


def valeur_courante(valeurs: Bouteille, champ: str) -> Any:
    if champ == COLONNE_QUANTITE:
        return valeurs.quantite
    if champ in NATURE_DES_CHAMPS:
        valeur = getattr(valeurs, champ)
        return valeur.value if isinstance(valeur, StrEnum) else valeur
    return valeurs.valeurs_maison.get(champ)


# --- corriger ----------------------------------------------------------------------------


def corriger(
    session: Session, bouteille_id: int, champ: str, nouvelle_valeur: Any, auteur: str
) -> Correction:
    """Enregistre une correction — jamais un écrasement de l'extraction.

    Refuse un champ inconnu, une colonne calculée par l'outil, et une saisie
    invalide pour le type de la colonne : quantité = entier ≥ 1, liste = code
    connu (un libellé est ramené à son code), nombre = nombre, texte = libre
    (decisions.md 0082). Sur une bouteille validée, la remet à relire et
    rouvre l'inventaire (0083).
    """
    auteur = _auteur(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    valeur = _saisie_valide(config_figee(bouteille.inventaire), champ, nouvelle_valeur)

    ancienne = valeur_courante(valeurs_courantes(session, bouteille_id), champ)
    correction = Correction(
        champ=champ,
        ancienne_valeur=ancienne,
        nouvelle_valeur=valeur,
        auteur=auteur,
    )
    bouteille.corrections.append(correction)
    if champ == COLONNE_QUANTITE:
        bouteille.quantite = valeur  # valeur courante ; l'historique est la correction

    if bouteille.statut == "validee":
        bouteille.statut = "extraite"
        bouteille.corrections.append(
            Correction(
                champ=CHAMP_STATUT,
                ancienne_valeur="validee",
                nouvelle_valeur="extraite",
                auteur=auteur,
            )
        )
    actualiser_statut(bouteille.inventaire)
    session.commit()
    return correction


def champs_corrigeables(config: ConfigMaison) -> list[str]:
    """Ce que l'expert peut corriger : les colonnes lues par le modèle, les
    colonnes expert, et les champs v0 extraits même non affichés."""
    depuis_config = [
        colonne.cle for colonne in config.colonnes if colonne.source != "systeme"
    ]
    return list(dict.fromkeys([*depuis_config, *NATURE_DES_CHAMPS, COLONNE_QUANTITE]))


def _saisie_valide(config: ConfigMaison, champ: str, valeur: Any) -> Any:
    """La valeur à enregistrer, validée selon le type de la colonne."""
    if champ == CHAMP_STATUT:
        raise CorrectionRefusee("Le statut ne se corrige pas : utiliser « valider ».")

    colonne = config.colonne(champ)
    if colonne is not None and colonne.source == "systeme":
        raise CorrectionRefusee(
            f"« {champ} » est calculée par l'outil (colonne système) : elle ne se corrige pas."
        )
    if champ == COLONNE_QUANTITE:
        return _quantite(valeur)
    if champ in CLES_RESERVEES_AU_PIPELINE:
        raise CorrectionRefusee(f"« {champ} » est géré par l'outil : il ne se corrige pas.")

    if colonne is not None:
        type_, codes = colonne.type, colonne
    elif champ in NATURE_DES_CHAMPS:
        type_, codes = NATURE_DES_CHAMPS[champ], VOCABULAIRE_V0.get(champ)
    else:
        raise CorrectionRefusee(
            f"Champ inconnu : « {champ} ». Champs corrigeables : "
            f"{', '.join(champs_corrigeables(config))}."
        )

    if type_ == "liste":
        return _code(champ, codes, valeur)
    if type_ == "nombre":
        return _nombre(champ, valeur)
    return "" if valeur is None else str(valeur).strip()  # texte libre


def _quantite(valeur: Any) -> int:
    texte = str(valeur).strip()
    if isinstance(valeur, bool) or not texte.isdigit() or int(texte) < 1:
        raise CorrectionRefusee(f"Quantité invalide : « {valeur} » (entier ≥ 1 attendu).")
    return int(texte)


def _nombre(champ: str, valeur: Any) -> float | int:
    if isinstance(valeur, bool):
        raise CorrectionRefusee(f"« {champ} » attend un nombre, reçu « {valeur} ».")
    if isinstance(valeur, (int, float)):
        return valeur
    try:
        nombre = float(str(valeur).strip().replace(",", "."))  # « 13,5 » à la française
    except ValueError:
        raise CorrectionRefusee(f"« {champ} » attend un nombre, reçu « {valeur} ».") from None
    return int(nombre) if nombre.is_integer() else nombre


def _code(champ: str, vocabulaire: Any, valeur: Any) -> str:
    """Un code connu ; un libellé de la maison est ramené à son code."""
    if hasattr(vocabulaire, "code_depuis"):  # colonne de la config
        code = vocabulaire.code_depuis(valeur)
        connus = [f"{v.code} ({v.libelle})" for v in vocabulaire.valeurs]
    else:  # enum v0
        texte = str(valeur).strip().casefold()
        code = next((m.value for m in vocabulaire if m.value == texte), None)
        connus = [m.value for m in vocabulaire]
    if code is None:
        raise CorrectionRefusee(
            f"« {valeur} » n'est pas une valeur de la liste « {champ} ». "
            f"Valeurs possibles : {', '.join(connus)}."
        )
    return code


def _auteur(auteur: str) -> str:
    auteur = (auteur or "").strip()
    if not auteur:
        raise CorrectionRefusee("Une correction ou une validation a toujours un auteur.")
    return auteur


# --- valider -----------------------------------------------------------------------------


def valider(session: Session, bouteille_id: int, auteur: str) -> None:
    """La bouteille est relue et approuvée. Seule une bouteille extraite peut
    l'être : une bouteille en erreur ne le peut pas, si bien qu'un inventaire qui
    en contient une ne passe jamais à `valide` (decisions.md 0083)."""
    auteur = _auteur(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    if bouteille.statut == "validee":
        return  # déjà validée : rien à faire, rien à tracer
    if bouteille.statut == "erreur":
        raise ValidationRefusee(
            f"Bouteille n°{bouteille.position} ({bouteille.identifiant}) en erreur : "
            f"relancer son extraction avant de la valider."
        )
    if bouteille.statut != "extraite":
        raise ValidationRefusee(
            f"Bouteille n°{bouteille.position} ({bouteille.identifiant}) pas encore "
            f"extraite (statut « {bouteille.statut} »)."
        )

    bouteille.statut = "validee"
    bouteille.corrections.append(
        Correction(
            champ=CHAMP_STATUT,
            ancienne_valeur="extraite",
            nouvelle_valeur="validee",
            auteur=auteur,
        )
    )
    actualiser_statut(bouteille.inventaire)
    session.commit()

