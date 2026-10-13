"""Le cycle de vie d'un inventaire (session 6 ; decisions.md 0168).

On commence un inventaire, on l'arrête, on le reprend, on le modifie — on ajoute
des bouteilles (dépôt), on en retire — et on le CLÔT quand on est sûr. Rien ne
se supprime vraiment :

- une bouteille retirée sort de la relecture, de l'export et des comptes, mais
  garde ses photos, sa lecture et son historique ; elle peut être remise ;
- un inventaire supprimé va à la corbeille : plus aucun écran ne l'ouvre, le
  worker ne le traite plus, il se restaure ;
- clos, il est en lecture seule (l'export reste possible) ; rouvrir est permis.

Chaque geste est tracé (`evenement_inventaire`, `evenement_bouteille`), avec
son auteur. Valider bouteille par bouteille reste FACULTATIF : on clôt avec ce
qui n'est pas validé, mais jamais tant qu'une bouteille n'a pas sa ligne dans
l'Excel (pas encore analysée, ou ajoutée et pas lancée).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.donnees.modeles import EvenementBouteille, EvenementInventaire, FicheBouteille, maintenant
from src.services.depot import groupes_en_attente
from src.services.extraction import charger_bouteille
from src.services.inventaires import actualiser_statut, charger_inventaire, verifier_modifiable
from src.services.relecture import auteur_valide


class CycleRefuse(ValueError):
    """Le geste n'est pas possible dans l'état actuel : le message dit pourquoi."""


def _tracer(session: Session, inventaire_id: int, type_: str, auteur: str, detail: Any = None) -> None:
    session.add(EvenementInventaire(inventaire_id=inventaire_id, type=type_, auteur=auteur, detail=detail))


def evenements_d_inventaire(session: Session, inventaire_id: int) -> list[EvenementInventaire]:
    return list(
        session.scalars(
            select(EvenementInventaire)
            .where(EvenementInventaire.inventaire_id == inventaire_id)
            .order_by(EvenementInventaire.id)
        )
    )


# --- ce qui reste à faire : le bilan ---------------------------------------------------------


@dataclass(frozen=True)
class Bilan:
    """Où en est un inventaire, du point de vue de l'Excel et de la clôture."""

    total: int  # bouteilles de l'inventaire (retirées exclues)
    validees: int
    non_validees: int  # analysées, pas validées : facultatif
    en_erreur: int  # leur ligne existe, signalée « erreur d'analyse »
    pas_analysees: list[int]  # positions : à extraire ou en cours
    en_attente: int  # bouteilles ajoutées (groupes de photos) pas encore lancées
    retirees: int

    @property
    def chaque_bouteille_a_sa_ligne(self) -> bool:
        return not self.pas_analysees and not self.en_attente

    def ce_qui_manque(self) -> str:
        """Pourquoi l'Excel (ou la clôture) attend, en clair."""
        raisons = []
        if self.pas_analysees:
            raisons.append(f"{len(self.pas_analysees)} bouteille(s) encore en cours d'analyse")
        if self.en_attente:
            raisons.append(
                f"{self.en_attente} bouteille(s) ajoutée(s) pas encore lancée(s) : lancez leur analyse ou retirez-les"
            )
        return " ; ".join(raisons)

    def ce_qui_n_est_pas_valide(self) -> str:
        """L'avertissement de la clôture : ce qui part sans avoir été validé."""
        morceaux = []
        if self.non_validees:
            morceaux.append(f"{self.non_validees} bouteille(s) non validée(s)")
        if self.en_erreur:
            morceaux.append(f"{self.en_erreur} en erreur d'analyse")
        return ", ".join(morceaux)


def bilan(session: Session, inventaire_id: int) -> Bilan:
    inventaire = charger_inventaire(session, inventaire_id)
    session.refresh(inventaire)
    bouteilles = list(inventaire.bouteilles)
    statuts = Counter(b.statut for b in bouteilles)
    return Bilan(
        total=len(bouteilles),
        validees=statuts["validee"],
        non_validees=statuts["extraite"],
        en_erreur=statuts["erreur"],
        pas_analysees=[b.position for b in bouteilles if b.statut in ("a_extraire", "en_cours")],
        en_attente=len(groupes_en_attente(session, inventaire_id)),
        retirees=sum(1 for b in inventaire.toutes_les_bouteilles if b.retiree),
    )


# --- l'inventaire --------------------------------------------------------------------------


def renommer(session: Session, inventaire_id: int, nom: str, auteur: str) -> None:
    auteur = auteur_valide(auteur)
    inventaire = charger_inventaire(session, inventaire_id)
    verifier_modifiable(inventaire)
    nom = (nom or "").strip()
    if not nom:
        raise CycleRefuse("Donnez un nom à la vente : il ne peut pas rester vide.")
    if len(nom) > 200:
        raise CycleRefuse("Nom trop long : 200 caractères au plus.")
    if nom == inventaire.nom:
        return
    _tracer(session, inventaire_id, "renommage", auteur, {"avant": inventaire.nom, "apres": nom})
    inventaire.nom = nom
    session.commit()


def archiver(session: Session, inventaire_id: int, auteur: str) -> bool:
    """Rangé hors de la liste principale (une vente terminée), toujours ouvrable.
    Renvoie False s'il l'était déjà."""
    auteur = auteur_valide(auteur)
    inventaire = charger_inventaire(session, inventaire_id)
    if inventaire.archive_le is not None:
        return False
    inventaire.archive_le = maintenant()
    _tracer(session, inventaire_id, "archivage", auteur)
    session.commit()
    return True


def desarchiver(session: Session, inventaire_id: int, auteur: str) -> bool:
    auteur = auteur_valide(auteur)
    inventaire = charger_inventaire(session, inventaire_id)
    if inventaire.archive_le is None:
        return False
    inventaire.archive_le = None
    _tracer(session, inventaire_id, "desarchivage", auteur)
    session.commit()
    return True


def supprimer(session: Session, inventaire_id: int, auteur: str) -> None:
    """À la corbeille : plus aucun écran ne l'ouvre et son analyse s'arrête (les
    bouteilles commencées se terminent). Rien n'est effacé : photos, lectures du
    modèle, corrections restent, et il se restaure. L'écran demande confirmation."""
    auteur = auteur_valide(auteur)
    inventaire = charger_inventaire(session, inventaire_id)
    detail = {"extraction": inventaire.extraction}
    # Une analyse finie n'a rien à arrêter : la mettre « en pause » la rendait
    # impossible à reprendre une fois restaurée (T4-D1).
    reste = any(b.statut in ("a_extraire", "en_cours") for b in inventaire.bouteilles)
    if inventaire.extraction == "lancee" and reste:
        inventaire.extraction = "annulee"
    inventaire.supprime_le = maintenant()
    _tracer(session, inventaire_id, "suppression", auteur, detail)
    session.commit()


def restaurer(session: Session, inventaire_id: int, auteur: str) -> None:
    """Sort de la corbeille, tel qu'il y était entré. Une analyse arrêtée par la
    suppression ne repart pas toute seule : « Reprendre l'analyse » au suivi."""
    auteur = auteur_valide(auteur)
    inventaire = charger_inventaire(session, inventaire_id, corbeille=True)
    if inventaire.supprime_le is None:
        raise CycleRefuse(f"L'inventaire « {inventaire.nom} » n'est pas dans la corbeille.")
    inventaire.supprime_le = None
    # Restauré « tel qu'il y était entré » : une analyse finie redevient lancée
    # (les inventaires mis en pause à tort avant T4-D1 aussi).
    if inventaire.extraction == "annulee" and not any(
        b.statut in ("a_extraire", "en_cours") for b in inventaire.bouteilles
    ):
        inventaire.extraction = "lancee"
    _tracer(session, inventaire_id, "restauration", auteur)
    session.commit()


def clore(session: Session, inventaire_id: int, auteur: str) -> Bilan:
    """Clôt l'inventaire : lecture seule ensuite (l'export reste possible).

    Permis avec des bouteilles non validées — valider reste facultatif ; ce qui
    ne l'est pas est noté dans la trace de clôture. Refusé tant qu'une
    bouteille n'a pas sa ligne dans l'Excel.
    """
    auteur = auteur_valide(auteur)
    inventaire = charger_inventaire(session, inventaire_id)
    if inventaire.clos_le is not None:
        raise CycleRefuse(f"L'inventaire « {inventaire.nom} » est déjà clos.")
    if inventaire.statut == "brouillon":
        raise CycleRefuse("Cet inventaire est encore en brouillon : lancez d'abord l'analyse de ses bouteilles.")
    etat = bilan(session, inventaire_id)
    if not etat.chaque_bouteille_a_sa_ligne:
        raise CycleRefuse(f"L'inventaire ne peut pas encore être clos : {etat.ce_qui_manque()}.")
    inventaire.clos_le = maintenant()
    _tracer(session, inventaire_id, "cloture", auteur, {
        "bouteilles": etat.total, "validees": etat.validees,
        "non_validees": etat.non_validees, "en_erreur": etat.en_erreur,
    })
    session.commit()
    return etat


def rouvrir(session: Session, inventaire_id: int, auteur: str) -> None:
    """Une erreur découverte après coup : l'inventaire redevient modifiable,
    et c'est tracé. L'écran demande confirmation."""
    auteur = auteur_valide(auteur)
    inventaire = charger_inventaire(session, inventaire_id)
    if inventaire.clos_le is None:
        raise CycleRefuse(f"L'inventaire « {inventaire.nom} » n'est pas clos.")
    _tracer(session, inventaire_id, "reouverture", auteur, {"clos_le": inventaire.clos_le.isoformat()})
    inventaire.clos_le = None
    session.commit()


# --- une bouteille ---------------------------------------------------------------------------


def retirer_bouteille(session: Session, bouteille_id: int, auteur: str, motif: str = "") -> FicheBouteille:
    """Retire une bouteille de l'inventaire (photographiée par erreur, pas dans la
    vente…) : plus de relecture, d'export ni de compte. Rien n'est effacé ;
    elle se remet depuis le récapitulatif."""
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    inventaire = charger_inventaire(session, bouteille.inventaire_id)
    verifier_modifiable(inventaire)
    if bouteille.retiree:
        raise CycleRefuse(f"La bouteille n°{bouteille.position} est déjà retirée.")
    if bouteille.statut == "en_cours":
        raise CycleRefuse(
            f"La bouteille n°{bouteille.position} est en cours d'analyse : attendez la fin pour la retirer."
        )
    bouteille.retiree = True
    motif = (motif or "").strip()
    bouteille.evenements.append(EvenementBouteille(type="retrait", auteur=auteur, detail={"motif": motif} if motif else None))
    session.flush()
    session.expire(inventaire, ["bouteilles"])
    actualiser_statut(inventaire)
    session.commit()
    return bouteille


def remettre_bouteille(session: Session, bouteille_id: int, auteur: str) -> FicheBouteille:
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    inventaire = charger_inventaire(session, bouteille.inventaire_id)
    verifier_modifiable(inventaire)
    if not bouteille.retiree:
        raise CycleRefuse(f"La bouteille n°{bouteille.position} n'est pas retirée.")
    bouteille.retiree = False
    bouteille.evenements.append(EvenementBouteille(type="remise", auteur=auteur))
    session.flush()
    session.expire(inventaire, ["bouteilles"])
    actualiser_statut(inventaire)
    session.commit()
    return bouteille


def bouteilles_retirees(session: Session, inventaire_id: int) -> list[FicheBouteille]:
    charger_inventaire(session, inventaire_id)
    return list(
        session.scalars(
            select(FicheBouteille)
            .where(FicheBouteille.inventaire_id == inventaire_id, FicheBouteille.retiree.is_(True))
            .order_by(FicheBouteille.position)
        )
    )
