"""La configuration d'une maison : nouvelle version, import, export, aperçu
(session 6 ; decisions.md 0161).

Le fichier JSON de `config/maisons/` reste LA config active d'une maison : la
ligne de commande le lit, et le format de chaque maison reste piloté par lui
(CLAUDE.md, contrainte 6). La page « Configuration » et l'import ne font rien
d'autre que produire une NOUVELLE version de ce fichier :

1. le contenu est validé EXACTEMENT comme un fichier (`config_depuis_texte`) :
   rien n'est écrit tant qu'il reste une erreur ;
2. son numéro de version est fixé par l'outil (la précédente + 1) ;
3. le fichier est réécrit d'un coup (fichier temporaire puis remplacement) ;
4. la version est enregistrée en base : chaque version reste exportable, et un
   inventaire garde celle de sa création (decisions.md 0073).
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.extract.consignes import CONSIGNES_MODIFIABLES
from src.config.maison import (
    NOYAU_CANONIQUE,
    SOURCES_MODELE,
    Colonne,
    ConfigInvalide,
    ConfigMaison,
    colonne_depuis_brut,
    config_depuis_texte,
    empreinte_config,
    lire_config,
    plier,
)
from src.donnees.modeles import ConfigVersion, Maison
from src.extract.schema import propriete_modele
from src.services.inventaires import _maison, _version_de_config

# Deux enregistrements simultanés liraient la même version et écriraient la
# même suivante : la lecture, la vérification et l'écriture se font d'un tenant.
_VERROU = threading.Lock()


class ConfigIntrouvable(LookupError):
    """Aucune config active pour cette maison (ou ce fichier), ou aucune version
    de ce numéro."""


class ConfigModifieeAilleurs(RuntimeError):
    """La config a changé depuis qu'elle a été ouverte (autre onglet, autre
    personne) : rien n'est écrit, il faut repartir de la version actuelle."""


class ConfigInchangee(ValueError):
    """Le contenu est identique à la version active : aucune version créée."""


@dataclass(frozen=True)
class ConfigActive:
    """La config active d'une maison : son fichier, validé."""

    fichier: Path
    texte: str
    config: ConfigMaison

    @property
    def brut(self) -> dict[str, Any]:
        return json.loads(self.texte)


@dataclass(frozen=True)
class VersionEnregistree:
    maison: str
    fichier: Path
    version: int  # le « version » écrit dans le fichier
    numero: int  # la version en base (compteur propre à la maison)
    nouvelle_maison: bool
    avertissements: list[str] = field(default_factory=list)


# --- lire ----------------------------------------------------------------------------------


def config_active(dossier_configs: Path, maison: str) -> ConfigActive:
    """Le fichier de la maison, validé. `LookupError` si aucune config valide ne
    la décrit."""
    for fichier in sorted(Path(dossier_configs).glob("*.json")):
        try:
            config, texte = lire_config(fichier)
        except ConfigInvalide:
            continue
        if plier(config.maison) == plier(maison):
            return ConfigActive(fichier=fichier, texte=texte, config=config)
    raise ConfigIntrouvable(f"Aucune config pour la maison « {maison} » dans {Path(dossier_configs).name}/.")


def maison_de_l_instance(dossier_configs: Path) -> str | None:
    """Une instance de l'application = une maison (decisions.md 0171) : sa
    configuration est la seule de `config/maisons/`. Si le dossier en contient
    plusieurs, la variable `CAVE_SCAN_MAISON` désigne celle de l'instance ; à
    défaut, la première par nom de fichier. None : aucune configuration valide."""
    valides = []
    for fichier in sorted(Path(dossier_configs).glob("*.json")):
        try:
            valides.append(lire_config(fichier)[0].maison)
        except ConfigInvalide:
            continue
    choisie = os.environ.get("CAVE_SCAN_MAISON", "").strip()
    if choisie:
        for maison in valides:
            if plier(maison) == plier(choisie):
                return maison
    return valides[0] if valides else None


# Le point de départ d'une configuration créée à la main (decisions.md 0172) :
# le numéro, la quantité, le noyau canonique toujours lu par le modèle et la
# colonne des doutes. Tout le reste s'ajoute ensuite sur la page.
CONFIGURATION_DE_DEPART: dict[str, Any] = {
    "version": 1,
    "langue": "fr",
    "photos_max_par_bouteille": 4,
    "regroupement_export": ["domaine", "appellation", "millesime", "format"],
    "colonnes": [
        {"cle": "id", "nom": "N°", "type": "texte", "source": "systeme",
         "description": "Identifiant stable de la bouteille, généré par l'outil."},
        {"cle": "quantite", "nom": "Quantité", "type": "nombre", "source": "expert",
         "description": "Nombre de bouteilles identiques et de même état. 1 par défaut."},
        {"cle": "domaine", "nom": "Domaine / Château", "type": "texte", "source": "modele",
         "description": "Producteur tel qu'écrit sur l'étiquette."},
        {"cle": "appellation", "nom": "Appellation", "type": "texte", "source": "modele",
         "description": "Appellation d'origine, avec la mention Grand Cru / 1er Cru si présente."},
        {"cle": "millesime", "nom": "Millésime", "type": "texte", "source": "modele",
         "description": "Année sur 4 chiffres, uniquement si lue sur l'étiquette, jamais déduite."},
        {"cle": "format", "nom": "Format", "type": "liste", "source": "modele_best_effort",
         "regle": "Seulement si la contenance est imprimée ou si la photo montre la bouteille entière.",
         "valeurs": [
             {"code": "demi_bouteille", "libelle": "Demi-bouteille", "description": "37,5 cl."},
             {"code": "bouteille", "libelle": "Bouteille", "description": "75 cl."},
             {"code": "magnum", "libelle": "Magnum", "description": "1,5 L."},
             {"code": "autre", "libelle": "Autre", "description": "Tout autre format."},
         ]},
        {"cle": "a_verifier", "nom": "À vérifier", "type": "texte", "source": "systeme",
         "description": "Champs incertains signalés par le modèle, pour la relecture."},
    ],
}


def creer_configuration(session: Session, dossier_configs: Path) -> VersionEnregistree:
    """Une configuration créée à la main, sans fichier JSON : le point de départ
    ci-dessus, que l'expert complète ensuite colonne par colonne (0172). Refusé
    si l'application en a déjà une : on la modifie, on n'en crée pas une autre."""
    if maison_de_l_instance(dossier_configs) is not None:
        raise ConfigInvalide("L'application a déjà sa configuration : modifiez-la plutôt.")
    brut = copy.deepcopy(CONFIGURATION_DE_DEPART)
    for colonne in brut["colonnes"]:
        if colonne["cle"] in NOYAU_CANONIQUE:
            colonne["canonique"] = True
    # Le nom n'est jamais affiché (une instance = une maison, 0171) ; il nomme le fichier.
    brut["maison"] = os.environ.get("CAVE_SCAN_MAISON", "").strip() or "Maison de vente"
    return importer(session, dossier_configs, json.dumps(brut, ensure_ascii=False), "configuration de départ")


def config_de_l_instance(dossier_configs: Path) -> ConfigActive | None:
    maison = maison_de_l_instance(dossier_configs)
    return config_active(dossier_configs, maison) if maison else None


def versions_de(session: Session, maison: str) -> list[ConfigVersion]:
    """Les versions enregistrées en base, la plus récente d'abord."""
    return list(
        session.scalars(
            select(ConfigVersion)
            .join(Maison, Maison.id == ConfigVersion.maison_id)
            .where(Maison.nom == maison)
            .order_by(ConfigVersion.numero.desc())
        )
    )


def apercu_modele(colonne: Colonne) -> str | None:
    """Ce que le modèle reçoit pour cette colonne, tel quel (le morceau du schéma
    qui la décrit) ; None si elle ne lui est jamais envoyée (expert, système)."""
    if not colonne.envoyee_au_modele:
        return None
    return json.dumps(propriete_modele(colonne), ensure_ascii=False, indent=2)


# --- écrire --------------------------------------------------------------------------------


def enregistrer_version(
    session: Session,
    dossier_configs: Path,
    maison: str,
    brut: dict[str, Any],
    version_vue: int | None = None,
) -> VersionEnregistree:
    """Le contenu édité dans la page devient la nouvelle version de la maison.

    `version_vue` : la version active quand la page a été ouverte ; si elle a
    changé depuis, rien n'est écrit (`ConfigModifieeAilleurs`). Le nom de la
    maison ne change pas ici : ce serait une autre maison.
    """
    with _VERROU:
        active = config_active(dossier_configs, maison)
        if version_vue is not None and version_vue != active.config.version:
            raise ConfigModifieeAilleurs(
                f"La configuration a été modifiée ailleurs depuis "
                f"que vous l'avez ouverte (version {active.config.version}, vous éditiez la version "
                f"{version_vue}). Rechargez la page pour repartir de la version actuelle."
            )
        brut = dict(brut)
        if plier(str(brut.get("maison", ""))) != plier(active.config.maison):
            raise ConfigInvalide(
                "Cette page ne modifie que la configuration de l'application : rechargez-la."
            )
        brut["maison"] = active.config.maison
        return _ecrire(session, active.fichier, brut, active, nouvelle_maison=False)


def importer(session: Session, dossier_configs: Path, texte: str, nom_fichier: str = "") -> VersionEnregistree:
    """Un fichier JSON apporté par la maison devient sa config active.

    Maison déjà connue : nouvelle version de SON fichier, numérotée par l'outil
    (la précédente + 1). Maison nouvelle : un nouveau fichier, nommé d'après
    elle. Dans les deux cas, validé comme n'importe quel fichier.
    """
    source = nom_fichier or "fichier importé"
    try:
        brut = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise ConfigInvalide(
            f"{source} : JSON illisible — le fichier est incomplet ou abîmé (ligne {erreur.lineno}, "
            f"colonne {erreur.colno})."
        ) from erreur
    except ValueError:  # un nombre de plus de 4 300 chiffres (T5-B4)
        raise ConfigInvalide(f"{source} : un nombre du fichier est démesuré (plus de 4 300 chiffres).") from None
    if not isinstance(brut, dict) or not isinstance(brut.get("maison"), str) or not brut["maison"].strip():
        # Toutes les autres erreurs, la validation complète les listera.
        config_depuis_texte(texte, source)
        raise ConfigInvalide(f"{source} : « maison » manquant ou vide.")

    with _VERROU:
        try:
            active = config_active(dossier_configs, brut["maison"])
        except LookupError:
            active = None
        if active is not None:
            brut["maison"] = active.config.maison
            return _ecrire(session, active.fichier, brut, active, nouvelle_maison=False)
        fichier = _fichier_libre(Path(dossier_configs), brut["maison"])
        return _ecrire(session, fichier, brut, None, nouvelle_maison=True)


def exporter_version(
    session: Session, dossier_configs: Path, maison: str, numero: int | None = None
) -> tuple[str, str]:
    """(nom de fichier, texte JSON) : la config active, ou la version `numero`
    enregistrée en base."""
    active = config_active(dossier_configs, maison)
    if numero is None:
        return active.fichier.name, active.texte
    version = next((v for v in versions_de(session, active.config.maison) if v.numero == numero), None)
    if version is None:
        raise ConfigIntrouvable(f"Aucune version n°{numero} de la configuration.")
    return f"{active.fichier.stem}_version_{numero}.json", version.contenu


def _ecrire(
    session: Session, fichier: Path, brut: dict[str, Any], active: ConfigActive | None, nouvelle_maison: bool
) -> VersionEnregistree:
    avertissements = []
    if active is not None:
        version = active.config.version + 1
        declaree = brut.get("version")
        if declaree not in (None, active.config.version, version):
            avertissements.append(
                f"Numéro de version fixé à {version} (le fichier indiquait {declaree!r}) : "
                f"chaque version suit la précédente."
            )
        brut["version"] = active.config.version
        if empreinte_config(_texte(brut)) == empreinte_config(active.texte):
            raise ConfigInchangee("Aucun changement par rapport à la version active : rien n'a été enregistré.")
    else:
        version = brut.get("version") if isinstance(brut.get("version"), int) and brut["version"] >= 1 else 1
    brut["version"] = version
    texte = _texte(brut)
    config = config_depuis_texte(texte, fichier.name)  # validation complète, comme un fichier

    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_name(f".{fichier.name}.en-cours")
    temporaire.write_text(texte, encoding="utf-8", newline="\n")
    os.replace(temporaire, fichier)

    enregistree, _nouvelle, autres = _version_de_config(
        session, _maison(session, config.maison), config, texte, fichier.name
    )
    session.commit()
    return VersionEnregistree(
        maison=config.maison,
        fichier=fichier,
        version=config.version,
        numero=enregistree.numero,
        nouvelle_maison=nouvelle_maison,
        avertissements=[*avertissements, *config.avertissements, *autres],
    )


def _texte(brut: dict[str, Any]) -> str:
    return json.dumps(brut, ensure_ascii=False, indent=2) + "\n"


def _fichier_libre(dossier: Path, maison: str) -> Path:
    """« Cave Dupont & Fils » -> cave_dupont_fils.json (ou _2, _3… s'il existe)."""
    base = re.sub(r"[^a-z0-9]+", "_", plier(maison)).strip("_") or "maison"
    candidat, rang = dossier / f"{base}.json", 2
    while candidat.exists():
        candidat, rang = dossier / f"{base}_{rang}.json", rang + 1
    return candidat


# --- édition dans la page ----------------------------------------------------------------
#
# La page envoie TOUTE la config à chaque action (ajouter, déplacer, supprimer,
# vérifier, enregistrer) : le serveur la relit, applique l'action et la
# réaffiche. Rien n'est gardé entre deux demandes ; rien n'est écrit avant
# « Enregistrer ».

TYPES_EDITABLES = ("texte", "liste", "nombre")
SOURCES_EDITABLES = ("modele", "modele_best_effort", "expert", "systeme")


def config_du_fichier(dossier_configs: Path, nom: str) -> ConfigActive:
    """La config active désignée par le nom de son fichier (sans « .json ») :
    l'adresse de la page reste lisible, sans accents ni espaces."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", nom or ""):
        raise ConfigIntrouvable(f"Aucune configuration « {nom} ».")
    fichier = Path(dossier_configs) / f"{Path(nom).stem}.json"
    if not fichier.is_file():
        raise ConfigIntrouvable(f"Aucune configuration « {nom} ».")
    config, texte = lire_config(fichier)
    return ConfigActive(fichier=fichier, texte=texte, config=config)


def brut_depuis_formulaire(champs: dict[str, str]) -> dict[str, Any]:
    """La config telle que la page l'affiche, relue champ par champ.

    Noms des champs : `c{i}_nom`, `c{i}_v{j}_libelle`… ; `nb_colonnes` et
    `c{i}_nb_valeurs` disent combien il y en a. Les commentaires (`_…`) de la
    config voyagent tels quels dans un champ caché.
    """

    def texte(nom: str) -> str:
        return (champs.get(nom) or "").strip()

    def nombre(valeur: str) -> bool:
        # Au plus 6 chiffres : au-delà, une saisie absurde que Python refuserait
        # même de convertir (plus de 4 300 chiffres, T5-B4).
        return valeur.isascii() and valeur.isdigit() and len(valeur) <= 6

    def entier(nom: str, defaut: int = 0) -> int:
        valeur = texte(nom)
        return int(valeur) if nombre(valeur) else defaut

    brut: dict[str, Any] = dict(_commentaires(champs.get("commentaires")))
    brut["maison"] = texte("maison")
    brut["version"] = entier("version_vue", 1)
    brut["langue"] = texte("langue") or "fr"
    plafond = texte("photos_max_par_bouteille")
    # Une saisie qui n'est pas un nombre est gardée telle quelle : la validation
    # dira pourquoi elle est refusée, au lieu de la remplacer en silence.
    brut["photos_max_par_bouteille"] = int(plafond) if nombre(plafond) else plafond

    colonnes, regroupement = [], []
    for i in range(entier("nb_colonnes")):
        colonne: dict[str, Any] = dict(_commentaires(champs.get(f"c{i}_commentaires")))
        nom = texte(f"c{i}_nom")
        cle = texte(f"c{i}_cle") or _identifiant(nom)
        colonne.update(cle=cle, nom=nom, type=texte(f"c{i}_type"), source=texte(f"c{i}_source"))
        for champ in ("description", "regle"):
            if texte(f"c{i}_{champ}"):
                colonne[champ] = texte(f"c{i}_{champ}")
        if cle in NOYAU_CANONIQUE:
            colonne["canonique"] = True  # posé par l'outil, jamais à la main (0021)
        if colonne["type"] == "liste":
            valeurs = []
            for j in range(entier(f"c{i}_nb_valeurs")):
                libelle = texte(f"c{i}_v{j}_libelle")
                code = texte(f"c{i}_v{j}_code") or _identifiant(libelle)
                if not (code or libelle):
                    continue  # ligne laissée vide
                valeur = {"code": code, "libelle": libelle}
                if texte(f"c{i}_v{j}_description"):
                    valeur["description"] = texte(f"c{i}_v{j}_description")
                valeurs.append(valeur)
            colonne["valeurs"] = valeurs
        if champs.get(f"c{i}_regrouper"):
            regroupement.append(cle)
        colonnes.append(colonne)
    brut["regroupement_export"] = regroupement
    brut["colonnes"] = colonnes
    # Les consignes : gardées seulement si elles diffèrent de celles d'origine.
    consignes = (champs.get("consignes") or "").replace("\r\n", "\n").strip()
    if consignes and consignes != CONSIGNES_MODIFIABLES.strip():
        brut["consignes"] = consignes
    return brut


def consignes_modifiees(active: ConfigActive, brut: dict[str, Any]) -> bool:
    """Les consignes envoyées au modèle changeraient-elles en enregistrant `brut` ?"""
    avant = active.config.consignes or CONSIGNES_MODIFIABLES.strip()
    apres = brut.get("consignes") or CONSIGNES_MODIFIABLES.strip()
    return avant.strip() != apres.strip()


def appliquer(brut: dict[str, Any], action: str) -> dict[str, Any]:
    """Les actions de la page qui changent la STRUCTURE, sans rien enregistrer :
    `ajouter_colonne`, `monter-3`, `descendre-3`, `supprimer-3`,
    `ajouter_valeur-3`, `supprimer_valeur-3-1`. Une action inconnue ne change
    rien."""
    brut = json.loads(json.dumps(brut))  # copie : la page reçoit un nouvel état
    colonnes = brut["colonnes"]
    nom, *arguments = (action or "").split("-")
    try:
        index = [int(argument) for argument in arguments]
    except ValueError:
        return brut

    def existe(i: int) -> bool:
        return 0 <= i < len(colonnes)

    if nom == "ajouter_colonne":
        # Avant les colonnes calculées qui ferment l'Excel (« À vérifier »…) (T4-B22).
        fin = len(colonnes)
        while fin > 0 and colonnes[fin - 1].get("source") == "systeme" and colonnes[fin - 1].get("cle") != "id":
            fin -= 1
        colonnes.insert(fin, {"cle": "", "nom": "", "type": "texte", "source": "expert"})
    elif nom in ("monter", "descendre") and len(index) == 1 and existe(index[0]):
        i = index[0]
        j = i - 1 if nom == "monter" else i + 1
        if existe(j):
            colonnes[i], colonnes[j] = colonnes[j], colonnes[i]
    elif nom == "supprimer" and len(index) == 1 and existe(index[0]):
        cle = colonnes.pop(index[0]).get("cle")
        brut["regroupement_export"] = [c for c in brut.get("regroupement_export", []) if c != cle]
    elif nom == "ajouter_valeur" and len(index) == 1 and existe(index[0]):
        colonne = colonnes[index[0]]
        colonne["type"] = "liste"
        colonne.setdefault("valeurs", []).append({"code": "", "libelle": ""})
    elif nom == "supprimer_valeur" and len(index) == 2 and existe(index[0]):
        valeurs = colonnes[index[0]].get("valeurs", [])
        if 0 <= index[1] < len(valeurs):
            valeurs.pop(index[1])
    return brut


@dataclass(frozen=True)
class ColonneEditee:
    """Une colonne telle que la page la montre."""

    index: int
    donnees: dict[str, Any]
    nouvelle: bool  # absente de la version active : sa clé se choisit encore
    codes_existants: tuple[str, ...]  # codes de la version active : stables, jamais modifiés
    envoyee: bool  # lue par le modèle (modele, best effort)
    apercu: str | None  # ce que le modèle reçoit ; None si la colonne n'est pas encore valide
    regroupee: bool
    en_erreur: bool = False  # citée par un refus : encadrée à l'écran


@dataclass(frozen=True)
class Edition:
    """L'état de la page Configuration."""

    active: ConfigActive
    brut: dict[str, Any]
    colonnes: list[ColonneEditee]
    commentaires: str  # les clés « _… » de la racine, en JSON, renvoyées telles quelles
    erreurs: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    verifiee: bool = False  # la validation complète a été faite


def edition(active: ConfigActive, brut: dict[str, Any] | None = None, verifier: bool = False) -> Edition:
    """Ce que la page affiche : la config (active, ou en cours d'édition), avec
    l'aperçu de chaque colonne et, si demandé, le résultat de la validation."""
    brut = active.brut if brut is None else brut
    anciennes = {colonne.cle: colonne for colonne in active.config.colonnes}
    regroupees = set(brut.get("regroupement_export") or [])
    colonnes = []
    for index, donnees in enumerate(brut.get("colonnes") or []):
        cle = donnees.get("cle", "")
        valide = colonne_depuis_brut(donnees)
        colonnes.append(
            ColonneEditee(
                index=index,
                donnees=donnees,
                nouvelle=cle not in anciennes,
                codes_existants=tuple(c for c in anciennes[cle].codes if c != "non_determinable")
                if cle in anciennes
                else (),
                envoyee=donnees.get("source") in SOURCES_MODELE,
                apercu=apercu_modele(valide) if valide is not None else None,
                regroupee=cle in regroupees,
            )
        )
    erreurs: list[str] = []
    avertissements: list[str] = []
    if verifier:
        candidat = dict(brut, version=active.config.version + 1)
        try:
            avertissements = list(config_depuis_texte(_texte(candidat), active.fichier.name).avertissements)
        except ConfigInvalide as refus:
            erreurs = refus.erreurs
    if erreurs:
        erreurs, fautives = _en_clair(erreurs, brut.get("colonnes") or [])
        colonnes = [replace(c, en_erreur=c.index in fautives) for c in colonnes]
    commentaires = {cle: valeur for cle, valeur in brut.items() if cle.startswith("_")}
    return Edition(
        active=active,
        brut=brut,
        colonnes=colonnes,
        commentaires=json.dumps(commentaires, ensure_ascii=False),
        erreurs=erreurs,
        avertissements=avertissements,
        verifiee=verifier,
    )


def _en_clair(erreurs: list[str], colonnes: list[dict[str, Any]]) -> tuple[list[str], set[int]]:
    """Les refus de la validation, dits pour la page (rapport du testeur, T1-M4) :
    chaque colonne par son nom d'en-tête, pas par sa clé ; une colonne sans nom
    n'a qu'un message (sa clé découle du nom). Renvoie aussi les index des
    colonnes citées, pour les encadrer."""
    fautives: set[int] = set()
    en_clair: list[str] = []
    for erreur in erreurs:
        index = None
        for i, donnees in enumerate(colonnes):
            cle, nom = donnees.get("cle") or "", donnees.get("nom") or ""
            if erreur.startswith(f"colonne n°{i + 1} ") or erreur.startswith(f"colonne n°{i + 1}:") or (
                cle and erreur.startswith(f"colonne « {cle} »")
            ):
                index = i
                if not nom:
                    if "« cle »" in erreur:
                        erreur = ""  # découle du nom : un seul message suffit
                    elif "« nom »" in erreur:
                        erreur = f"La colonne n°{i + 1} n'a pas de nom : donnez-lui un nom (l'en-tête de l'Excel) ou retirez-la."
                elif cle:
                    erreur = erreur.replace(f"colonne « {cle} »", f"Colonne « {nom} »", 1)
                break
        if index is not None:
            fautives.add(index)
        if erreur:
            erreur = erreur.replace("« cle »", "« clé »").replace("« libelle »", "« libellé »")
            en_clair.append(erreur)
    return en_clair, fautives


def commentaires_de_colonne(donnees: dict[str, Any]) -> str:
    """Les clés « _… » d'une colonne, en JSON, pour les renvoyer telles quelles."""
    return json.dumps({c: v for c, v in donnees.items() if c.startswith("_")}, ensure_ascii=False)


def _identifiant(libelle: str) -> str:
    """« État de la capsule » -> etat_de_la_capsule (clé ou code d'une nouveauté)."""
    identifiant = re.sub(r"[^a-z0-9]+", "_", plier(libelle)).strip("_")
    if identifiant and not identifiant[0].isalpha():
        identifiant = f"c_{identifiant}"
    return identifiant


def _commentaires(texte: str | None) -> dict[str, Any]:
    try:
        valeur = json.loads(texte or "{}")
    except json.JSONDecodeError:
        return {}
    return {c: v for c, v in valeur.items() if c.startswith("_")} if isinstance(valeur, dict) else {}
