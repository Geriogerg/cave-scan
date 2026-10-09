"""Ce qu'on tire d'un inventaire : l'export, les statistiques, le score du modèle.

Tout se lit depuis la base, avec la config FIGÉE de l'inventaire (decisions.md
0073) : modifier le JSON après coup ne change rien à ce qui sort ici.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.compare.compare_listings import RapportComparaison, comparer
from src.donnees.modeles import STATUTS_BOUTEILLE, Correction, Extraction, FicheBouteille
from src.export.excel_writer import ecrire_excel
from src.io.manual_listing import colonnes_toujours_vides, load_manual
from src.services.inventaires import charger_inventaire, config_figee
from src.services.relecture import CHAMP_STATUT, valeurs_courantes, valeurs_modele


def exporter(session: Session, inventaire_id: int, chemin: str | Path) -> Path:
    """L'Excel de l'inventaire : valeurs courantes (modèle + corrections), config
    figée, regroupement et surlignage exactement comme en session 1."""
    inventaire = charger_inventaire(session, inventaire_id)
    bouteilles = [valeurs_courantes(session, bouteille.id) for bouteille in inventaire.bouteilles]
    return ecrire_excel(bouteilles, config_figee(inventaire), chemin)


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
    auto = [valeurs_modele(session, bouteille.id) for bouteille in inventaire.bouteilles]
    manuel = load_manual(chemin_manuel, config)
    systematiques = [colonne.cle for colonne in config.colonnes_best_effort]
    return ResultatComparaison(
        rapport=comparer(auto, manuel, systematiques=systematiques),
        colonnes_toujours_vides=colonnes_toujours_vides(manuel),
    )


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



def stats_inventaire(session: Session, inventaire_id: int) -> StatsInventaire:
    """Bouteilles par statut, coût total en tokens, champs les plus corrigés."""
    inventaire = charger_inventaire(session, inventaire_id)
    ids = [bouteille.id for bouteille in inventaire.bouteilles]

    extractions = list(session.scalars(select(Extraction).where(Extraction.bouteille_id.in_(ids))))
    mesurees = [e for e in extractions if e.tokens_entree is not None or e.tokens_sortie is not None]
    corrections = [
        c
        for c in session.scalars(select(Correction).where(Correction.bouteille_id.in_(ids)))
        if c.champ != CHAMP_STATUT
    ]
    par_statut = Counter(bouteille.statut for bouteille in inventaire.bouteilles)

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
        champs_les_plus_corriges=Counter(c.champ for c in corrections).most_common(),
        bouteilles_mesurees=len({e.bouteille_id for e in mesurees}),
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
