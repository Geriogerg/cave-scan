"""Ce que les écrans consultent : inventaires, bouteilles paginées, fiche
d'une bouteille, export en mémoire — et, pour l'écran de relecture, la fiche
complète d'une bouteille, la navigation et le récapitulatif.

Fonctions de service comme les autres (decisions.md 0080, 0118) : l'API ne fait
que les appeler et mettre leur résultat en forme. Rien n'est calculé dans une
route.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.maison import COLONNE_QUANTITE, LIBELLE_NON_DETERMINABLE, Colonne, ConfigMaison
from src.donnees.modeles import Correction, EvenementBouteille, FicheBouteille, Inventaire
from src.export.excel_writer import a_relire, regrouper
from src.extract.schema import DOUTE_PAIRE_PHOTOS, NON_DETERMINABLE, Bouteille, est_abstention
from src.services.cas_particuliers import bouteilles_liees, evenements_de
from src.services.cycle_de_vie import bilan
from src.services.extraction import BouteilleIntrouvable, extractions_de
from src.services.inventaires import charger_inventaire, config_figee
from src.services.pilotage import Avancement, avancement
from src.textes import accord
from src.services.relecture import (
    extraction_qui_fait_foi,
    CHAMP_STATUT,
    LIBELLES_EVENEMENT,
    champs_corrigeables,
    champs_obligatoires,
    corrections_de,
    valeur_courante,
    valeur_pour_formulaire,
    valeurs_courantes,
    valeurs_courantes_de_l_inventaire,
    valeurs_modele,
    version_de,
)
from src.services.restitution import StatsInventaire, exporter, stats_inventaire

PAR_PAGE_MAX = 200


# --- inventaires -----------------------------------------------------------------------------


@dataclass(frozen=True)
class EtatInventaire:
    inventaire: Inventaire
    avancement: Avancement
    stats: StatsInventaire


def etat_inventaire(session: Session, inventaire_id: int) -> EtatInventaire:
    """Statut, progression et statistiques d'un inventaire."""
    return EtatInventaire(
        inventaire=charger_inventaire(session, inventaire_id),
        avancement=avancement(session, inventaire_id),
        stats=stats_inventaire(session, inventaire_id),
    )


def exporter_en_octets(session: Session, inventaire_id: int) -> tuple[str, bytes]:
    """L'Excel de l'inventaire, en mémoire : (nom de fichier proposé, contenu)."""
    inventaire = charger_inventaire(session, inventaire_id)
    with tempfile.TemporaryDirectory(prefix="cave-scan-export-") as dossier:
        chemin = exporter(session, inventaire_id, Path(dossier) / "export.xlsx")
        contenu = Path(chemin).read_bytes()
    return nom_du_fichier_excel(inventaire), contenu


def nom_du_fichier_excel(inventaire: Inventaire) -> str:
    """« Vente de printemps — 2026-10-13.xlsx » plutôt que « inventaire_5.xlsx »
    (T3-DS2) ; sans les caractères interdits dans un nom de fichier."""
    import re

    nom = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", inventaire.nom).strip(" .") or f"inventaire {inventaire.id}"
    return f"{nom[:80]} — {inventaire.cree_le:%Y-%m-%d}.xlsx"


def entete_telechargement(nom: str) -> str:
    """`Content-Disposition` d'un fichier au nom accentué : un nom de secours en
    ASCII, et le vrai nom en UTF-8 (RFC 6266) — un en-tête HTTP n'accepte pas
    « — » ni « é » tels quels."""
    import unicodedata
    from urllib.parse import quote

    secours = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii").replace('"', "")
    return f"attachment; filename=\"{secours or 'export.xlsx'}\"; filename*=UTF-8''{quote(nom)}"


# --- bouteilles ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumeBouteille:
    id: int
    position: int
    identifiant: str
    statut: str
    quantite: int
    a_verifier: bool
    domaine: Any
    appellation: Any
    millesime: Any


@dataclass(frozen=True)
class PageBouteilles:
    total: int
    page: int
    par_page: int
    bouteilles: list[ResumeBouteille] = field(default_factory=list)


def parcourir_bouteilles(
    session: Session,
    inventaire_id: int,
    statut: str | None = None,
    a_verifier: bool | None = None,
    page: int = 1,
    par_page: int = 50,
) -> PageBouteilles:
    """Les bouteilles d'un inventaire, dans l'ordre, filtrées puis paginées.

    « À vérifier » est la MÊME règle que le surlignage de l'export (`a_relire`,
    decisions.md 0055) : l'écran et l'Excel disent la même chose.
    """
    inventaire = charger_inventaire(session, inventaire_id)
    config = config_figee(inventaire)
    resumes = []
    for bouteille in inventaire.bouteilles:
        if statut is not None and bouteille.statut != statut:
            continue
        valeurs = valeurs_courantes(session, bouteille.id)
        douteuse = a_relire(valeurs, config)
        if a_verifier is not None and douteuse != a_verifier:
            continue
        resumes.append(
            ResumeBouteille(
                id=bouteille.id,
                position=bouteille.position,
                identifiant=bouteille.identifiant,
                statut=bouteille.statut,
                quantite=valeurs.quantite,
                a_verifier=douteuse,
                domaine=valeur_courante(valeurs, "domaine"),
                appellation=valeur_courante(valeurs, "appellation"),
                millesime=valeur_courante(valeurs, "millesime"),
            )
        )
    debut = (page - 1) * par_page
    return PageBouteilles(total=len(resumes), page=page, par_page=par_page, bouteilles=resumes[debut : debut + par_page])


def bouteille_de(session: Session, inventaire_id: int, bouteille_id: int) -> FicheBouteille:
    """La bouteille, si et seulement si elle appartient à CET inventaire."""
    inventaire = charger_inventaire(session, inventaire_id)
    bouteille = session.get(FicheBouteille, bouteille_id)
    if bouteille is None or bouteille.inventaire_id != inventaire_id:
        # Le nom de la vente, pas des numéros internes que l'écran ne montre pas (T8-D6).
        raise BouteilleIntrouvable(f"Cette bouteille n'existe pas (ou plus) dans « {inventaire.nom} ».")
    return bouteille


@dataclass(frozen=True)
class FicheComplete:
    """Ce que l'API rend pour une bouteille."""

    bouteille: FicheBouteille
    valeurs_courantes: dict[str, Any]
    valeurs_modele: dict[str, Any]
    champs_corriges: list[str]
    champs_a_verifier: list[str]
    a_verifier: bool
    notes: Any
    historique: list[Correction]
    nb_extractions: int
    photos: list[int]  # ses photos, dans l'ordre de l'expert (decisions.md 0166)
    precedente_id: int | None
    suivante_id: int | None
    version: str = ""
    evenements: list[EvenementBouteille] = field(default_factory=list)


def fiche_bouteille(session: Session, inventaire_id: int, bouteille_id: int) -> FicheComplete:
    bouteille = bouteille_de(session, inventaire_id, bouteille_id)
    config = config_figee(bouteille.inventaire)
    courantes, modele = valeurs_courantes(session, bouteille.id), valeurs_modele(session, bouteille.id)
    champs = champs_corrigeables(config)
    historique = corrections_de(bouteille)
    voisines_ = session.execute(
        select(
            select(func.max(FicheBouteille.id))
            .where(FicheBouteille.inventaire_id == inventaire_id, FicheBouteille.position == bouteille.position - 1)
            .scalar_subquery(),
            select(func.max(FicheBouteille.id))
            .where(FicheBouteille.inventaire_id == inventaire_id, FicheBouteille.position == bouteille.position + 1)
            .scalar_subquery(),
        )
    ).one()
    return FicheComplete(
        bouteille=bouteille,
        valeurs_courantes={champ: valeur_courante(courantes, champ) for champ in champs},
        valeurs_modele={
            champ: valeur_courante(modele, champ)
            for champ in champs
            if not _saisie_expert(config, champ)  # le modèle ne remplit jamais ces colonnes
        },
        champs_corriges=sorted({c.champ for c in historique if c.champ != CHAMP_STATUT}),
        champs_a_verifier=list(modele.champs_a_verifier),
        a_verifier=a_relire(courantes, config),
        notes=modele.notes,
        historique=historique,
        nb_extractions=len(extractions_de(bouteille)),
        photos=[photo.id for photo in bouteille.photos],
        precedente_id=voisines_[0],
        suivante_id=voisines_[1],
        version=version_de(session, bouteille.id),
        evenements=evenements_de(session, bouteille.id),
    )


def _saisie_expert(config, champ: str) -> bool:
    colonne = config.colonne(champ)
    return colonne is not None and colonne.source == "expert"


def tableau_des_inventaires(session: Session) -> list[tuple[Inventaire, Avancement]]:
    """L'accueil : chaque inventaire avec son avancement, le plus récent d'abord."""
    from src.services.inventaires import lister_inventaires

    return [(inventaire, avancement(session, inventaire.id)) for inventaire in reversed(lister_inventaires(session))]


# --- écran de relecture (session 5) ---------------------------------------------------------

# Ce que la relecture parcourt : les bouteilles pas encore extraites sont sautées
# (et comptées à part) tant que l'extraction continue (guide de session 5, §1).
NAVIGABLES = ("extraite", "validee", "erreur")


@dataclass(frozen=True)
class EtatRelecture:
    """Une bouteille vue de la barre de relecture : de quoi compter et naviguer."""

    id: int
    position: int
    identifiant: str
    statut: str
    a_verifier: bool  # même règle que le surlignage de l'export (`a_relire`)
    paire_signalee: bool

    @property
    def navigable(self) -> bool:
        return self.statut in NAVIGABLES

    @property
    def reste_a_relire(self) -> bool:
        """Ce que l'expert a encore à traiter : extraite non validée, ou en erreur."""
        return self.statut in ("extraite", "erreur")


def etats_de_relecture(session: Session, inventaire_id: int) -> list[EtatRelecture]:
    """Toutes les bouteilles de l'inventaire, dans l'ordre, en quelques requêtes :
    chaque page de relecture compte et filtre les 300 bouteilles."""
    inventaire = charger_inventaire(session, inventaire_id)
    config = config_figee(inventaire)
    valeurs = valeurs_courantes_de_l_inventaire(session, inventaire_id)
    return [
        EtatRelecture(
            id=bouteille.id,
            position=bouteille.position,
            identifiant=bouteille.identifiant,
            statut=bouteille.statut,
            a_verifier=a_relire(valeurs[bouteille.id], config),
            paire_signalee=bouteille.paire_signalee,
        )
        for bouteille in inventaire.bouteilles
    ]


def voisines(
    etats: list[EtatRelecture], bouteille_id: int, a_verifier_seulement: bool = False
) -> tuple[int | None, int | None]:
    """Bouteilles précédente et suivante (J / K, flèches) : extraites, validées
    ou en erreur — et, avec le filtre, seulement celles à vérifier."""
    position = next(etat.position for etat in etats if etat.id == bouteille_id)
    candidates = [e for e in etats if e.navigable and (e.a_verifier or not a_verifier_seulement)]
    precedentes = [e.id for e in candidates if e.position < position]
    suivantes = [e.id for e in candidates if e.position > position]
    return (precedentes[-1] if precedentes else None, suivantes[0] if suivantes else None)


def prochaine_a_relire(
    etats: list[EtatRelecture], apres_position: int | None = None, a_verifier_seulement: bool = False
) -> int | None:
    """La bouteille à présenter : la première non validée APRÈS `apres_position`,
    sinon la première non validée depuis le début. Une bouteille dont la paire
    est signalée ne peut pas être validée : elle attend au récapitulatif. None
    quand il ne reste rien à relire."""
    candidates = [
        e for e in etats
        if e.reste_a_relire and not e.paire_signalee and (e.a_verifier or not a_verifier_seulement)
    ]
    if apres_position is not None:
        apres = [e for e in candidates if e.position > apres_position]
        if apres:
            return apres[0].id
    return candidates[0].id if candidates else None


@dataclass(frozen=True)
class Compteurs:
    """La barre de progression de la relecture."""

    total: int
    validees: int
    a_relire: int  # extraites non validées (signalées comprises)
    a_verifier: int  # parmi elles, celles où un doute reste (même règle que l'export)
    en_erreur: int
    pas_encore_extraites: int
    signalees: int


def compter(etats: list[EtatRelecture]) -> Compteurs:
    return Compteurs(
        total=len(etats),
        validees=sum(1 for e in etats if e.statut == "validee"),
        a_relire=sum(1 for e in etats if e.statut == "extraite"),
        a_verifier=sum(1 for e in etats if e.statut == "extraite" and e.a_verifier),
        en_erreur=sum(1 for e in etats if e.statut == "erreur"),
        pas_encore_extraites=sum(1 for e in etats if e.statut in ("a_extraire", "en_cours")),
        signalees=sum(1 for e in etats if e.paire_signalee),
    )


ORIGINES = {
    "lue": "lue sur la photo",
    "deduite": "déduite par le modèle",
    "proposee": "proposée, à vérifier",
    "corrigee": "corrigée par l'expert",
    "saisie": "saisie par l'expert",
    "defaut": "par défaut",
    "depot": "saisie au dépôt",
    "vide": "à saisir",
    "a_remplir": "à remplir",
}


@dataclass(frozen=True)
class ChampRelecture:
    """Un champ du formulaire de relecture, dans l'ordre de la config."""

    cle: str
    nom: str  # en-tête de la colonne pour la maison
    type: str  # texte, liste, nombre
    source: str  # modele, modele_best_effort, expert
    saisie: str  # ce que le champ affiche ; vide = « à remplir »
    options: list[tuple[str, str]]  # listes : (code, libellé), « Non déterminable » compris
    origine: str  # une clé d'ORIGINES
    a_remplir: bool  # abstention : affichée « à remplir », jamais comme une valeur
    a_verifier: bool  # doute précis du modèle sur ce champ
    lue: str | None  # la lecture du modèle, en clair ; None pour une colonne expert
    peut_revenir: bool  # corrigé, et différent de la lecture du modèle
    avertissement: str = ""  # saisie acceptée mais inhabituelle (millésime, T4-DS4)

    @property
    def origine_en_clair(self) -> str:
        return ORIGINES[self.origine]


@dataclass(frozen=True)
class LigneHistorique:
    le: datetime
    auteur: str
    texte: str


@dataclass(frozen=True)
class FicheRelecture:
    """Tout ce que l'écran de relecture affiche pour une bouteille."""

    inventaire: Inventaire
    bouteille: FicheBouteille
    version: str  # l'état affiché : un enregistrement fait ailleurs depuis est signalé
    champs: list[ChampRelecture]
    doutes_ailleurs: list[str]  # doutes du modèle sur des champs que la maison n'affiche pas
    doute_paire: bool  # le modèle doute lui-même que les photos montrent la même bouteille
    notes_modele: str
    erreur: str | None  # bouteille en erreur : la raison, en clair
    obligatoires: list[str]  # en erreur : ce qu'il faut saisir pour la valider à la main (0169)
    en_attente: bool  # analyse ou réanalyse demandée, pas encore faite
    historique: list[LigneHistorique]
    compteurs: Compteurs
    precedente_id: int | None
    suivante_id: int | None
    a_precharger: list[int]  # photos de la bouteille suivante
    separee_de: FicheBouteille | None
    liees: list[FicheBouteille]  # nées de la même séparation
    fusionnee_avec: list[str]  # identifiants avec lesquels l'export la fusionnera
    regroupement: list[str]  # noms des colonnes de regroupement de la maison
    filtre: bool
    rang: int = 0  # place parmi les bouteilles présentes (une retirée ne compte plus, T4-B8)
    attente: Attente | None = None  # en attente du modèle : en pause ? déjà lue ?


@dataclass(frozen=True)
class Attente:
    """Une bouteille que le modèle n'a pas (encore) lue : ce que l'écran en dit (T5-B1)."""

    arretee: str  # "" si l'analyse tourne ; sinon son état (« en pause »…) : rien ne bougera seul
    deja_essayee: bool  # une lecture a déjà été tentée : c'est une réanalyse


def attente_de(bouteille: FicheBouteille) -> Attente | None:
    if bouteille.statut not in ("a_extraire", "en_cours"):
        return None
    extraction = bouteille.inventaire.extraction
    arretee = "" if extraction == "lancee" or bouteille.statut == "en_cours" else (
        "pas encore lancée" if extraction == "non_lancee" else "en pause"
    )
    return Attente(arretee=arretee, deja_essayee=bool(extractions_de(bouteille)))


def fiche_de_relecture(
    session: Session, inventaire_id: int, bouteille_id: int, a_verifier_seulement: bool = False
) -> FicheRelecture:
    bouteille = bouteille_de(session, inventaire_id, bouteille_id)
    inventaire = bouteille.inventaire
    config = config_figee(inventaire)
    courantes, modele = valeurs_courantes(session, bouteille.id), valeurs_modele(session, bouteille.id)
    corriges = {c.champ for c in corrections_de(bouteille) if c.champ != CHAMP_STATUT}

    best_effort = {colonne.cle for colonne in config.colonnes_best_effort}
    doutes = set(modele.champs_a_verifier) - best_effort
    if bouteille.statut in ("a_extraire", "en_cours") and extraction_qui_fait_foi(bouteille) is None:
        doutes = set()  # pas encore lue : ni doute ni certitude du modèle (T6-B7)
    affiches = [colonne for colonne in config.colonnes if colonne.source != "systeme"]
    champs = [
        _champ(colonne, courantes, modele, colonne.cle in corriges, "tous" in doutes or colonne.cle in doutes)
        for colonne in affiches
    ]
    noms_affiches = {colonne.cle for colonne in affiches}

    etats = etats_de_relecture(session, inventaire_id)
    precedente, suivante = voisines(etats, bouteille.id, a_verifier_seulement)
    liees = bouteilles_liees(session, bouteille)
    return FicheRelecture(
        inventaire=inventaire,
        bouteille=bouteille,
        version=version_de(session, bouteille.id),
        champs=champs,
        doutes_ailleurs=sorted(d for d in doutes if d not in noms_affiches and d not in ("tous", DOUTE_PAIRE_PHOTOS)),
        doute_paire=DOUTE_PAIRE_PHOTOS in modele.champs_a_verifier,
        # Pas de « Note du modèle » inventée pour une bouteille qu'il n'a jamais lue (T5-B1).
        notes_modele=modele.notes if bouteille.statut != "erreur" and extraction_qui_fait_foi(bouteille) else "",
        erreur=raison_de_l_erreur(bouteille) if bouteille.statut == "erreur" else None,
        obligatoires=[config.colonne(cle).nom for cle in champs_obligatoires(config)],
        en_attente=bouteille.statut in ("a_extraire", "en_cours"),
        attente=attente_de(bouteille),
        historique=_historique(session, bouteille, config),
        compteurs=compter(etats),
        rang=next((n for n, e in enumerate(etats, start=1) if e.id == bouteille.id), bouteille.position),
        precedente_id=precedente,
        suivante_id=suivante,
        a_precharger=_photos_de(session, suivante),
        separee_de=session.get(FicheBouteille, bouteille.separee_de_id) if bouteille.separee_de_id else None,
        liees=liees,
        fusionnee_avec=_fusionnees_a_l_export(session, courantes, liees, config),
        regroupement=[config.colonne(cle).nom for cle in config.regroupement_export if config.colonne(cle)],
        filtre=a_verifier_seulement,
    )


def _champ(colonne: Colonne, courantes: Bouteille, modele: Bouteille, corrige: bool, douteux: bool) -> ChampRelecture:
    valeur = valeur_courante(courantes, colonne.cle)
    expert = colonne.source == "expert"
    lue = None if expert else valeur_courante(modele, colonne.cle)
    # Revenue à la lecture du modèle (« Revenir à la valeur du modèle ») : le
    # champ redit d'où vient sa valeur, pas « corrigée » (rapport du testeur, T1-m6).
    corrige = corrige and (expert or valeur != lue)
    if expert and not corrige and colonne.cle == COLONNE_QUANTITE:
        origine = "depot" if valeur not in (None, 1) else "defaut"
    elif expert:
        origine = "saisie" if corrige else "vide"
    elif corrige:
        origine = "saisie" if est_abstention(lue) else "corrigee"
    elif est_abstention(valeur):
        origine = "a_remplir"
    elif colonne.source == "modele_best_effort":
        origine = "proposee"
    elif colonne.cle == "couleur" and str(getattr(modele.couleur_source, "value", modele.couleur_source)) == "inferee":
        origine = "deduite"
    else:
        origine = "lue"
    return ChampRelecture(
        cle=colonne.cle,
        nom=colonne.nom,
        type=colonne.type,
        source=colonne.source,
        saisie=valeur_pour_formulaire(valeur),
        options=[(v.code, v.libelle) for v in colonne.valeurs] if colonne.type == "liste" else [],
        origine=origine,
        a_remplir=not expert and est_abstention(valeur),
        a_verifier=douteux and not expert,
        lue=None if expert else en_clair(colonne, lue),
        peut_revenir=corrige and not expert and lue != valeur,
        avertissement=_millesime_inhabituel(colonne.cle, valeur),
    )


def _millesime_inhabituel(cle: str, valeur: Any) -> str:
    """« 20152009 » tapé au doigt : accepté (jamais deviné à la place de l'expert),
    mais signalé (T4-DS4)."""
    import re

    if cle != "millesime" or valeur in (None, "") or est_abstention(valeur):
        return ""
    return "" if re.fullmatch(r"(1[6-9]|20)\d\d|NM", str(valeur).strip(), re.IGNORECASE) else (
        "Inhabituel : 4 chiffres (ex. 2015) ou NM attendus."
    )


def en_clair(colonne: Colonne | None, valeur: Any) -> str:
    """Une valeur telle que l'expert la lit : libellé de la maison, abstention en mots."""
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        return "vide"
    if est_abstention(valeur):
        return LIBELLE_NON_DETERMINABLE.lower() if str(valeur) == NON_DETERMINABLE else "non lisible"
    if colonne is not None and colonne.type == "liste":
        return colonne.libelle(valeur) or str(valeur)
    return str(valeur)


def raison_de_l_erreur(bouteille: FicheBouteille) -> str:
    """Pourquoi l'extraction a échoué, en français pour l'expert — jamais le
    message technique brut (CLAUDE.md)."""
    toutes = extractions_de(bouteille)
    motif = (toutes[-1].erreur or "") if toutes else ""
    if motif.startswith("panne systématique"):
        return ("L'analyse s'est arrêtée sur une panne du service d'analyse (clé, modèle ou crédit). "
                "Elle reprendra quand l'analyse sera relancée depuis l'écran de suivi.")
    if motif.startswith("réponse inexploitable"):
        return "Le modèle a répondu, mais sa réponse n'a pas pu être lue."
    if "bloquée" in motif or motif.startswith("refus du modèle"):
        return "Le service d'analyse a refusé de traiter ces photos."
    if motif.startswith(("génération interrompue", "réponse vide", "aucun appel d'outil")):
        return "Le modèle n'a pas rendu de réponse exploitable."
    return "Le service d'analyse n'a pas répondu à temps (panne passagère)."


def _photos_de(session: Session, bouteille_id: int | None) -> list[int]:
    if bouteille_id is None:
        return []
    return [photo.id for photo in session.get(FicheBouteille, bouteille_id).photos]


def _fusionnees_a_l_export(
    session: Session, courantes: Bouteille, liees: list[FicheBouteille], config: ConfigMaison
) -> list[str]:
    """Les bouteilles nées de la même séparation que l'export fusionnera avec
    celle-ci : identiques sur les colonnes de regroupement de la maison
    (decisions.md 0140). L'écran prévient ; la config décide."""
    return [
        autre.identifiant
        for autre in liees
        if len(regrouper([courantes, valeurs_courantes(session, autre.id)], config)) == 1
    ]


def _historique(session: Session, bouteille: FicheBouteille, config: ConfigMaison) -> list[LigneHistorique]:
    """Analyses, corrections et actions de l'expert, dans l'ordre, en clair."""
    lignes = []
    for extraction in extractions_de(bouteille):
        resultat = "en erreur" if extraction.erreur else "réussie"
        lignes.append(LigneHistorique(extraction.cree_le, f"modèle {extraction.modele}", f"analyse {resultat}"))
    for correction in corrections_de(bouteille):
        if correction.champ == CHAMP_STATUT:
            texte = {"validee": "validée", "extraite": "remise à relire", "a_extraire": "remise à analyser"}.get(
                correction.nouvelle_valeur, f"statut « {correction.nouvelle_valeur} »"
            )
        else:
            colonne = config.colonne(correction.champ)
            nom = colonne.nom if colonne else correction.champ
            texte = (f"{nom} : {en_clair(colonne, correction.ancienne_valeur)} → "
                     f"{en_clair(colonne, correction.nouvelle_valeur)}")
        lignes.append(LigneHistorique(correction.cree_le, correction.auteur, texte))
    for evenement in evenements_de(session, bouteille.id):
        texte = LIBELLES_EVENEMENT.get(evenement.type, evenement.type)
        detail = evenement.detail or {}
        if evenement.type == "separation" and "nouvelle" in detail:
            texte = f"{accord(detail['quantite'], 'exemplaire séparé', 'exemplaires séparés')} vers {detail['nouvelle']}"
        elif evenement.type == "separation" and "source" in detail:
            texte = f"née de la séparation de {detail['source']} ({accord(detail['quantite'], 'exemplaire', 'exemplaires')})"
        elif evenement.type == "signalement_paire" and detail.get("motif"):
            texte = f"{texte} : {detail['motif']}"
        lignes.append(LigneHistorique(evenement.cree_le, evenement.auteur, texte))
    return sorted(lignes, key=lambda ligne: ligne.le)


@dataclass(frozen=True)
class Recapitulatif:
    """Fin de relecture : ce qui est fait, ce qui reste, ce qu'on a mesuré."""

    inventaire: Inventaire
    stats: StatsInventaire
    compteurs: Compteurs
    restantes: list[EtatRelecture]  # à relire : extraites, non validées, non signalées
    en_erreur: list[EtatRelecture]
    signalees: list[EtatRelecture]
    pas_encore_extraites: list[EtatRelecture]
    champs_corriges: list[tuple[str, int]]  # (nom de la colonne, nombre), les plus corrigés d'abord
    excel_attend: str  # vide si chaque bouteille a sa ligne ; sinon, ce qui manque (0170)

    @property
    def termine(self) -> bool:
        return self.compteurs.total > 0 and self.compteurs.validees == self.compteurs.total


def recapitulatif(session: Session, inventaire_id: int) -> Recapitulatif:
    etat = bilan(session, inventaire_id)
    inventaire = charger_inventaire(session, inventaire_id)
    config = config_figee(inventaire)
    etats = etats_de_relecture(session, inventaire_id)
    stats = stats_inventaire(session, inventaire_id)
    return Recapitulatif(
        inventaire=inventaire,
        stats=stats,
        compteurs=compter(etats),
        restantes=[e for e in etats if e.statut == "extraite" and not e.paire_signalee],
        en_erreur=[e for e in etats if e.statut == "erreur"],
        signalees=[e for e in etats if e.paire_signalee],
        pas_encore_extraites=[e for e in etats if e.statut in ("a_extraire", "en_cours")],
        champs_corriges=[
            (config.colonne(champ).nom if config.colonne(champ) else champ, nombre)
            for champ, nombre in stats.champs_les_plus_corriges
        ],
        excel_attend=(
            "aucune bouteille" if not etat.total else "" if etat.chaque_bouteille_a_sa_ligne else etat.ce_qui_manque()
        ),
    )
