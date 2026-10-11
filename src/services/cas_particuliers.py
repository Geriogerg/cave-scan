"""Les cas particuliers de la relecture (guide de session 5, §5).

Réanalyser, signaler un problème de photos, séparer une bouteille. (« Inverser
les photos » a disparu avec les rôles étiquette / contre-étiquette : les photos
d'une bouteille sont numérotées, sans rôle — decisions.md 0164, 0166.) Chaque action est tracée dans l'historique des événements de la
bouteille (decisions.md 0139) ; aucune ne modifie une extraction ni ne
supprime une correction. Le modèle n'est jamais appelé ici : réanalyser remet
la bouteille dans la file d'attente, et c'est le worker qui l'extrait.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.maison import COLONNE_QUANTITE
from src.donnees.modeles import Correction, EvenementBouteille, FicheBouteille
from src.services.extraction import charger_bouteille
from src.services.inventaires import actualiser_statut, config_figee, verifier_modifiable
from src.services.relecture import (
    auteur_valide,
    champs_corrigeables,
    quantite_valide,
    remettre_a_relire,
    valeur_courante,
    valeurs_courantes,
    valeurs_modele,
)


class ActionRefusee(ValueError):
    """L'action n'est pas possible dans l'état actuel : le message dit pourquoi."""


def evenements_de(session: Session, bouteille_id: int) -> list[EvenementBouteille]:
    """Les actions de l'expert sur la bouteille, dans l'ordre."""
    return list(
        session.scalars(
            select(EvenementBouteille)
            .where(EvenementBouteille.bouteille_id == bouteille_id)
            .order_by(EvenementBouteille.id)
        )
    )


def _tracer(bouteille: FicheBouteille, type_: str, auteur: str, detail: Any = None) -> None:
    bouteille.evenements.append(EvenementBouteille(type=type_, auteur=auteur, detail=detail))


def _nom(bouteille: FicheBouteille) -> str:
    return f"Bouteille n°{bouteille.position} ({bouteille.identifiant})"


# --- réanalyser ------------------------------------------------------------------------------


def reanalyser(session: Session, bouteille_id: int, auteur: str) -> bool:
    """Remet UNE bouteille dans la file d'attente : le worker l'extrait de nouveau.

    L'extraction précédente reste en base (immuable) ; la nouvelle fera foi, et
    les corrections déjà faites restent prioritaires sur elle (decisions.md
    0072). Une bouteille validée est remise à relire. Renvoie False si elle
    était déjà en attente ou en cours d'extraction.
    """
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    verifier_modifiable(bouteille.inventaire)
    if bouteille.statut in ("a_extraire", "en_cours"):
        return False
    inventaire = bouteille.inventaire
    if inventaire.extraction != "lancee":
        etat = {"annulee": "a été annulée", "arretee": "s'est arrêtée"}.get(inventaire.extraction, "n'est pas lancée")
        raise ActionRefusee(
            f"L'analyse de cet inventaire {etat} : relancez-la depuis l'écran de suivi, "
            f"puis réanalysez la bouteille."
        )
    statut_precedent = bouteille.statut
    remettre_a_relire(bouteille, auteur, statut="a_extraire")
    bouteille.statut = "a_extraire"
    _tracer(bouteille, "reanalyse", auteur, {"statut_precedent": statut_precedent})
    actualiser_statut(inventaire)
    session.commit()
    return True


# --- signaler un problème de photos ----------------------------------------------------------


def signaler_paire(session: Session, bouteille_id: int, auteur: str, motif: str = "") -> bool:
    """Les photos ne montrent pas toutes cette bouteille (photo d'une autre
    bouteille dans le groupe) : la bouteille est marquée et ne peut plus être
    validée (decisions.md 0145). Noms internes d'origine (« paire ») gardés :
    l'historique les porte. Renvoie False si elle était déjà signalée."""
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    verifier_modifiable(bouteille.inventaire)
    if bouteille.paire_signalee:
        return False
    bouteille.paire_signalee = True
    remettre_a_relire(bouteille, auteur)
    motif = (motif or "").strip()
    _tracer(bouteille, "signalement_paire", auteur, {"motif": motif} if motif else None)
    actualiser_statut(bouteille.inventaire)
    session.commit()
    return True


def lever_signalement(session: Session, bouteille_id: int, auteur: str) -> bool:
    """Le signalement était une erreur : la bouteille peut de nouveau être validée.
    Renvoie False si elle n'était pas signalée."""
    auteur = auteur_valide(auteur)
    bouteille = charger_bouteille(session, bouteille_id)
    verifier_modifiable(bouteille.inventaire)
    if not bouteille.paire_signalee:
        return False
    bouteille.paire_signalee = False
    _tracer(bouteille, "signalement_leve", auteur)
    session.commit()
    return True


# --- séparer ---------------------------------------------------------------------------------

MOTIF_IDENTIFIANT = re.compile(r"^(B-[0-9A-F]+)(?:-\d+)?$")


def separer(session: Session, bouteille_id: int, quantite: Any, auteur: str) -> FicheBouteille:
    """Bouteilles identiques d'état différent (5 bonnes + 1 abîmée) : crée une
    seconde bouteille, avec les MÊMES photos, juste après la première, qui
    reçoit `quantite` exemplaires — la somme des quantités est conservée.

    La nouvelle bouteille lit la réponse du modèle de sa source (aucun nouvel
    appel) et reprend les corrections déjà faites : elle part des mêmes valeurs,
    que l'expert ajuste ensuite (état, description). Renvoie la nouvelle
    bouteille (decisions.md 0144).
    """
    auteur = auteur_valide(auteur)
    source = charger_bouteille(session, bouteille_id)
    verifier_modifiable(source.inventaire)
    if source.statut not in ("extraite", "validee"):
        raise ActionRefusee(
            f"{_nom(source)} : seule une bouteille déjà analysée peut être séparée."
        )
    nombre = quantite_valide(quantite)
    if nombre >= source.quantite:
        raise ActionRefusee(
            f"{_nom(source)} compte {source.quantite} exemplaire(s) : on peut en séparer "
            f"{source.quantite - 1} au plus. Indiquez d'abord la quantité totale, puis séparez."
        )
    inventaire = source.inventaire
    config = config_figee(inventaire)

    # La place juste après la source : les suivantes reculent d'un rang, en deux
    # temps (la contrainte d'unicité refuserait un décalage direct).
    # Toutes, retirées comprises : elles gardent leur place (decisions.md 0168).
    suivantes = [b for b in inventaire.toutes_les_bouteilles if b.position > source.position]
    for bouteille in suivantes:
        bouteille.position = -(bouteille.position + 1)
    session.flush()
    for bouteille in suivantes:
        bouteille.position = -bouteille.position
    session.flush()

    nouvelle = FicheBouteille(
        inventaire=inventaire,
        identifiant=_identifiant_libre(session, inventaire.id, source.identifiant),
        groupe_id=source.groupe_id,  # les mêmes photos
        position=source.position + 1,
        quantite=nombre,
        statut="extraite",
        separee_de_id=source.id,
    )
    session.add(nouvelle)
    session.flush()

    # Mêmes valeurs que la source : ses corrections sont reprises, champ par champ.
    courantes_source = valeurs_courantes(session, source.id)
    lues = valeurs_modele(session, nouvelle.id)
    pour_la_nouvelle = []
    for champ in champs_corrigeables(config):
        if champ == COLONNE_QUANTITE:
            continue
        reprise, lue = valeur_courante(courantes_source, champ), valeur_courante(lues, champ)
        if reprise != lue:
            pour_la_nouvelle.append(Correction(champ=champ, ancienne_valeur=lue, nouvelle_valeur=reprise, auteur=auteur))
    pour_la_nouvelle.append(Correction(champ=COLONNE_QUANTITE, ancienne_valeur=None, nouvelle_valeur=nombre, auteur=auteur))
    nouvelle.corrections.extend(pour_la_nouvelle)

    # La source garde le reste ; validée, elle redevient à relire (0169).
    pour_la_source = Correction(
        champ=COLONNE_QUANTITE, ancienne_valeur=source.quantite, nouvelle_valeur=source.quantite - nombre, auteur=auteur
    )
    source.corrections.append(pour_la_source)
    source.quantite -= nombre
    remettre_a_relire(source, auteur)
    session.flush()

    # Les corrections écrites par la séparation sont nommées dans son événement :
    # les statistiques ne les comptent pas comme des corrections de l'expert.
    _tracer(nouvelle, "separation", auteur, {
        "source": source.identifiant, "quantite": nombre, "corrections": [c.id for c in pour_la_nouvelle],
    })
    _tracer(source, "separation", auteur, {
        "nouvelle": nouvelle.identifiant, "quantite": nombre, "corrections": [pour_la_source.id],
    })
    session.expire(inventaire, ["bouteilles"])  # ordre des positions relu
    actualiser_statut(inventaire)
    session.commit()
    return nouvelle


def _identifiant_libre(session: Session, inventaire_id: int, identifiant_source: str) -> str:
    """« B-XXXXXXXXXX-2 », « -3 »… à partir de l'identifiant d'origine : stable,
    lisible, unique dans l'inventaire (decisions.md 0065)."""
    trouve = MOTIF_IDENTIFIANT.match(identifiant_source)
    racine = trouve.group(1) if trouve else identifiant_source
    pris = set(
        session.scalars(select(FicheBouteille.identifiant).where(FicheBouteille.inventaire_id == inventaire_id))
    )
    rang = 2
    while f"{racine}-{rang}" in pris:
        rang += 1
    return f"{racine}-{rang}"


def bouteilles_liees(session: Session, bouteille: FicheBouteille) -> list[FicheBouteille]:
    """Les bouteilles nées de la même séparation que celle-ci (sa source, ses
    séparées, et leurs sœurs), elle exceptée, dans l'ordre de l'inventaire."""
    racine = bouteille
    vues = {racine.id}
    while racine.separee_de_id is not None and racine.separee_de_id not in vues:
        racine = session.get(FicheBouteille, racine.separee_de_id)
        vues.add(racine.id)
    famille = {racine.id: racine}
    a_explorer = [racine.id]
    while a_explorer:
        enfants = session.scalars(select(FicheBouteille).where(FicheBouteille.separee_de_id.in_(a_explorer))).all()
        a_explorer = [enfant.id for enfant in enfants if enfant.id not in famille]
        famille.update({enfant.id: enfant for enfant in enfants})
    return sorted((b for b in famille.values() if b.id != bouteille.id), key=lambda b: b.position)
