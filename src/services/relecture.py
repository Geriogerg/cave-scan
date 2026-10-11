"""Relecture par l'expert : valeurs courantes, corrections, validation.

La sortie du modèle n'est JAMAIS modifiée (decisions.md 0072) :
- `valeurs_modele` : ce que le modèle a lu, et seulement ça — c'est ce que
  mesure la comparaison au listing de l'expert (0081) ;
- `valeurs_courantes` : la même chose, remplacée champ par champ par la
  dernière correction ; RECALCULÉE à chaque lecture, jamais stockée ;
- `corriger` : ajoute un enregistrement à l'historique, valide la saisie selon
  le type de la colonne (0082) ;
- `valider` : la bouteille est relue et approuvée (0169).

L'écran de relecture (session 5) passe par les mêmes fonctions, avec en plus :
- une VERSION de la bouteille telle qu'affichée : enregistrer par-dessus une
  modification faite ailleurs (autre onglet) est d'abord signalé (0142) ;
- `valider_en_relecture` : ce que l'écran affiche encore sans l'avoir
  enregistré est enregistré d'abord, et une saisie refusée bloque la
  validation — côté serveur, pas seulement dans le navigateur (0143).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from src.config.maison import COLONNE_QUANTITE, CLES_RESERVEES_AU_PIPELINE, NOYAU_CANONIQUE, ConfigMaison
from src.donnees.modeles import Correction, EvenementBouteille, Extraction, FicheBouteille
from src.extract.base import interpreter
from src.extract.schema import (
    NATURE_DES_CHAMPS,
    Bouteille,
    Couleur,
    Effervescence,
    Format,
    est_abstention,
)
from src.normalize.normalize import normalize
from src.services.extraction import (
    charger_bouteille,
    derniere_extraction_reussie,
    extractions_de,
)
from src.services.inventaires import actualiser_statut, charger_inventaire, config_figee, verifier_modifiable

# Le changement de statut d'une bouteille (validation, remise à relire) est
# tracé dans l'historique sous ce nom (decisions.md 0169).
CHAMP_STATUT = "statut"

# Vocabulaire v0 des champs de liste qu'une config ne redéfinit pas.
VOCABULAIRE_V0: dict[str, type[StrEnum]] = {
    "couleur": Couleur,
    "effervescence": Effervescence,
    "format": Format,
}

# Temps de relecture envoyé par l'écran : borné, une valeur absurde (horloge
# du poste déréglée) ne doit pas fausser les statistiques du pilote.
TEMPS_RELECTURE_MAX_MS = 60 * 60 * 1000


class CorrectionRefusee(ValueError):
    """Champ inconnu, colonne non corrigeable, ou saisie invalide pour son type."""


class ValidationRefusee(ValueError):
    """La bouteille ne peut pas être validée dans son état actuel."""


class SaisiesRefusees(ValidationRefusee):
    """Validation refusée : des saisies affichées à l'écran sont invalides.

    `refus` : champ -> raison, pour les montrer à côté de chaque champ.
    """

    def __init__(self, refus: dict[str, str]) -> None:
        self.refus = refus
        super().__init__(
            "Bouteille non validée : "
            + ("une saisie est refusée" if len(refus) == 1 else f"{len(refus)} saisies sont refusées")
            + ". Corrigez "
            + ("le champ signalé" if len(refus) == 1 else "les champs signalés")
            + " puis validez de nouveau."
        )


class ModificationConcurrente(RuntimeError):
    """La bouteille a changé depuis qu'elle a été affichée (decisions.md 0142).

    `changements` : ce qui a changé, en clair. Rien n'a été écrit : l'écran
    propose de recharger, ou d'enregistrer quand même.
    """

    def __init__(self, changements: list[str]) -> None:
        self.changements = changements
        detail = " ; ".join(changements) if changements else "modification non détaillée"
        super().__init__(
            f"Cette bouteille a été modifiée ailleurs depuis que vous l'avez ouverte ({detail}). "
            f"Rechargez-la pour voir ces changements, ou enregistrez quand même : "
            f"l'historique garde toutes les corrections."
        )


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
    return _avec_corrections(_valeurs_du_modele(bouteille), corrections_de(bouteille))


def valeurs_courantes_de_l_inventaire(session: Session, inventaire_id: int) -> dict[int, Bouteille]:
    """`valeurs_courantes` de TOUTES les bouteilles d'un inventaire, en quelques
    requêtes au lieu de deux par bouteille : l'écran de relecture compte et
    filtre 300 bouteilles à chaque page. Même calcul, mêmes résultats (un test
    le vérifie)."""
    inventaire = charger_inventaire(session, inventaire_id)
    config = config_figee(inventaire)
    bouteilles = {bouteille.id: bouteille for bouteille in inventaire.bouteilles}
    ids = list(bouteilles)

    reussies = {
        extraction.bouteille_id: extraction
        for extraction in session.scalars(
            select(Extraction).where(
                Extraction.id.in_(
                    select(func.max(Extraction.id))
                    .where(Extraction.bouteille_id.in_(ids), Extraction.erreur.is_(None))
                    .group_by(Extraction.bouteille_id)
                )
            )
        )
    }
    dernieres = {
        extraction.bouteille_id: extraction
        for extraction in session.scalars(
            select(Extraction).where(
                Extraction.id.in_(
                    select(func.max(Extraction.id)).where(Extraction.bouteille_id.in_(ids)).group_by(Extraction.bouteille_id)
                )
            )
        )
    }
    corrections: dict[int, list[Correction]] = {bouteille_id: [] for bouteille_id in ids}
    for correction in session.scalars(
        select(Correction).where(Correction.bouteille_id.in_(ids)).order_by(Correction.id)
    ):
        corrections[correction.bouteille_id].append(correction)

    def qui_fait_foi(bouteille: FicheBouteille) -> Extraction | None:
        vues: set[int] = set()
        while bouteille is not None and bouteille.id not in vues:
            vues.add(bouteille.id)
            if bouteille.id in reussies:
                return reussies[bouteille.id]
            bouteille = bouteilles.get(bouteille.separee_de_id) if bouteille.separee_de_id else None
        return None

    return {
        bouteille.id: _avec_corrections(
            _construire(bouteille, qui_fait_foi(bouteille), dernieres.get(bouteille.id), config),
            corrections[bouteille.id],
        )
        for bouteille in bouteilles.values()
    }


def corrections_de(bouteille: FicheBouteille) -> list[Correction]:
    """L'historique de la bouteille, dans l'ordre — lu par une requête, jamais par
    une liste chargée plus tôt dans la session (decisions.md 0095)."""
    return list(
        object_session(bouteille).scalars(
            select(Correction).where(Correction.bouteille_id == bouteille.id).order_by(Correction.id)
        )
    )


def extraction_qui_fait_foi(bouteille: FicheBouteille) -> Extraction | None:
    """La dernière extraction réussie de la bouteille. Une bouteille née d'une
    séparation, tant qu'elle n'a pas la sienne, lit celle de sa source : mêmes
    photos, même lecture (decisions.md 0144)."""
    session = object_session(bouteille)
    vues: set[int] = set()
    while bouteille is not None and bouteille.id not in vues:
        vues.add(bouteille.id)
        extraction = derniere_extraction_reussie(bouteille)
        if extraction is not None:
            return extraction
        bouteille = session.get(FicheBouteille, bouteille.separee_de_id) if bouteille.separee_de_id else None
    return None


def _valeurs_du_modele(bouteille: FicheBouteille) -> Bouteille:
    extraction = extraction_qui_fait_foi(bouteille)
    derniere = None
    if extraction is None:  # le motif de l'échec : la dernière tentative
        toutes = extractions_de(bouteille)
        derniere = toutes[-1] if toutes else None
    return _construire(bouteille, extraction, derniere, config_figee(bouteille.inventaire))


def _construire(
    bouteille: FicheBouteille,
    extraction: Extraction | None,
    derniere: Extraction | None,
    config: ConfigMaison,
) -> Bouteille:
    """Ce que le modèle a lu, à partir de l'extraction qui fait foi — ou, faute
    d'extraction réussie, une abstention complète qui dit pourquoi."""
    if extraction is None:
        motif = derniere.erreur if derniere is not None else "pas encore extraite"
        valeurs = Bouteille(champs_a_verifier=["tous"], notes=f"Extraction sans résultat : {motif}.")
    else:
        try:
            valeurs = interpreter(extraction.sortie_brute, config)
        except Exception as erreur:  # ne doit pas arriver : validée à l'extraction
            valeurs = Bouteille(
                champs_a_verifier=["tous"], notes=f"Réponse du modèle illisible : {erreur}."
            )
    # La normalisation (identité en v0, decisions.md 0007) s'applique à la
    # LECTURE : la réponse brute reste intacte, ses règles futures vaudront
    # aussi pour les inventaires déjà extraits.
    valeurs = normalize(valeurs)
    valeurs.id = bouteille.identifiant
    valeurs.quantite = bouteille.quantite
    return valeurs


def _avec_corrections(valeurs: Bouteille, corrections: list[Correction]) -> Bouteille:
    for correction in corrections:
        if correction.champ != CHAMP_STATUT:
            _poser(valeurs, correction.champ, correction.nouvelle_valeur)
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


def valeur_pour_formulaire(valeur: Any) -> str:
    """Ce qu'un champ du formulaire de relecture affiche. Une abstention ou une
    absence de valeur est un champ VIDE, présenté « à remplir » — jamais le mot
    « non_lisible » posé comme une valeur (guide de session 5, §2)."""
    if valeur is None or est_abstention(valeur):
        return ""
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    return str(valeur).strip()


# --- version affichée --------------------------------------------------------------------


def version_de(session: Session, bouteille_id: int) -> str:
    """L'état de la bouteille tel qu'un écran l'affiche : le dernier enregistrement
    de chacun de ses historiques. Toute correction, validation, extraction ou
    action (inversion, signalement, séparation, réanalyse) le change
    (decisions.md 0142)."""
    ligne = session.execute(
        select(
            select(func.max(Correction.id)).where(Correction.bouteille_id == bouteille_id).scalar_subquery(),
            select(func.max(Extraction.id)).where(Extraction.bouteille_id == bouteille_id).scalar_subquery(),
            select(func.max(EvenementBouteille.id))
            .where(EvenementBouteille.bouteille_id == bouteille_id)
            .scalar_subquery(),
        )
    ).one()
    return "-".join(str(numero or 0) for numero in ligne)


def verifier_version(session: Session, bouteille_id: int, version_vue: str | None) -> None:
    """Lève `ModificationConcurrente` si la bouteille a changé depuis `version_vue`.
    Sans version (ligne de commande, API sans écran) : rien à vérifier."""
    if version_vue is None:
        return
    actuelle = version_de(session, bouteille_id)
    if version_vue != actuelle:
        raise ModificationConcurrente(_changements_depuis(session, bouteille_id, version_vue))


def _changements_depuis(session: Session, bouteille_id: int, version_vue: str) -> list[str]:
    """Ce qui a été enregistré depuis la version affichée, en clair."""
    try:
        correction_vue, extraction_vue, evenement_vue = (int(morceau) for morceau in version_vue.split("-"))
    except ValueError:
        return []
    changements = []
    for correction in session.scalars(
        select(Correction)
        .where(Correction.bouteille_id == bouteille_id, Correction.id > correction_vue)
        .order_by(Correction.id)
    ):
        quand = f"{correction.auteur}, {heure_locale(correction.cree_le)}"
        if correction.champ == CHAMP_STATUT:
            action = "validée" if correction.nouvelle_valeur == "validee" else "remise à relire"
            changements.append(f"bouteille {action} ({quand})")
        else:
            changements.append(
                f"« {correction.champ} » : {_lisible(correction.ancienne_valeur)} → "
                f"{_lisible(correction.nouvelle_valeur)} ({quand})"
            )
    nouvelles = session.scalar(
        select(func.count(Extraction.id)).where(Extraction.bouteille_id == bouteille_id, Extraction.id > extraction_vue)
    )
    if nouvelles:
        changements.append("nouvelle analyse du modèle")
    for evenement in session.scalars(
        select(EvenementBouteille)
        .where(EvenementBouteille.bouteille_id == bouteille_id, EvenementBouteille.id > evenement_vue)
        .order_by(EvenementBouteille.id)
    ):
        changements.append(
            f"{LIBELLES_EVENEMENT.get(evenement.type, evenement.type)} "
            f"({evenement.auteur}, {heure_locale(evenement.cree_le)})"
        )
    return changements


LIBELLES_EVENEMENT = {
    "reanalyse": "réanalyse demandée",
    "inversion_photos": "photos inversées",  # avant les groupes de photos (0166) : historique seulement
    "signalement_paire": "problème de photos signalé",
    "signalement_leve": "signalement de photos levé",
    "separation": "bouteille séparée",
    "retrait": "bouteille retirée de l'inventaire",
    "remise": "bouteille remise dans l'inventaire",
}


def heure_locale(instant: datetime) -> str:
    """Une date de la base (UTC sans fuseau, decisions.md 0086) à l'heure du poste."""
    return instant.replace(tzinfo=UTC).astimezone().strftime("%H:%M")


def _lisible(valeur: Any) -> str:
    if valeur is None or est_abstention(valeur):
        return "vide"
    return f"« {valeur} »"


# --- corriger ----------------------------------------------------------------------------


def corriger(
    session: Session, bouteille_id: int, champ: str, nouvelle_valeur: Any, auteur: str
) -> Correction:
    """Enregistre une correction — jamais un écrasement de l'extraction.

    Refuse un champ inconnu, une colonne calculée par l'outil, et une saisie
    invalide pour le type de la colonne : quantité = entier ≥ 1, liste = code
    connu (un libellé est ramené à son code), nombre = nombre, texte = libre
    (decisions.md 0082). Sur une bouteille validée, la remet à relire et
    rouvre l'inventaire (0169).
    """
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    valeur = _saisie_valide(config_figee(bouteille.inventaire), champ, nouvelle_valeur)
    return enregistrer_correction(session, bouteille, champ, valeur, auteur)


def enregistrer_correction(
    session: Session, bouteille: FicheBouteille, champ: str, valeur: Any, auteur: str
) -> Correction:
    """Ajoute à l'historique une valeur DÉJÀ validée, puis applique la règle de
    statut : une bouteille validée qu'on modifie est à relire (decisions.md 0169).
    Jamais sur un inventaire clos (lecture seule, 0168)."""
    verifier_modifiable(bouteille.inventaire)
    ancienne = valeur_courante(valeurs_courantes(session, bouteille.id), champ)
    correction = Correction(
        champ=champ,
        ancienne_valeur=ancienne,
        nouvelle_valeur=valeur,
        auteur=auteur,
    )
    bouteille.corrections.append(correction)
    if champ == COLONNE_QUANTITE:
        bouteille.quantite = valeur  # valeur courante ; l'historique est la correction
    remettre_a_relire(bouteille, auteur)
    actualiser_statut(bouteille.inventaire)
    session.commit()
    return correction


def remettre_a_relire(bouteille: FicheBouteille, auteur: str, statut: str = "extraite") -> None:
    """Une bouteille validée dont quelque chose change n'est plus validée : son
    statut passe à `statut`, et c'est tracé dans l'historique (decisions.md 0169).
    Une bouteille validée en saisie manuelle (aucune analyse réussie) redevient
    « en erreur », pas « extraite » (0169)."""
    if bouteille.statut != "validee":
        return
    if statut == "extraite" and extraction_qui_fait_foi(bouteille) is None:
        statut = "erreur"
    bouteille.statut = statut
    bouteille.corrections.append(
        Correction(champ=CHAMP_STATUT, ancienne_valeur="validee", nouvelle_valeur=statut, auteur=auteur)
    )


def champs_obligatoires(config: ConfigMaison) -> list[str]:
    """Ce qu'une bouteille dont l'analyse a échoué doit avoir, saisi à la main,
    pour être validée : les colonnes du noyau canonique PRÉSENTES dans la config
    de la maison — toujours saisissables à l'écran (choix du 2026-10-11, 0169)."""
    return [cle for cle in NOYAU_CANONIQUE if config.colonne(cle) is not None]


def champs_obligatoires_manquants(session: Session, bouteille: FicheBouteille) -> list[str]:
    """Les champs obligatoires encore vides (ou en abstention), par leur nom à l'écran."""
    config = config_figee(bouteille.inventaire)
    courantes = valeurs_courantes(session, bouteille.id)
    return [
        config.colonne(cle).nom
        for cle in champs_obligatoires(config)
        if est_abstention(valeur_courante(courantes, cle)) or valeur_courante(courantes, cle) in (None, "")
    ]


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
        return quantite_valide(valeur)
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


def quantite_valide(valeur: Any) -> int:
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


def auteur_valide(auteur: str) -> str:
    auteur = (auteur or "").strip()
    if not auteur:
        raise CorrectionRefusee("Une correction ou une validation a toujours un auteur.")
    return auteur


# --- corriger depuis l'écran de relecture --------------------------------------------------


def corriger_en_relecture(
    session: Session,
    bouteille_id: int,
    champ: str,
    saisie: Any,
    auteur: str,
    version_vue: str | None,
    forcer: bool = False,
) -> Correction | None:
    """Enregistre la saisie d'UN champ de l'écran, dès la sortie du champ.

    Par `corriger` (mêmes règles de saisie, même historique), avec deux
    garde-fous de plus : une bouteille modifiée ailleurs depuis son affichage
    n'est pas écrasée sans que l'expert le demande (`forcer`), et une saisie
    identique à la valeur courante n'ajoute rien à l'historique. Renvoie la
    correction, ou None s'il n'y avait rien à enregistrer.
    """
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    if not forcer:
        verifier_version(session, bouteille_id, version_vue)
    config = config_figee(bouteille.inventaire)
    a_enregistrer, refus = _saisies_a_enregistrer(config, valeurs_courantes(session, bouteille_id), {champ: saisie})
    if refus:
        raise CorrectionRefusee(refus[champ])
    if champ not in a_enregistrer:
        return None
    return enregistrer_correction(session, bouteille, champ, a_enregistrer[champ], auteur)


def revenir_a_la_valeur_du_modele(
    session: Session,
    bouteille_id: int,
    champ: str,
    auteur: str,
    version_vue: str | None = None,
    forcer: bool = False,
) -> Correction:
    """Remet la lecture du modèle dans un champ corrigé — par une NOUVELLE
    correction : rien n'est supprimé de l'historique (guide de session 5, §2)."""
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    if not forcer:
        verifier_version(session, bouteille_id, version_vue)
    config = config_figee(bouteille.inventaire)
    colonne = config.colonne(champ)
    if champ not in champs_corrigeables(config) or champ == COLONNE_QUANTITE or (
        colonne is not None and colonne.source == "expert"
    ):
        raise CorrectionRefusee(f"« {champ} » n'a pas de valeur lue par le modèle : rien à remettre.")
    lue = valeur_courante(valeurs_modele(session, bouteille_id), champ)
    if lue == valeur_courante(valeurs_courantes(session, bouteille_id), champ):
        raise CorrectionRefusee(f"« {champ} » porte déjà la valeur lue par le modèle.")
    return enregistrer_correction(session, bouteille, champ, lue, auteur)


def _saisies_a_enregistrer(
    config: ConfigMaison, courantes: Bouteille, saisies: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Ce que l'écran affiche et qui n'est pas encore en base : (valeurs validées
    à enregistrer, raisons des refus par champ).

    Une saisie identique à ce que le champ affichait au chargement n'est pas une
    modification ; une saisie qui revient à la même valeur (« 13,5 » pour 13.5)
    non plus : l'historique ne garde que de vrais changements.
    """
    a_enregistrer: dict[str, Any] = {}
    refus: dict[str, str] = {}
    for champ, saisie in saisies.items():
        actuelle = valeur_courante(courantes, champ)
        texte = "" if saisie is None else str(saisie).strip()
        if texte == valeur_pour_formulaire(actuelle):
            continue
        try:
            valeur = _saisie_valide(config, champ, saisie)
        except CorrectionRefusee as erreur:
            refus[champ] = str(erreur)
            continue
        if valeur != actuelle:
            a_enregistrer[champ] = valeur
    return a_enregistrer, refus


# --- valider -----------------------------------------------------------------------------


def valider(session: Session, bouteille_id: int, auteur: str, temps_ms: int | None = None) -> None:
    """La bouteille est relue et approuvée — facultatif (0168). Une bouteille
    extraite peut l'être ; une bouteille dont l'analyse a ÉCHOUÉ aussi, une fois
    ses champs obligatoires saisis à la main (« saisie manuelle », tracée par le
    passage « erreur » -> « validée » dans l'historique, 0169) : elle ne bloque
    plus l'inventaire. Une bouteille dont les photos sont signalées, non, tant
    que le signalement n'est pas levé (0145).

    `temps_ms` : temps passé sur la bouteille à l'écran, absences longues
    exclues ; il s'ajoute au temps de relecture de la bouteille (0169).
    """
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    verifier_modifiable(bouteille.inventaire)
    if bouteille.statut == "validee":
        _ajouter_temps(bouteille, temps_ms)
        session.commit()
        return  # déjà validée : rien d'autre à faire, rien à tracer
    if bouteille.statut == "erreur":
        manquants = champs_obligatoires_manquants(session, bouteille)
        if manquants:
            raise ValidationRefusee(
                f"Bouteille n°{bouteille.position} ({bouteille.identifiant}) : l'analyse a échoué. Pour la "
                f"valider en saisie manuelle, remplissez d'abord : {', '.join(manquants)} — ou réanalysez-la."
            )
    elif bouteille.statut != "extraite":
        raise ValidationRefusee(
            f"Bouteille n°{bouteille.position} ({bouteille.identifiant}) pas encore "
            f"extraite (statut « {bouteille.statut} »)."
        )
    if bouteille.paire_signalee:
        raise ValidationRefusee(
            f"Bouteille n°{bouteille.position} ({bouteille.identifiant}) : un problème de photos est "
            f"signalé. Elle ne peut pas être validée tant que le signalement n'est pas levé."
        )

    ancien = bouteille.statut  # « erreur » : validée en saisie manuelle
    bouteille.statut = "validee"
    bouteille.corrections.append(
        Correction(
            champ=CHAMP_STATUT,
            ancienne_valeur=ancien,
            nouvelle_valeur="validee",
            auteur=auteur,
        )
    )
    _ajouter_temps(bouteille, temps_ms)
    actualiser_statut(bouteille.inventaire)
    session.commit()


def ajouter_temps_de_relecture(session: Session, bouteille_id: int, temps_ms: int | None) -> None:
    """Le temps passé sur une bouteille ouverte, SANS la valider : envoyé par
    l'écran en la quittant, et chaque minute (decisions.md 0169). Cumulé avec
    celui des validations, borné à 1 h par envoi. Une mesure, pas une
    modification : comptée même sur un inventaire clos."""
    _ajouter_temps(charger_bouteille(session, bouteille_id), temps_ms)
    session.commit()


def _ajouter_temps(bouteille: FicheBouteille, temps_ms: int | None) -> None:
    if temps_ms is None:
        return
    temps = max(0, min(int(temps_ms), TEMPS_RELECTURE_MAX_MS))
    bouteille.temps_relecture_ms = (bouteille.temps_relecture_ms or 0) + temps


def valider_en_relecture(
    session: Session,
    bouteille_id: int,
    auteur: str,
    saisies: Mapping[str, Any],
    version_vue: str | None,
    temps_ms: int | None = None,
    forcer: bool = False,
) -> None:
    """Valider depuis l'écran (Entrée, Ctrl+Entrée ou le bouton).

    `saisies` : ce que chaque champ de l'écran affiche. Ce qui n'est pas encore
    en base est enregistré d'abord, par les règles de `corriger` — une sortie de
    champ manquée ne perd rien. Une saisie invalide bloque la validation
    (`SaisiesRefusees`, raison par champ) ; les saisies valides sont gardées.
    Si la bouteille a été modifiée ailleurs depuis son affichage, rien n'est
    écrit sans `forcer` (decisions.md 0142, 0143).
    """
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    if not forcer:
        verifier_version(session, bouteille_id, version_vue)
    config = config_figee(bouteille.inventaire)
    a_enregistrer, refus = _saisies_a_enregistrer(config, valeurs_courantes(session, bouteille_id), saisies)
    for champ, valeur in a_enregistrer.items():
        enregistrer_correction(session, bouteille, champ, valeur, auteur)
    if refus:
        raise SaisiesRefusees(refus)
    valider(session, bouteille_id, auteur, temps_ms)


def valider_inventaire(session: Session, inventaire_id: int, auteur: str) -> int:
    """Constate que l'inventaire est entièrement relu — sans valider AUCUNE
    bouteille à la place de l'expert : chaque bouteille se valide une par une,
    après avoir été vue (decisions.md 0138, qui remplace 0120).

    Refusé, avec un message pour l'expert, s'il reste une bouteille en erreur,
    pas encore extraite, signalée ou à relire. Renvoie le nombre de bouteilles
    validées (toutes).
    """
    auteur_valide(auteur)
    inventaire = charger_inventaire(session, inventaire_id)
    if inventaire.statut == "brouillon":
        raise ValidationRefusee("Cet inventaire est encore en brouillon : ses photos n'ont pas été analysées.")
    en_erreur = [b.position for b in inventaire.bouteilles if b.statut == "erreur"]
    pas_extraites = [b.position for b in inventaire.bouteilles if b.statut in ("a_extraire", "en_cours")]
    signalees = [b.position for b in inventaire.bouteilles if b.statut == "extraite" and b.paire_signalee]
    a_relire = [b.position for b in inventaire.bouteilles if b.statut == "extraite" and not b.paire_signalee]
    raisons = []
    if en_erreur:
        raisons.append(
            f"{len(en_erreur)} bouteille(s) en erreur ({_positions(en_erreur)}) : les réanalyser, ou "
            f"saisir leurs champs obligatoires à la main pour les valider"
        )
    if pas_extraites:
        raisons.append(f"{len(pas_extraites)} bouteille(s) pas encore extraite(s) ({_positions(pas_extraites)})")
    if signalees:
        raisons.append(
            f"{len(signalees)} bouteille(s) avec un problème de photos signalé ({_positions(signalees)})"
        )
    if a_relire:
        raisons.append(
            f"{len(a_relire)} bouteille(s) à relire ({_positions(a_relire)}) : chaque bouteille se "
            f"valide une par une, depuis l'écran de relecture"
        )
    if raisons:
        raise ValidationRefusee("L'inventaire ne peut pas encore être validé : " + " ; ".join(raisons) + ".")
    # Rien à écrire : chaque validation de bouteille a déjà tenu le statut de
    # l'inventaire à jour (`actualiser_statut`).
    return len(inventaire.bouteilles)


def _positions(positions: list[int]) -> str:
    montrees = ", ".join(f"n°{p}" for p in positions[:10])
    return montrees + (" …" if len(positions) > 10 else "")
