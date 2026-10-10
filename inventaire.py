#!/usr/bin/env python
"""Relecture d'un inventaire en ligne de commande.

    python inventaire.py lister
    python inventaire.py bouteilles 1
    python inventaire.py fiche 1 3                          (3 : position, ou identifiant B-…)
    python inventaire.py corriger 1 3 millesime 2016 --auteur "Nom"
    python inventaire.py valider 1 3 --auteur "Nom"
    python inventaire.py stats 1
    python inventaire.py exporter 1 [--sortie out/inventaire_1.xlsx]

Comme run_v0.py, aucune logique métier ici (decisions.md 0080) : chaque commande
appelle une fonction de service et affiche le résultat. Une correction est un
enregistrement de plus dans l'historique : la sortie du modèle n'est jamais
modifiée (0072).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.config import environnement
from src.donnees.base import session_de_base, url_de_base
from src.services.extraction import derniere_extraction_reussie, extractions_de
from src.services.inventaires import charger_inventaire, config_figee, lister_inventaires
from src.services.relecture import (
    CHAMP_STATUT,
    CorrectionRefusee,
    ValidationRefusee,
    champs_corrigeables,
    corrections_de,
    corriger,
    valeur_courante,
    valeurs_courantes,
    valeurs_modele,
    valider,
)
from src.services.restitution import (
    bouteille_par_reference,
    exporter,
    lister_bouteilles,
    stats_inventaire,
)

RACINE = Path(__file__).resolve().parent


def main(argv: Sequence[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):  # accents sur une console cp1252 (0039)
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")

    arguments = _analyseur().parse_args(argv)
    environnement.charger_env()  # la même base que run_v0.py, si `.env` la désigne
    try:
        with session_de_base(arguments.base) as session:
            arguments.commande(session, arguments)
    except (LookupError, CorrectionRefusee, ValidationRefusee) as erreur:
        # Inventaire ou bouteille introuvable, saisie refusée : rien n'a été écrit.
        print(erreur, file=sys.stderr)
        return 2
    except PermissionError as erreur:
        print(
            f"Impossible d'écrire {erreur.filename} : le fichier est-il ouvert dans Excel ? "
            f"Le fermer, puis relancer.",
            file=sys.stderr,
        )
        return 2
    return 0


# --- les commandes ---------------------------------------------------------------------------


def _lister(session: Session, arguments: argparse.Namespace) -> None:
    inventaires = lister_inventaires(session)
    print(f"Base : {url_de_base(arguments.base)}\n")
    if not inventaires:
        print("Aucun inventaire. En créer un : python run_v0.py --photos DOSSIER")
        return
    print(f"{'N°':>4}  {'statut':<7} {'btl':>4}  {'config':<7} {'créé le (UTC)':<16}  maison — nom")
    for inventaire in inventaires:
        print(
            f"{inventaire.id:>4}  {inventaire.statut:<7} {len(inventaire.bouteilles):>4}  "
            f"n°{inventaire.config_version.numero:<5} {inventaire.cree_le:%Y-%m-%d %H:%M}  "
            f"{inventaire.maison.nom} — {inventaire.nom}"
        )


def _bouteilles(session: Session, arguments: argparse.Namespace) -> None:
    inventaire = charger_inventaire(session, arguments.inventaire)
    print(
        f"Inventaire n°{inventaire.id} « {inventaire.nom} » — {inventaire.maison.nom}, "
        f"statut {inventaire.statut}\n"
    )
    print(f"{'pos':>4}  {'identifiant':<12}  {'statut':<10} {'qté':>3}  domaine · appellation · millésime")
    for bouteille in lister_bouteilles(session, inventaire.id):
        valeurs = valeurs_courantes(session, bouteille.id)
        resume = " · ".join(_affiche(v) for v in (valeurs.domaine, valeurs.appellation, valeurs.millesime))
        print(
            f"{bouteille.position:>4}  {bouteille.identifiant:<12}  {bouteille.statut:<10} "
            f"{valeurs.quantite:>3}  {resume}"
        )
    print(f"\nDétail, historique et extractions d'une bouteille : python inventaire.py fiche {inventaire.id} POSITION")


def _fiche(session: Session, arguments: argparse.Namespace) -> None:
    bouteille = bouteille_par_reference(session, arguments.inventaire, arguments.bouteille)
    config = config_figee(bouteille.inventaire)
    modele = valeurs_modele(session, bouteille.id)
    courantes = valeurs_courantes(session, bouteille.id)
    historique = corrections_de(bouteille)
    corriges = {correction.champ for correction in historique if correction.champ != CHAMP_STATUT}

    print(
        f"Bouteille n°{bouteille.position} — {bouteille.identifiant} — {bouteille.statut} — "
        f"inventaire n°{bouteille.inventaire.id} « {bouteille.inventaire.nom} »"
    )
    contre = bouteille.photo_contre.nom_origine if bouteille.photo_contre else "(pas de contre-étiquette)"
    print(f"Photos : {bouteille.photo_etiquette.nom_origine} + {contre}\n")

    print(f"  {'champ':<18} {'lu par le modèle':<34} valeur courante")
    for champ in champs_corrigeables(config):
        colonne = config.colonne(champ)
        saisie_expert = colonne is not None and colonne.source == "expert"
        lu = "(saisie de l'expert)" if saisie_expert else _affiche(valeur_courante(modele, champ))
        courante = _affiche(valeur_courante(courantes, champ))
        marque = "   ← corrigé" if champ in corriges else ""
        print(f"  {champ:<18} {lu:<34} {courante}{marque}")
    print(f"\n  À vérifier selon le modèle : {_affiche(modele.champs_a_verifier)}")

    print(f"\nHistorique ({len(historique)}) :")
    for correction in historique:
        print(
            f"  {correction.cree_le:%Y-%m-%d %H:%M} UTC  {correction.champ} : "
            f"« {_affiche(correction.ancienne_valeur)} » -> « {_affiche(correction.nouvelle_valeur)} »"
            f" — {correction.auteur}"
        )

    extractions = extractions_de(bouteille)
    foi = derniere_extraction_reussie(bouteille)
    print(f"\nExtractions ({len(extractions)}) — réponses brutes du modèle, jamais modifiées :")
    for extraction in extractions:
        tokens = (
            "tokens non mesurés"
            if extraction.tokens_entree is None and extraction.tokens_sortie is None
            else f"{extraction.tokens_entree or 0} + {extraction.tokens_sortie or 0} tokens"
        )
        issue = f"erreur : {extraction.erreur}" if extraction.erreur else "réussie"
        print(
            f"  {extraction.cree_le:%Y-%m-%d %H:%M} UTC  {extraction.modele}  prompt "
            f"{extraction.version_prompt}  {tokens}  {extraction.duree_ms / 1000:.1f} s  {issue}"
            f"{'   ← fait foi' if extraction is foi else ''}"
        )


def _corriger(session: Session, arguments: argparse.Namespace) -> None:
    bouteille = bouteille_par_reference(session, arguments.inventaire, arguments.bouteille)
    correction = corriger(session, bouteille.id, arguments.champ, arguments.valeur, arguments.auteur)
    print(
        f"Correction enregistrée — bouteille n°{bouteille.position} ({bouteille.identifiant}), "
        f"{correction.champ} : « {_affiche(correction.ancienne_valeur)} » -> "
        f"« {_affiche(correction.nouvelle_valeur)} », par {correction.auteur}."
    )
    print(
        f"La sortie du modèle est inchangée. Bouteille {bouteille.statut}, inventaire "
        f"{bouteille.inventaire.statut}.\nRéexporter : python inventaire.py exporter {arguments.inventaire}"
    )


def _valider(session: Session, arguments: argparse.Namespace) -> None:
    bouteille = bouteille_par_reference(session, arguments.inventaire, arguments.bouteille)
    valider(session, bouteille.id, arguments.auteur)
    stats = stats_inventaire(session, arguments.inventaire)
    print(
        f"Bouteille n°{bouteille.position} ({bouteille.identifiant}) validée. Inventaire "
        f"{stats.statut} : {stats.par_statut['validee']}/{stats.nb_bouteilles} bouteille(s) validée(s)."
    )


def _stats(session: Session, arguments: argparse.Namespace) -> None:
    stats = stats_inventaire(session, arguments.inventaire)
    print(f"Inventaire n°{stats.inventaire_id} « {stats.nom} » — statut {stats.statut}\n")
    repartition = ", ".join(f"{statut} {nombre}" for statut, nombre in stats.par_statut.items())
    print(f"Bouteilles   : {stats.nb_bouteilles} ({repartition})")
    print(
        f"Extractions  : {stats.nb_extractions} (relances comprises), dont "
        f"{stats.nb_extractions_en_erreur} en erreur"
    )
    if stats.tokens_par_bouteille is None:
        print("Tokens       : non mesurés (aucune extraction par un vrai modèle)")
    else:
        entree, sortie = stats.tokens_par_bouteille
        print(
            f"Tokens       : {stats.tokens_entree} en entrée, {stats.tokens_sortie} en sortie "
            f"({stats.extractions_mesurees} extraction(s) mesurée(s))"
        )
        print(
            f"Par bouteille: ~{entree:.0f} en entrée, ~{sortie:.0f} en sortie "
            f"(moyenne sur {stats.bouteilles_mesurees} bouteille(s), relances comprises)"
        )
    if stats.duree_par_extraction_ms is not None:
        print(
            f"Durée        : {stats.duree_totale_ms / 1000:.1f} s au total, "
            f"{stats.duree_par_extraction_ms / 1000:.1f} s par extraction"
        )
    champs = ", ".join(f"{champ} {nombre}" for champ, nombre in stats.champs_les_plus_corriges)
    print(
        f"Corrections  : {stats.nb_corrections} sur {stats.nb_bouteilles_corrigees} bouteille(s)"
        + (f" — {champs}" if champs else "")
    )
    # Relecture à l'écran (session 5) : de quoi mesurer le gain réel.
    if stats.temps_relecture_moyen_ms is None:
        print("Relecture    : temps pas encore mesuré (relecture à l'écran)")
    else:
        print(
            f"Relecture    : {stats.temps_relecture_total_ms / 1000:.0f} s au total, "
            f"{stats.temps_relecture_moyen_ms / 1000:.1f} s par bouteille "
            f"({stats.bouteilles_chronometrees} chronométrée(s), absences exclues)"
        )
    print(
        f"Cas particuliers : {stats.nb_reanalysees} réanalysée(s), {stats.nb_separees} née(s) d'une "
        f"séparation, {stats.nb_signalees} paire(s) signalée(s)"
    )


def _exporter(session: Session, arguments: argparse.Namespace) -> None:
    sortie = arguments.sortie or RACINE / "out" / f"inventaire_{arguments.inventaire}.xlsx"
    chemin = exporter(session, arguments.inventaire, sortie)
    print(f"Listing écrit : {chemin}")
    print("Valeurs courantes (modèle + corrections de l'expert), config figée de l'inventaire.")


# --- affichage et analyse de la ligne de commande ----------------------------------------------


def _affiche(valeur: Any) -> str:
    if isinstance(valeur, list):
        return ", ".join(str(element) for element in valeur) or "—"
    if valeur is None or valeur == "":
        return "—"
    return str(valeur)


def _analyseur() -> argparse.ArgumentParser:
    # `--base` est accepté avant comme après la commande.
    commun = argparse.ArgumentParser(add_help=False)
    commun.add_argument("--base", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    analyseur = argparse.ArgumentParser(
        description="Relire, corriger, valider et exporter un inventaire enregistré en base. "
        "Créer ou extraire un inventaire : run_v0.py."
    )
    analyseur.add_argument(
        "--base",
        type=Path,
        default=None,
        help="Base de données (défaut : variable CAVE_SCAN_DB, sinon data/cave_scan.db).",
    )
    commandes = analyseur.add_subparsers(title="commandes", required=True, metavar="COMMANDE")

    def commande(nom: str, fonction: Any, aide: str) -> argparse.ArgumentParser:
        sous = commandes.add_parser(nom, parents=[commun], help=aide, description=aide)
        sous.set_defaults(commande=fonction)
        return sous

    commande("lister", _lister, "Les inventaires de la base.")

    sous = commande("bouteilles", _bouteilles, "Les bouteilles d'un inventaire, valeurs courantes.")
    sous.add_argument("inventaire", type=int, metavar="ID")

    sous = commande("fiche", _fiche, "Une bouteille : modèle, valeurs courantes, historique, extractions.")
    sous.add_argument("inventaire", type=int, metavar="ID")
    sous.add_argument("bouteille", metavar="BOUTEILLE", help="Position (1, 2…) ou identifiant B-….")

    sous = commande("corriger", _corriger, "Corrige un champ (la sortie du modèle reste intacte).")
    sous.add_argument("inventaire", type=int, metavar="ID")
    sous.add_argument("bouteille", metavar="BOUTEILLE", help="Position (1, 2…) ou identifiant B-….")
    sous.add_argument("champ", metavar="CHAMP", help="Clé du champ : millesime, domaine, quantite, estimation…")
    sous.add_argument("valeur", metavar="VALEUR", help="Liste : code ou libellé. Quantité : entier ≥ 1.")
    sous.add_argument("--auteur", required=True, help="Qui corrige : tracé dans l'historique.")

    sous = commande("valider", _valider, "Marque une bouteille comme relue et approuvée.")
    sous.add_argument("inventaire", type=int, metavar="ID")
    sous.add_argument("bouteille", metavar="BOUTEILLE", help="Position (1, 2…) ou identifiant B-….")
    sous.add_argument("--auteur", required=True, help="Qui valide : tracé dans l'historique.")

    sous = commande("stats", _stats, "Statuts, coût en tokens, champs les plus corrigés.")
    sous.add_argument("inventaire", type=int, metavar="ID")

    sous = commande("exporter", _exporter, "Excel de l'inventaire : modèle + corrections.")
    sous.add_argument("inventaire", type=int, metavar="ID")
    sous.add_argument("--sortie", type=Path, help="Chemin du .xlsx (défaut : out/inventaire_ID.xlsx).")
    return analyseur


if __name__ == "__main__":
    raise SystemExit(main())
