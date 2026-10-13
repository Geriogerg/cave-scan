"""Ce qu'on tire d'un inventaire : l'export, les statistiques, le score du modèle.

Tout se lit depuis la base, avec la config FIGÉE de l'inventaire (decisions.md
0073) : modifier le JSON après coup ne change rien à ce qui sort ici.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.compare.compare_listings import (
    RapportComparaison,
    SignauxModele,
    comparer,
    relever_signaux,
)
from src.donnees.modeles import STATUTS_BOUTEILLE, Correction, EvenementBouteille, Extraction, FicheBouteille
from src.export.excel_writer import EtatLigne, ecrire_excel
from src.io.manual_listing import colonnes_toujours_vides, load_manual
from src.services.cycle_de_vie import bilan
from src.services.inventaires import charger_inventaire, config_figee
from src.services.relecture import (
    CHAMP_STATUT,
    extraction_qui_fait_foi,
    valeur_courante,
    valeurs_courantes,
    valeurs_modele,
)


class ExportRefuse(ValueError):
    """Une bouteille n'aurait pas sa ligne dans l'Excel : le message dit laquelle."""


def exporter(session: Session, inventaire_id: int, chemin: str | Path) -> Path:
    """L'Excel de l'inventaire : valeurs courantes (modèle + corrections), config
    figée, regroupement et surlignage comme en session 1.

    Une ligne par bouteille, toujours (decisions.md 0170) : refusé tant qu'une
    bouteille n'est pas encore analysée ou qu'une bouteille ajoutée n'est pas
    lancée ; une bouteille en erreur a sa ligne, signalée « Erreur d'analyse »
    (ou « Saisie manuelle » une fois validée à la main). Les bouteilles retirées
    n'en font plus partie. Valider bouteille par bouteille reste facultatif.
    """
    inventaire = charger_inventaire(session, inventaire_id)
    etat = bilan(session, inventaire_id)
    if not etat.total:  # rapport du testeur, T1-S9
        raise ExportRefuse("L'inventaire n'a encore aucune bouteille : il n'y a rien à mettre dans l'Excel.")
    if not etat.chaque_bouteille_a_sa_ligne:
        raise ExportRefuse(
            f"L'Excel n'est pas encore disponible : chaque bouteille doit y avoir sa ligne. Il reste "
            f"{etat.ce_qui_manque()}."
        )
    bouteilles = [valeurs_courantes(session, bouteille.id) for bouteille in inventaire.bouteilles]
    etats = {}
    for fiche in inventaire.bouteilles:
        sans_lecture = extraction_qui_fait_foi(fiche) is None
        etats[fiche.identifiant] = EtatLigne(
            erreur=fiche.statut == "erreur",
            saisie_manuelle=fiche.statut == "validee" and sans_lecture,
            relue=fiche.statut == "validee",
        )
    return ecrire_excel(bouteilles, config_figee(inventaire), chemin, etats)


@dataclass(frozen=True)
class ResultatComparaison:
    rapport: RapportComparaison
    colonnes_toujours_vides: list[str] = field(default_factory=list)


def comparer_au_listing(
    session: Session, inventaire_id: int, chemin_manuel: str | Path
) -> ResultatComparaison:
    """Le score du MODÈLE face au listing de l'expert : sa sortie brute, sans les
    corrections — sinon chaque correction gonflerait son score (decisions.md
    0081). Les corrections, elles, se mesurent dans `stats_inventaire`."""
    inventaire = charger_inventaire(session, inventaire_id)
    config = config_figee(inventaire)
    auto = [valeurs_modele(session, bouteille.id) for bouteille in _photographiees(inventaire)]
    manuel = load_manual(chemin_manuel, config)
    systematiques = [colonne.cle for colonne in config.colonnes_best_effort]
    rapport = comparer(auto, manuel, systematiques=systematiques)
    return ResultatComparaison(
        rapport=replace(rapport, consignes_modifiees=bool(config.consignes)),
        colonnes_toujours_vides=colonnes_toujours_vides(manuel),
    )


def signaux_du_modele(session: Session, inventaire_id: int) -> SignauxModele:
    """Ce que le modèle dit de son propre travail, sans référence à l'expert —
    lisible avant que son listing existe."""
    inventaire = charger_inventaire(session, inventaire_id)
    config = config_figee(inventaire)
    auto = [valeurs_modele(session, bouteille.id) for bouteille in _photographiees(inventaire)]
    return relever_signaux(auto, [colonne.cle for colonne in config.colonnes_best_effort])


def _champs_vraiment_corriges(session: Session, corrections: list[Correction]) -> list[tuple[str, int]]:
    """Par champ, le nombre de bouteilles dont la valeur DIFFÈRE de la lecture du
    modèle : une correction suivie d'un « Revenir à la valeur du modèle » n'en est
    plus une (T2-D12). Les colonnes de l'expert comptent dès qu'elles sont saisies."""
    par_bouteille: dict[int, set[str]] = {}
    for correction in corrections:
        par_bouteille.setdefault(correction.bouteille_id, set()).add(correction.champ)
    compte: Counter[str] = Counter()
    for bouteille_id, champs in par_bouteille.items():
        courantes, modele = valeurs_courantes(session, bouteille_id), valeurs_modele(session, bouteille_id)
        for champ in champs:
            if valeur_courante(courantes, champ) != valeur_courante(modele, champ):
                compte[champ] += 1
    return compte.most_common()


def _photographiees(inventaire) -> list[FicheBouteille]:
    """Les bouteilles telles que le modèle les a lues : une par groupe de photos.
    Une bouteille née d'une séparation reprend la lecture de sa source ; la
    compter décalerait l'alignement ligne à ligne avec le listing de l'expert
    (decisions.md 0010, 0170). Les retirées n'en font déjà plus partie."""
    return [bouteille for bouteille in inventaire.bouteilles if bouteille.separee_de_id is None]


@dataclass(frozen=True)
class StatsInventaire:
    """Les chiffres d'un inventaire — dont le premier coût réel par bouteille."""

    inventaire_id: int
    nom: str
    statut: str
    nb_bouteilles: int
    par_statut: dict[str, int]
    nb_extractions: int  # relances et échecs compris : chaque appel compte
    nb_extractions_en_erreur: int
    tokens_entree: int
    tokens_sortie: int
    extractions_mesurees: int  # celles dont l'usage en tokens est connu
    bouteilles_mesurees: int  # bouteilles ayant consommé des tokens mesurés
    duree_totale_ms: int
    nb_corrections: int  # corrections de valeurs (changements de statut exclus)
    nb_bouteilles_corrigees: int
    champs_les_plus_corriges: list[tuple[str, int]]
    # Relecture (guide de session 5, §6) : de quoi mesurer le gain réel du pilote.
    corrections_par_bouteille: dict[str, int] = field(default_factory=dict)  # identifiant -> nombre
    temps_relecture_total_ms: int = 0  # absences longues exclues, mesuré par l'écran
    bouteilles_chronometrees: int = 0
    nb_reanalysees: int = 0
    nb_separees: int = 0  # bouteilles nées d'une séparation
    nb_signalees: int = 0  # bouteilles dont la paire a été signalée au moins une fois

    @property
    def tokens_par_bouteille(self) -> tuple[float, float] | None:
        """Tokens moyens (entrée, sortie) par bouteille ayant consommé des tokens
        mesurés — relances comprises, puisqu'elles sont facturées."""
        if not self.bouteilles_mesurees:
            return None
        return (
            self.tokens_entree / self.bouteilles_mesurees,
            self.tokens_sortie / self.bouteilles_mesurees,
        )

    @property
    def duree_par_extraction_ms(self) -> float | None:
        if not self.nb_extractions:
            return None
        return self.duree_totale_ms / self.nb_extractions

    @property
    def temps_relecture_moyen_ms(self) -> float | None:
        """Temps moyen de relecture par bouteille chronométrée."""
        if not self.bouteilles_chronometrees:
            return None
        return self.temps_relecture_total_ms / self.bouteilles_chronometrees


def stats_inventaire(session: Session, inventaire_id: int) -> StatsInventaire:
    """Bouteilles par statut, coût total en tokens, champs les plus corrigés,
    et la relecture : temps, corrections par bouteille, réanalyses, séparations,
    signalements."""
    inventaire = charger_inventaire(session, inventaire_id)
    ids = [bouteille.id for bouteille in inventaire.bouteilles]

    extractions = list(session.scalars(select(Extraction).where(Extraction.bouteille_id.in_(ids))))
    mesurees = [e for e in extractions if e.tokens_entree is not None or e.tokens_sortie is not None]
    evenements = list(session.scalars(select(EvenementBouteille).where(EvenementBouteille.bouteille_id.in_(ids))))
    # Les corrections écrites par une séparation (valeurs reprises, quantités
    # réparties) ne sont pas des corrections de l'expert : la séparation se
    # compte à part (decisions.md 0144).
    de_separation = {
        correction_id
        for evenement in evenements
        if evenement.type == "separation"
        for correction_id in (evenement.detail or {}).get("corrections", [])
    }
    corrections = [
        c
        for c in session.scalars(select(Correction).where(Correction.bouteille_id.in_(ids)))
        if c.champ != CHAMP_STATUT and c.id not in de_separation
    ]
    par_statut = Counter(bouteille.statut for bouteille in inventaire.bouteilles)
    identifiants = {bouteille.id: bouteille.identifiant for bouteille in inventaire.bouteilles}
    chronometrees = [b.temps_relecture_ms for b in inventaire.bouteilles if b.temps_relecture_ms]

    return StatsInventaire(
        inventaire_id=inventaire.id,
        nom=inventaire.nom,
        statut=inventaire.statut,
        nb_bouteilles=len(ids),
        par_statut={statut: par_statut.get(statut, 0) for statut in STATUTS_BOUTEILLE},
        nb_extractions=len(extractions),
        nb_extractions_en_erreur=sum(1 for e in extractions if e.erreur is not None),
        tokens_entree=sum(e.tokens_entree or 0 for e in mesurees),
        tokens_sortie=sum(e.tokens_sortie or 0 for e in mesurees),
        extractions_mesurees=len(mesurees),
        duree_totale_ms=sum(e.duree_ms for e in extractions),
        nb_corrections=len(corrections),
        nb_bouteilles_corrigees=len({c.bouteille_id for c in corrections}),
        champs_les_plus_corriges=_champs_vraiment_corriges(session, corrections),
        bouteilles_mesurees=len({e.bouteille_id for e in mesurees}),
        corrections_par_bouteille={
            identifiants[bouteille_id]: nombre
            for bouteille_id, nombre in Counter(c.bouteille_id for c in corrections).most_common()
        },
        temps_relecture_total_ms=sum(chronometrees),
        bouteilles_chronometrees=len(chronometrees),
        nb_reanalysees=len({e.bouteille_id for e in evenements if e.type == "reanalyse"}),
        nb_separees=sum(1 for b in inventaire.bouteilles if b.separee_de_id is not None),
        nb_signalees=len({e.bouteille_id for e in evenements if e.type == "signalement_paire"}),
    )


def lister_bouteilles(session: Session, inventaire_id: int) -> list[FicheBouteille]:
    return list(charger_inventaire(session, inventaire_id).bouteilles)


def bouteille_par_reference(session: Session, inventaire_id: int, reference: str) -> FicheBouteille:
    """Une bouteille désignée comme l'utilisateur la voit : son identifiant
    (« B-… », colonne N° de l'export) ou sa position dans l'inventaire."""
    reference = reference.strip()
    for bouteille in charger_inventaire(session, inventaire_id).bouteilles:
        if bouteille.identifiant.casefold() == reference.casefold() or (
            reference.isdigit() and bouteille.position == int(reference)
        ):
            return bouteille
    raise LookupError(
        f"Aucune bouteille « {reference} » dans l'inventaire n°{inventaire_id} "
        f"(identifiant B-… ou position)."
    )
