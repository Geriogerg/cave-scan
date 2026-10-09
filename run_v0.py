#!/usr/bin/env python
"""Orchestrateur : photos -> base -> Excel + score du modèle.

    python run_v0.py --dry-run
    python run_v0.py --photos data/photos [--manual listing.xlsx] [--nom "Cave X"] [--limite 3]
    python run_v0.py --inventaire 4 [--manual listing.xlsx]

`--photos` crée un inventaire (config figée, photos stockées), l'extrait, l'exporte.
`--inventaire ID` reprend un inventaire existant : termine son extraction là où
elle s'était arrêtée — sans jamais refaire une bouteille déjà extraite — puis
réexporte et rescore.

Ce script ne contient AUCUNE logique métier (decisions.md 0080) : il lit la ligne
de commande, appelle les fonctions de service, affiche. Il ne connaît que le
Protocol `Extractor`, jamais une implémentation précise (0014). Le livrable reste
le RAPPORT DE COMPARAISON : le score du modèle face à l'expert (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from src.compare.compare_listings import formater_rapport, formater_signaux
from src.config import environnement
from src.config.maison import ConfigInvalide, ConfigMaison, charger_config
from src.donnees.base import dossier_stockage, session_de_base
from src.donnees.modeles import FicheBouteille
from src.extract.base import Extractor
from src.extract.fixture_extract import FixtureExtractor, generer_photos_fictives
from src.io.photos import PhotosInvalides
from src.services.extraction import ExtractionArretee, extraire_inventaire, reste_a_extraire
from src.services.inventaires import (
    InventaireCree,
    InventaireIntrouvable,
    charger_inventaire,
    config_figee,
    creer_inventaire,
)
from src.services.restitution import (
    comparer_au_listing,
    exporter,
    lister_bouteilles,
    signaux_du_modele,
    stats_inventaire,
)

RACINE = Path(__file__).resolve().parent
CONFIG_DEFAUT = RACINE / "config" / "maisons" / "maison_test.json"
SORTIE_DEFAUT = RACINE / "out" / "listing_auto.xlsx"

FIXTURES = RACINE / "tests" / "fixtures"
FIXTURE_AUTO = FIXTURES / "bouteilles_auto.json"
FIXTURE_MANUEL = FIXTURES / "manuel.json"

# Options d'avant la base de données : on dit par quoi elles sont remplacées,
# plutôt que de laisser argparse répondre « argument non reconnu » (0084).
OPTIONS_REMPLACEES = {
    "journal": (
        "--journal n'existe plus : chaque extraction est enregistrée dans la base "
        "dès qu'elle revient (CAVE_SCAN_DB, ou --base). Pour reprendre, réexporter "
        "ou rescorer un inventaire : --inventaire ID."
    ),
    "reprendre": (
        "--reprendre est remplacé par --inventaire ID : la base garde les "
        "extractions déjà faites, et relancer avec le numéro de l'inventaire "
        "reprend là où il s'est arrêté. Numéros : python inventaire.py lister"
    ),
    "auto": (
        "--auto est remplacé par --inventaire ID : il réexporte et rescore depuis "
        "la base sans rappeler le modèle (ajouter --manual pour le score). "
        "Numéros : python inventaire.py lister"
    ),
}


class Arret(Exception):
    """Arrêt propre : le message dit quoi faire ; code de sortie 2."""


def main(argv: Sequence[str] | None = None) -> int:
    # Rapport ET messages d'erreur contiennent des accents ; la console Windows
    # est en cp1252 par défaut (decisions.md 0039, 0071).
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")

    analyseur = _analyseur()
    arguments = analyseur.parse_args(argv)
    for option, message in OPTIONS_REMPLACEES.items():
        if getattr(arguments, option) is not None:
            print(message, file=sys.stderr)
            return 2
    if not (arguments.dry_run or arguments.photos or arguments.inventaire is not None):
        analyseur.error("indiquer --photos (nouvel inventaire), --inventaire ID (reprise) ou --dry-run.")

    environnement.charger_env()  # clés, base, stockage : comme inventaire.py
    try:
        if arguments.dry_run:
            return _dry_run(arguments)
        if arguments.manual is not None and not arguments.manual.is_file():
            # Avant tout appel payant, pas après.
            raise Arret(f"Listing manuel introuvable : {arguments.manual}")
        if arguments.inventaire is not None:
            return _reprendre(arguments)
        return _nouvel_inventaire(arguments)
    except Arret as arret:
        print(arret, file=sys.stderr)
        return 2


# --- les trois modes ------------------------------------------------------------------------


def _dry_run(arguments: argparse.Namespace) -> int:
    """Le vrai chemin, hors ligne : photos générées, extraction rejouée depuis les
    fixtures (decisions.md 0085). Base et stockage TEMPORAIRES : la base de
    l'utilisateur n'est jamais touchée — sauf `--base`, qui garde l'inventaire
    de démonstration pour essayer `inventaire.py` sans clé."""
    print(f"DRY-RUN — fixtures {FIXTURE_AUTO.name} / {FIXTURE_MANUEL.name}, hors ligne.\n")
    chemin_config = arguments.maison or CONFIG_DEFAUT
    config = _config(chemin_config)
    extracteur = FixtureExtractor.depuis_json(FIXTURE_AUTO, config)

    with tempfile.TemporaryDirectory(prefix="cave-scan-dry-run-") as temporaire:
        temporaire = Path(temporaire)
        photos = generer_photos_fictives(temporaire / "photos", len(extracteur))
        if arguments.base is None:
            base, stockage = temporaire / "base.db", temporaire / "stockage"
        else:  # la base gardée ne doit pas pointer vers des photos effacées
            base, stockage = arguments.base, dossier_stockage()
        with session_de_base(base) as session:
            cree = _creer(session, config, chemin_config, photos, "dry-run", stockage, None)
            _extraire(session, cree.inventaire_id, extracteur, stockage)
            _restituer(session, cree.inventaire_id, FIXTURE_MANUEL, arguments.sortie)
            if arguments.base is not None:
                _rappel_reprise(cree.inventaire_id, arguments.base)
    return 0


def _nouvel_inventaire(arguments: argparse.Namespace) -> int:
    chemin_config = arguments.maison or CONFIG_DEFAUT
    config = _config(chemin_config)
    nom = arguments.nom or f"{arguments.photos.name} — {datetime.now():%Y-%m-%d %H:%M}"
    stockage = dossier_stockage()

    with session_de_base(arguments.base) as session:
        # Les photos sont vérifiées (impair, HEIC, doublons) AVANT la création du
        # client du modèle : un dossier invalide se signale sans clé ni coût.
        cree = _creer(session, config, chemin_config, arguments.photos, nom, stockage, arguments.limite)
        extracteur = _extracteur(arguments.backend, config, cree.inventaire_id)
        print(f"Modèle : {extracteur.modele}\n")
        _extraire(session, cree.inventaire_id, extracteur, stockage)
        _restituer(session, cree.inventaire_id, arguments.manual, arguments.sortie)
        _rappel_reprise(cree.inventaire_id, arguments.base)
    return 0


def _reprendre(arguments: argparse.Namespace) -> int:
    creation = (("--maison", arguments.maison), ("--limite", arguments.limite), ("--nom", arguments.nom))
    ignorees = [option for option, valeur in creation if valeur is not None]
    if ignorees:
        print(
            f"⚠  {', '.join(ignorees)} ignoré(s) : s'applique(nt) à la création d'un "
            f"inventaire, qui garde ensuite sa config figée (decisions.md 0073)."
        )

    stockage = dossier_stockage()
    with session_de_base(arguments.base) as session:
        try:
            inventaire = charger_inventaire(session, arguments.inventaire)
        except InventaireIntrouvable as erreur:
            raise Arret(f"{erreur} Numéros : python inventaire.py lister") from None
        version = inventaire.config_version
        print(
            f"Inventaire n°{inventaire.id} « {inventaire.nom} » — {inventaire.maison.nom}, "
            f"config n°{version.numero} (version {version.version_declaree}, figée).\n"
        )
        reste = reste_a_extraire(session, inventaire.id)
        if reste:
            extracteur = _extracteur(arguments.backend, config_figee(inventaire), inventaire.id)
            print(f"Modèle : {extracteur.modele} — {reste} bouteille(s) à extraire.\n")
            _extraire(session, inventaire.id, extracteur, stockage)
        else:
            print("Toutes les bouteilles sont extraites : aucun appel au modèle.")
        _restituer(session, inventaire.id, arguments.manual, arguments.sortie)
    return 0


# --- étapes communes ----------------------------------------------------------------------


def _creer(
    session: Session,
    config: ConfigMaison,
    chemin_config: Path,
    photos: Path,
    nom: str,
    stockage: Path,
    limite: int | None,
) -> InventaireCree:
    try:
        cree = creer_inventaire(session, config.maison, chemin_config, photos, nom, stockage, limite)
    except (PhotosInvalides, NotADirectoryError) as erreur:
        raise Arret(str(erreur)) from None

    connue = "nouvelle version" if cree.nouvelle_config else "version déjà connue"
    print(f"Inventaire n°{cree.inventaire_id} « {nom} » — config n°{cree.config_numero} ({connue}).")
    for avertissement in cree.avertissements:
        if avertissement not in config.avertissements:  # celles-ci, déjà affichées
            print(f"⚠  {avertissement}")

    # L'appariement AVANT l'extraction : une paire décalée se voit ici, pas
    # après avoir payé tous les appels (decisions.md 0023, 0068).
    print(f"Appariement de {cree.nb_bouteilles} paire(s), tri par {cree.tri} :")
    if cree.sans_date:
        apercu = ", ".join(cree.sans_date[:3]) + ("…" if len(cree.sans_date) > 3 else "")
        print(
            f"  ⚠  {len(cree.sans_date)} photo(s) sans date EXIF ({apercu}) : tri par nom "
            f"de fichier pour TOUTES — vérifier qu'il suit l'ordre de prise de vue."
        )
    for bouteille in lister_bouteilles(session, cree.inventaire_id):
        print(
            f"  {bouteille.position:>3}. {bouteille.identifiant}  "
            f"{bouteille.photo_etiquette.nom_origine} + {bouteille.photo_contre.nom_origine}"
        )
    print()
    return cree


def _extraire(session: Session, inventaire_id: int, extracteur: Extractor, stockage: Path) -> None:
    def progression(rang: int, total: int, bouteille: FicheBouteille) -> None:
        print(f"  [{rang}/{total}] n°{bouteille.position} {bouteille.identifiant}", flush=True)

    reprise = f"    python run_v0.py --inventaire {inventaire_id}"
    print("Extraction :")
    try:
        bilan = extraire_inventaire(session, inventaire_id, extracteur, stockage, progression)
    except ExtractionArretee as arret:
        raise Arret(
            f"\n{arret}\nLes bouteilles déjà extraites sont en base. Une fois la cause "
            f"corrigée, reprendre là où l'extraction s'est arrêtée :\n{reprise}"
        ) from None
    except KeyboardInterrupt:
        raise Arret(
            f"\nInterrompu. Les bouteilles déjà extraites sont en base ; reprendre là où "
            f"l'extraction s'est arrêtée :\n{reprise}"
        ) from None

    print(
        f"  {bilan.extraites} extraite(s), {bilan.en_erreur} en erreur, "
        f"{bilan.deja_faites} déjà faite(s) avant ce lancement."
    )
    if bilan.en_erreur:
        print(f"  Les bouteilles en erreur seront retentées par :\n{reprise}")
    stats = stats_inventaire(session, inventaire_id)
    if stats.tokens_par_bouteille is not None:
        entree, sortie = stats.tokens_par_bouteille
        print(f"  Coût : ~{entree:.0f} tokens en entrée et ~{sortie:.0f} en sortie par bouteille.")


def _restituer(session: Session, inventaire_id: int, chemin_manuel: Path | None, sortie: Path) -> None:
    try:
        chemin_excel = exporter(session, inventaire_id, sortie)
    except PermissionError as erreur:  # Windows : le fichier est ouvert dans Excel
        raise Arret(
            f"Impossible d'écrire {erreur.filename} : le fichier est-il ouvert dans Excel ? "
            f"Le fermer puis relancer — pour un inventaire en base, sans rien réextraire :\n"
            f"    python run_v0.py --inventaire {inventaire_id}"
        ) from None
    print(f"\nListing automatique écrit : {chemin_excel}")

    if chemin_manuel is None:
        print(
            "\nAucun listing manuel fourni : PAS DE SCORE.\n"
            "Le livrable de la v0 est la comparaison à l'expert ; sans son "
            "fichier,\nce run montre seulement ce que le modèle produit.\n"
        )
        print(formater_signaux(signaux_du_modele(session, inventaire_id)))
        return

    resultat = comparer_au_listing(session, inventaire_id, chemin_manuel)
    if resultat.colonnes_toujours_vides:
        print(
            f"\n⚠  Colonnes jamais renseignées par l'expert : "
            f"{', '.join(resultat.colonnes_toujours_vides)}.\n"
            f"   Soit il ne les remplit pas, soit l'en-tête du fichier ne correspond "
            f"pas au champ canonique — dans ce second cas le score de ces champs ne "
            f"veut rien dire."
        )
    print()
    print(formater_rapport(resultat.rapport))


def _rappel_reprise(inventaire_id: int, base: Path | None) -> None:
    option = f' --base "{base}"' if base is not None else ""
    print(
        f"\nInventaire n°{inventaire_id} en base. Reprendre, réexporter ou rescorer :\n"
        f"    python run_v0.py --inventaire {inventaire_id}{option} [--manual LISTING]\n"
        f"Relire, corriger, valider, statistiques :\n"
        f"    python inventaire.py bouteilles {inventaire_id}{option}"
    )


# --- branchements ----------------------------------------------------------------------


def _config(chemin: Path) -> ConfigMaison:
    """La config validée AVANT tout appel au modèle (guide de session 1, étape 4.1)."""
    try:
        config = charger_config(chemin)
    except ConfigInvalide as erreur:
        raise Arret(str(erreur)) from None
    print(f"Config : {config.maison}, version {config.version} ({config.chemin.name})")
    for avertissement in config.avertissements:
        print(f"⚠  {avertissement}")
    print()
    return config


def _extracteur(backend: str, config: ConfigMaison, inventaire_id: int) -> Extractor:
    """Le fournisseur choisi. Imports tardifs : le dry-run ne dépend d'aucun SDK,
    et le backend gratuit n'exige pas le SDK payant (ni l'inverse)."""
    if backend == "anthropic":
        from src.extract.vision_extract import VisionExtractor

        return VisionExtractor(config=config)

    from src.extract.gemini_extract import GeminiExtractor

    try:
        return GeminiExtractor(config=config)
    except ValueError as erreur:  # le SDK refuse de créer un client sans clé
        raise Arret(
            f"Clé Gemini absente : {erreur}\n"
            f"-> La renseigner dans {environnement.FICHIER_ENV} (GEMINI_API_KEY=...), voir .env.example,\n"
            f"   puis reprendre l'inventaire n°{inventaire_id} (déjà créé, photos stockées) :\n"
            f"    python run_v0.py --inventaire {inventaire_id}"
        ) from None


def _analyseur() -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(
        description="Pipeline : photos -> base -> Excel maison -> score du modèle face à l'expert. "
        "Relecture et corrections : inventaire.py."
    )
    mode = analyseur.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Tourne hors ligne sur les fixtures : ni clé API, ni réseau, ni photos ; "
        "base temporaire, sauf --base.",
    )
    mode.add_argument("--photos", type=Path, help="Dossier des photos : crée un nouvel inventaire.")
    mode.add_argument(
        "--inventaire",
        type=int,
        metavar="ID",
        help="Reprend un inventaire existant : termine son extraction là où elle "
        "s'était arrêtée, réexporte, rescore.",
    )

    analyseur.add_argument(
        "--backend",
        choices=("gemini", "anthropic"),
        default="gemini",
        help="Fournisseur du modèle vision. « gemini » (défaut) a un palier GRATUIT, "
        "mais Flash uniquement : bon pour valider le pipeline. Le chiffre qui décide "
        "de la suite mérite d'être rejoué sur « anthropic » (payant) — decisions.md 0050.",
    )
    analyseur.add_argument(
        "--manual",
        type=Path,
        help="Listing manuel de l'expert. SANS lui : extraction et Excel seulement, "
        "aucun score.",
    )
    analyseur.add_argument("--nom", help="Nom du nouvel inventaire (défaut : dossier + date).")
    analyseur.add_argument(
        "--limite",
        type=int,
        help="Le nouvel inventaire ne garde que les N premières bouteilles : vérifier "
        "sur 3 bouteilles avant d'en lancer 200.",
    )
    analyseur.add_argument(
        "--maison",
        type=Path,
        help=f"Config JSON de la maison (défaut : {CONFIG_DEFAUT.name}). Figée dans "
        "l'inventaire à sa création.",
    )
    analyseur.add_argument(
        "--sortie", type=Path, default=SORTIE_DEFAUT, help="Chemin du .xlsx produit."
    )
    analyseur.add_argument(
        "--base",
        type=Path,
        help="Base de données (défaut : variable CAVE_SCAN_DB, sinon data/cave_scan.db).",
    )

    # Remplacées : acceptées pour pouvoir dire par quoi (decisions.md 0084).
    analyseur.add_argument("--journal", nargs="?", const="", help=argparse.SUPPRESS)
    analyseur.add_argument("--reprendre", action="store_const", const="", help=argparse.SUPPRESS)
    analyseur.add_argument("--auto", nargs="?", const="", help=argparse.SUPPRESS)
    return analyseur


if __name__ == "__main__":
    raise SystemExit(main())
