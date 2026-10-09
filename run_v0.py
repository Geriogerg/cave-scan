#!/usr/bin/env python
"""Orchestrateur de la v0 : photos -> Excel + tableau de scores.

    python run_v0.py --dry-run
    python run_v0.py --photos data/photos --manual data/listing_expert.json

Le livrable est le RAPPORT DE COMPARAISON imprimé en fin de course. L'Excel
n'est que la forme livrable du listing automatique ; il ne prouve rien à lui
seul (CLAUDE.md).

Ce module ne connaît que le Protocol `Extractor` : il ne sait pas s'il parle à
un VLM ou à des fixtures (decisions.md 0014).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from src.compare.compare_listings import (
    comparer,
    formater_rapport,
    formater_signaux,
    relever_signaux,
)
from src.config.maison import ConfigInvalide, ConfigMaison, charger_config
from src.export.excel_writer import ecrire_excel
from src.extract.base import Extractor
from src.extract.fixture_extract import FixtureExtractor
from src.extract.schema import Bouteille, bouteille_depuis_dict
from src.io.manual_listing import colonnes_toujours_vides, load_manual
from src.io.photos import PhotosBouteille, PhotosInvalides, apparier_photos
from src.normalize.normalize import normalize

RACINE = Path(__file__).resolve().parent
CONFIG_DEFAUT = RACINE / "config" / "maisons" / "maison_test.json"
SORTIE_DEFAUT = RACINE / "out" / "listing_auto.xlsx"

FIXTURES = RACINE / "tests" / "fixtures"
FIXTURE_AUTO = FIXTURES / "bouteilles_auto.json"
FIXTURE_MANUEL = FIXTURES / "manuel.json"


def _charger_env() -> None:
    """Charge `.env` s'il existe, pour que `.env.example` dise la vérité.

    Le SDK ne lit que les variables d'environnement : sans ceci, un `.env`
    rempli consciencieusement n'aurait servi à rien, et l'erreur aurait été
    un « clé absente » incompréhensible.
    """
    fichier = RACINE / ".env"
    if not fichier.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        print(
            f"⚠  {fichier} existe mais python-dotenv n'est pas installé : "
            f"il ne sera pas lu.\n   `pip install python-dotenv`, ou exportez "
            f"ANTHROPIC_API_KEY dans l'environnement.",
            file=sys.stderr,
        )
        return
    load_dotenv(fichier)


def charger_journal(journal: Path) -> list[Bouteille]:
    """Relit les bouteilles déjà extraites lors d'un run interrompu.

    Le journal est écrit par l'outil lui-même : il se relit comme une source de
    confiance (identifiant, quantité, codes propres à la maison conservés).
    """
    if not journal.exists():
        return []
    return [
        bouteille_depuis_dict(json.loads(ligne))
        for ligne in journal.read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]


def extraire(
    extracteur: Extractor,
    photos: Sequence[PhotosBouteille],
    journal: Path | None = None,
    reprendre: bool = False,
) -> list[Bouteille]:
    """Extrait puis normalise, bouteille par bouteille, dans l'ordre.

    Chaque bouteille est écrite dans le journal DÈS qu'elle est extraite
    (decisions.md 0046) : une campagne de 200 bouteilles interrompue à la 180e
    ne doit pas perdre 180 appels API déjà payés. `reprendre` repart de là où
    le journal s'arrête.

    Chaque bouteille reçoit l'identifiant stable de ses photos (decisions.md
    0065), posé par le pipeline et jamais par le modèle.
    """
    identifiants = [vues.identifiant for vues in photos]
    _refuser_les_doublons(photos, identifiants)

    bouteilles: list[Bouteille] = []

    if journal is not None:
        journal.parent.mkdir(parents=True, exist_ok=True)
        if reprendre:
            bouteilles = charger_journal(journal)
            _verifier_reprise(bouteilles, identifiants, journal)
            if bouteilles:
                print(f"  reprise : {len(bouteilles)} bouteille(s) déjà au journal")
        else:
            journal.write_text("", encoding="utf-8")

    for index, vues in enumerate(photos[len(bouteilles) :], start=len(bouteilles) + 1):
        print(f"  [{index}/{len(photos)}] {vues.nom}", flush=True)
        bouteille = normalize(
            extracteur.extract(
                etiquette=vues.etiquette,
                contre_etiquette=vues.contre_etiquette,
                autres=vues.autres,
            )
        )
        bouteille.id = identifiants[index - 1]
        bouteilles.append(bouteille)
        if journal is not None:
            with journal.open("a", encoding="utf-8") as flux:
                flux.write(json.dumps(bouteille.as_dict(), ensure_ascii=False) + "\n")

    return bouteilles


def _refuser_les_doublons(photos: Sequence[PhotosBouteille], identifiants: list[str]) -> None:
    """Deux bouteilles aux photos identiques : presque toujours une photo copiée
    deux fois. On s'arrête AVANT tout appel au modèle plutôt que de payer deux
    fois la même bouteille et de fausser l'alignement avec le listing."""
    vus: dict[str, int] = {}
    doublons = []
    for rang, identifiant in enumerate(identifiants):
        if identifiant in vus:
            doublons.append(f"{photos[vus[identifiant]].nom} et {photos[rang].nom}")
        vus.setdefault(identifiant, rang)
    if doublons:
        raise ValueError(
            "Photos identiques pour plusieurs bouteilles (photo copiée deux fois ?) : "
            + " ; ".join(doublons)
        )


def _verifier_reprise(bouteilles: list[Bouteille], identifiants: list[str], journal: Path) -> None:
    """Une reprise n'a de sens que sur les MÊMES photos : sinon chaque bouteille
    reprise serait décalée d'une ligne, en silence."""
    if len(bouteilles) > len(identifiants):
        raise ValueError(
            f"{journal} contient {len(bouteilles)} bouteille(s) pour {len(identifiants)} "
            f"paire(s) de photos : le dossier a changé depuis le run interrompu. "
            f"Relancer sans --reprendre."
        )
    for rang, (bouteille, attendu) in enumerate(zip(bouteilles, identifiants), start=1):
        if bouteille.id and bouteille.id != attendu:
            raise ValueError(
                f"{journal} ne correspond plus aux photos (bouteille n°{rang} : "
                f"{bouteille.id} au journal, {attendu} sur le disque). Dossier modifié "
                f"depuis le run interrompu ? Relancer sans --reprendre."
            )


def _annoncer_appariement(appariement) -> None:
    """Montre l'appariement AVANT l'extraction : une paire décalée se voit ici,
    pas après avoir payé tous les appels (decisions.md 0023, 0068)."""
    print(f"Appariement de {len(appariement.bouteilles)} paire(s), tri par {appariement.tri} :")
    if appariement.sans_date:
        print(
            f"  ⚠  {len(appariement.sans_date)} photo(s) sans date EXIF "
            f"({', '.join(appariement.sans_date[:3])}{'…' if len(appariement.sans_date) > 3 else ''}) : "
            f"tri par nom de fichier pour TOUTES — vérifier qu'il suit l'ordre de prise de vue."
        )
    for rang, vues in enumerate(appariement.bouteilles, start=1):
        print(f"  {rang:>3}. {vues.nom}")
    print()


def _photos_factices(nombre: int) -> list[PhotosBouteille]:
    """Chemins fictifs du dry-run : `FixtureExtractor` les ignore, mais le
    pipeline garde exactement la même forme qu'avec de vraies photos."""
    return [
        PhotosBouteille(
            etiquette=Path(f"(fixture)/bouteille_{i:02d}_etiquette.jpg"),
            contre_etiquette=Path(f"(fixture)/bouteille_{i:02d}_contre.jpg"),
        )
        for i in range(1, nombre + 1)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        description="Pipeline v0 : extraction VLM -> Excel maison -> scores vs expert."
    )
    analyseur.add_argument(
        "--dry-run",
        action="store_true",
        help="Tourne hors ligne sur les fixtures : ni clé API, ni réseau, ni photos.",
    )
    analyseur.add_argument("--photos", type=Path, help="Dossier des photos.")
    analyseur.add_argument(
        "--backend",
        choices=("gemini", "anthropic"),
        default="gemini",
        help="Fournisseur du modèle vision. « gemini » (défaut) a un palier "
        "GRATUIT, mais Flash uniquement : bon pour valider le pipeline. Le "
        "chiffre qui décide de la suite mérite d'être rejoué sur "
        "« anthropic » (payant, ~0,06 €/bouteille) — cf. decisions.md 0050.",
    )
    analyseur.add_argument(
        "--manual",
        type=Path,
        help="Listing manuel de l'expert. SANS lui : extraction et Excel "
        "seulement, aucun score — c'est le mode d'attente avant que le fichier "
        "de l'expert existe.",
    )
    analyseur.add_argument(
        "--auto",
        type=Path,
        help="Rejoue un journal .jsonl déjà produit au lieu de ré-extraire. "
        "Permet de refaire le score autant de fois qu'on veut — après "
        "correction du listing expert, par exemple — sans rappeler le modèle.",
    )
    analyseur.add_argument(
        "--limite",
        type=int,
        help="N'extrait que les N premières bouteilles. À utiliser pour le "
        "premier run payant : on vérifie sur 3 bouteilles avant d'en lancer 200.",
    )
    analyseur.add_argument(
        "--maison",
        type=Path,
        default=CONFIG_DEFAUT,
        help=f"Config JSON de la maison (défaut : {CONFIG_DEFAUT.name}). "
        "Validée au démarrage : une config invalide arrête tout.",
    )
    analyseur.add_argument(
        "--sortie", type=Path, default=SORTIE_DEFAUT, help="Chemin du .xlsx produit."
    )
    analyseur.add_argument(
        "--journal",
        type=Path,
        help="Journal d'extraction .jsonl (défaut : à côté du .xlsx). "
        "Écrit au fil de l'eau pour ne rien perdre si le run s'interrompt.",
    )
    analyseur.add_argument(
        "--reprendre",
        action="store_true",
        help="Repart du journal existant au lieu de tout ré-extraire.",
    )
    arguments = analyseur.parse_args(argv)
    journal = arguments.journal or arguments.sortie.with_suffix(".jsonl")

    # Le rapport ET les messages d'erreur contiennent des accents ; la console
    # Windows est en cp1252 par défaut. Les deux flux, sinon un refus de config
    # ou de photos s'afficherait mutilé, au moment précis où il faut le lire.
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")

    _charger_env()

    # La config est validée AVANT tout appel au modèle : une config invalide ne
    # doit coûter ni un appel, ni une seconde (guide, étape 4.1).
    try:
        config = charger_config(arguments.maison)
    except ConfigInvalide as erreur:
        print(erreur, file=sys.stderr)
        return 2
    print(f"Config : {config.maison}, version {config.version} ({config.chemin.name})")
    for avertissement in config.avertissements:
        print(f"⚠  {avertissement}")
    print()

    # Rejeu : ni modèle, ni photos, ni clé — juste re-scorer.
    if arguments.auto:
        bouteilles = charger_journal(arguments.auto)
        if not bouteilles:
            analyseur.error(f"Journal vide ou introuvable : {arguments.auto}")
        print(f"Rejeu de {arguments.auto} — {len(bouteilles)} bouteille(s).")
        return _restituer(bouteilles, config, arguments.manual, arguments.sortie, journal=None)

    if arguments.dry_run:
        extracteur: Extractor = FixtureExtractor.depuis_json(FIXTURE_AUTO, config)
        photos = _photos_factices(len(extracteur))
        chemin_manuel = FIXTURE_MANUEL
        print(f"DRY-RUN — fixtures {FIXTURE_AUTO.name} / {FIXTURE_MANUEL.name}, hors ligne.\n")
    else:
        if not arguments.photos:
            analyseur.error("--photos est requis hors --dry-run.")

        # Les photos sont vérifiées AVANT de créer le client du modèle : un
        # dossier invalide (nombre impair, HEIC…) se signale sans clé ni coût.
        try:
            appariement = apparier_photos(arguments.photos)
        except PhotosInvalides as erreur:
            print(erreur, file=sys.stderr)
            return 2
        photos = appariement.bouteilles
        _annoncer_appariement(appariement)
        if arguments.limite:
            photos = photos[: arguments.limite]

        # Imports tardifs : le dry-run ne doit dépendre d'aucun SDK ni clé API,
        # et le backend gratuit ne doit pas exiger le SDK payant (ni l'inverse).
        if arguments.backend == "gemini":
            from src.extract.gemini_extract import GeminiExtractor

            try:
                extracteur: Extractor = GeminiExtractor(config=config)
            except ValueError as erreur:  # le SDK refuse de créer un client sans clé
                print(
                    f"Clé Gemini absente : {erreur}\n"
                    f"-> La renseigner dans {RACINE / '.env'} (GEMINI_API_KEY=...), "
                    f"voir .env.example.",
                    file=sys.stderr,
                )
                return 2
        else:
            from src.extract.vision_extract import VisionExtractor

            extracteur = VisionExtractor(config=config)
        chemin_manuel = arguments.manual
        print(f"Modèle : {extracteur.modele} — {len(photos)} bouteille(s).\n")

    print("Extraction :")
    bouteilles = extraire(extracteur, photos, journal, arguments.reprendre)
    return _restituer(bouteilles, config, chemin_manuel, arguments.sortie, journal)


def _restituer(
    bouteilles: list[Bouteille],
    config: ConfigMaison,
    chemin_manuel: Path | None,
    sortie: Path,
    journal: Path | None,
) -> int:
    """Excel + rapport. Commun à l'extraction et au rejeu d'un journal."""
    chemin_excel = ecrire_excel(bouteilles, config, sortie)
    print(f"\nListing automatique écrit : {chemin_excel}")
    if journal is not None:
        print(f"Journal d'extraction       : {journal}")

    if chemin_manuel is None:
        print(
            "\nAucun listing manuel fourni : PAS DE SCORE.\n"
            "Le livrable de la v0 est la comparaison à l'expert ; sans son "
            "fichier,\nce run montre seulement ce que le modèle produit.\n"
        )
        print(formater_signaux(relever_signaux(bouteilles, _systematiques(config))))
        return 0

    manuel = load_manual(chemin_manuel, config)

    vides = colonnes_toujours_vides(manuel)
    if vides:
        print(
            f"\n⚠  Colonnes jamais renseignées par l'expert : {', '.join(vides)}.\n"
            f"   Soit il ne les remplit pas, soit l'en-tête du fichier ne "
            f"correspond pas au champ canonique — dans ce second cas le score "
            f"de ces champs ne veut rien dire."
        )

    rapport = comparer(bouteilles, manuel, systematiques=_systematiques(config))
    print()
    print(formater_rapport(rapport))
    return 0



def _systematiques(config: ConfigMaison) -> tuple[str, ...]:
    """Colonnes best effort : toujours à vérifier, donc pas des doutes du modèle."""
    return tuple(colonne.cle for colonne in config.colonnes_best_effort)


if __name__ == "__main__":
    raise SystemExit(main())
