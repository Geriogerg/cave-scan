"""Config de format d'une maison de vente : chargée et validée au démarrage.

Une maison = un fichier JSON dans `config/maisons/`. Il décrit les colonnes de
l'export (clé, en-tête, type, source, valeurs possibles), et pilote du même
coup ce qui est demandé au modèle (decisions.md 0020). Changer de maison ou de
nomenclature, c'est modifier ce fichier, jamais le code.

Validation STRICTE (decisions.md 0052) : une config mal écrite ne doit jamais
produire un export plausible et faux. Toutes les anomalies sont rassemblées
dans une seule `ConfigInvalide`, chacune dit quoi corriger et où.

Ce module ne contient aucune valeur propre à une maison : seulement la forme du
fichier, et les noms que le pipeline sait servir (noyau canonique, colonnes
système, quantité).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.extract.schema import NATURE_DES_CHAMPS, NON_DETERMINABLE

TYPES = ("texte", "liste", "nombre")
SOURCES = ("modele", "modele_best_effort", "expert", "systeme")
SOURCES_MODELE = ("modele", "modele_best_effort")

# Noyau canonique (decisions.md 0021) : extrait pour toutes les maisons, même
# si une config ne l'affiche pas.
NOYAU_CANONIQUE = ("domaine", "appellation", "millesime", "format")

# Colonnes que l'outil sait calculer lui-même (source « systeme ») : une
# colonne système inconnue serait une colonne vide sans explication.
COLONNES_SYSTEME = ("id", "a_verifier")

# Seule colonne expert que le pipeline connaît : elle porte une valeur par
# défaut (1) et s'additionne au regroupement (decisions.md 0017).
COLONNE_QUANTITE = "quantite"

# Noms qu'aucune colonne modèle ne peut prendre : métadonnées du pipeline, ou
# champs dont le modèle ne doit jamais décider.
CLES_RESERVEES_AU_PIPELINE = (
    "id",
    "quantite",
    "a_verifier",
    "champs_a_verifier",
    "couleur_source",
    "valeurs_maison",
    "photos_meme_bouteille",
)

# Valeur ajoutée d'office à chaque liste, sans être écrite dans le fichier.
LIBELLE_NON_DETERMINABLE = "Non déterminable"
DESCRIPTION_NON_DETERMINABLE = (
    "Rien de ce qui est visible sur les photos ne permet de trancher."
)

CLES_RACINE = ("maison", "version", "langue", "regroupement_export", "colonnes")
CLES_COLONNE = (
    "cle", "nom", "type", "source", "description", "regle", "canonique", "valeurs",
)
CLES_VALEUR = ("code", "libelle", "description")

MOTIF_CLE = re.compile(r"^[a-z][a-z0-9_]*$")
MOTIF_CODE = re.compile(r"^[a-z0-9][a-z0-9_]*$")

# Ce qui ressemble à un exemple de réponse dans un texte envoyé au modèle :
# une citation, ou une annonce d'exemple. C'est du few-shot (decisions.md
# 0053) — signalé, pas bloqué : la config appartient à la maison.
MOTIFS_EXEMPLE = (
    re.compile(r"«[^»]{3,}»"),
    re.compile(r'"[^"]{3,}"'),
    re.compile(r"\b(ex\.|exemple|e\.g\.)", re.IGNORECASE),
)


class ConfigInvalide(ValueError):
    """La config ne respecte pas le format attendu. Le message liste tout."""


@dataclass(frozen=True)
class Valeur:
    """Une valeur possible d'une colonne de type liste."""

    code: str  # stable : stocké, comparé, jamais modifié
    libelle: str  # affiché à l'export, modifiable librement
    description: str = ""  # guide le modèle


@dataclass(frozen=True)
class Colonne:
    """Une colonne de l'export, et ce que le pipeline doit en faire."""

    cle: str
    nom: str
    type: str
    source: str
    description: str = ""
    regle: str = ""
    canonique: bool = False
    valeurs: tuple[Valeur, ...] = ()

    @property
    def envoyee_au_modele(self) -> bool:
        """Les colonnes expert et système ne sont JAMAIS envoyées au modèle."""
        return self.source in SOURCES_MODELE

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(valeur.code for valeur in self.valeurs)

    def libelle(self, code: Any) -> str | None:
        """Libellé affiché d'un code, ou None s'il n'appartient pas à la liste."""
        for valeur in self.valeurs:
            if valeur.code == code:
                return valeur.libelle
        return None

    def code_depuis(self, texte: Any) -> str | None:
        """Retrouve le code d'un texte qui est soit un code, soit un libellé.

        Insensible à la casse et aux accents : « rosé », « Rosé » et « rose »
        désignent la même valeur. Ce n'est pas de la normalisation — on décode
        le vocabulaire de la maison avec le dictionnaire qu'elle a fourni.
        """
        if texte is None:
            return None
        cible = plier(texte)
        if not cible:
            return None
        for valeur in self.valeurs:
            if cible in (plier(valeur.code), plier(valeur.libelle)):
                return valeur.code
        return None


@dataclass(frozen=True)
class ConfigMaison:
    """Config d'une maison, validée. Pures données."""

    chemin: Path
    maison: str
    version: int
    langue: str
    colonnes: tuple[Colonne, ...]
    regroupement_export: tuple[str, ...] = ()
    avertissements: tuple[str, ...] = ()

    def colonne(self, cle: str) -> Colonne | None:
        return next((c for c in self.colonnes if c.cle == cle), None)

    @property
    def colonnes_modele(self) -> tuple[Colonne, ...]:
        """Colonnes envoyées au modèle, dans l'ordre du fichier."""
        return tuple(c for c in self.colonnes if c.envoyee_au_modele)

    @property
    def colonnes_best_effort(self) -> tuple[Colonne, ...]:
        return tuple(c for c in self.colonnes if c.source == "modele_best_effort")


def plier(texte: Any) -> str:
    """Forme comparable d'un libellé : sans casse, sans accents, espaces réduits."""
    decompose = unicodedata.normalize("NFKD", str(texte).strip())
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans_accents.casefold().split())


def charger_config(chemin: str | Path) -> ConfigMaison:
    """Charge et valide la config d'une maison. Lève `ConfigInvalide` sinon."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"Config maison introuvable : {chemin}")

    try:
        brut = json.loads(
            chemin.read_text(encoding="utf-8"), object_pairs_hook=_refuser_doublons
        )
    except json.JSONDecodeError as erreur:
        raise ConfigInvalide(
            f"{chemin} : JSON illisible, ligne {erreur.lineno} colonne "
            f"{erreur.colno} : {erreur.msg}."
        ) from erreur
    except _CleEnDouble as erreur:
        raise ConfigInvalide(f"{chemin} : {erreur}") from None

    return _valider(brut, chemin)


class _CleEnDouble(Exception):
    pass


def _refuser_doublons(paires: list[tuple[str, Any]]) -> dict[str, Any]:
    """`json` garde silencieusement la DERNIÈRE occurrence d'une clé en double.

    Sans ce crochet, « clés uniques » ne serait jamais vérifié : une colonne
    dont le `nom` est écrit deux fois prendrait la seconde valeur sans que
    personne ne le sache.
    """
    objet: dict[str, Any] = {}
    for cle, valeur in paires:
        if cle in objet:
            ou = dict(paires).get("cle")
            contexte = f" dans la colonne « {ou} »" if isinstance(ou, str) else ""
            raise _CleEnDouble(f"clé « {cle} » en double{contexte}.")
        objet[cle] = valeur
    return objet


def _valider(brut: Any, chemin: Path) -> ConfigMaison:
    erreurs: list[str] = []

    if not isinstance(brut, dict):
        raise ConfigInvalide(f"{chemin} : un objet JSON est attendu à la racine.")

    _cles_inconnues(brut, CLES_RACINE, "la racine", erreurs)

    maison = brut.get("maison")
    if not isinstance(maison, str) or not maison.strip():
        erreurs.append("« maison » : nom de la maison manquant ou vide.")

    version = brut.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        erreurs.append(
            f"« version » : entier ≥ 1 attendu (reçu {version!r}). Elle est "
            f"copiée dans chaque export pour savoir quelle config l'a produit."
        )

    langue = brut.get("langue", "fr")
    if not isinstance(langue, str):
        erreurs.append(f"« langue » : texte attendu (reçu {langue!r}).")

    colonnes_brutes = brut.get("colonnes")
    colonnes: list[Colonne] = []
    if not isinstance(colonnes_brutes, list) or not colonnes_brutes:
        erreurs.append("« colonnes » : liste non vide attendue.")
    else:
        for index, entree in enumerate(colonnes_brutes):
            colonne = _valider_colonne(entree, index, erreurs)
            if colonne is not None:
                colonnes.append(colonne)

    _verifier_unicite(colonnes, erreurs)
    # Clés déclarées, valides ou non : une colonne déjà signalée invalide ne doit
    # pas produire en plus « aucune colonne de clé X » dans le regroupement.
    cles_declarees = {
        entree.get("cle")
        for entree in (colonnes_brutes if isinstance(colonnes_brutes, list) else [])
        if isinstance(entree, dict)
    }
    regroupement = _valider_regroupement(
        brut.get("regroupement_export", []), colonnes, cles_declarees, erreurs
    )

    if erreurs:
        liste = "\n".join(f"  - {erreur}" for erreur in erreurs)
        raise ConfigInvalide(f"{chemin} : config invalide ({len(erreurs)}) :\n{liste}")

    return ConfigMaison(
        chemin=chemin,
        maison=maison.strip(),
        version=version,
        langue=langue,
        colonnes=tuple(colonnes),
        regroupement_export=regroupement,
        avertissements=tuple(_reperer_exemples(colonnes)),
    )


def _cles_inconnues(objet: dict[str, Any], connues: tuple[str, ...], ou: str, erreurs: list[str]) -> None:
    """Une clé inconnue est presque toujours une faute de frappe. Les clés
    préfixées par « _ » sont des commentaires et sont ignorées."""
    for cle in objet:
        if not cle.startswith("_") and cle not in connues:
            erreurs.append(
                f"{ou} : clé inconnue « {cle} » (clés possibles : {', '.join(connues)} ; "
                f"préfixer par « _ » pour un commentaire)."
            )


def _valider_colonne(entree: Any, index: int, erreurs: list[str]) -> Colonne | None:
    if not isinstance(entree, dict):
        erreurs.append(f"colonne n°{index + 1} : objet attendu.")
        return None

    cle = entree.get("cle")
    ou = f"colonne « {cle} »" if isinstance(cle, str) and cle else f"colonne n°{index + 1}"
    nb_erreurs = len(erreurs)

    _cles_inconnues(entree, CLES_COLONNE, ou, erreurs)

    if not isinstance(cle, str) or not MOTIF_CLE.match(cle):
        erreurs.append(
            f"{ou} : « cle » doit être un identifiant en minuscules "
            f"(lettres, chiffres, _), reçu {cle!r}."
        )
    nom = entree.get("nom")
    if not isinstance(nom, str) or not nom.strip():
        erreurs.append(f"{ou} : « nom » (en-tête de colonne) manquant ou vide.")
    type_ = entree.get("type")
    if type_ not in TYPES:
        erreurs.append(f"{ou} : type {type_!r} inconnu (types connus : {', '.join(TYPES)}).")
    source = entree.get("source")
    if source not in SOURCES:
        erreurs.append(f"{ou} : source {source!r} inconnue (sources connues : {', '.join(SOURCES)}).")

    description = entree.get("description", "")
    regle = entree.get("regle", "")
    canonique = entree.get("canonique", False)
    for champ, valeur in (("description", description), ("regle", regle)):
        if not isinstance(valeur, str):
            erreurs.append(f"{ou} : « {champ} » doit être un texte.")
    if not isinstance(canonique, bool):
        erreurs.append(f"{ou} : « canonique » doit valoir true ou false.")

    valeurs = _valider_valeurs(entree.get("valeurs"), type_, ou, erreurs)

    if len(erreurs) > nb_erreurs:
        return None  # forme invalide : inutile de contrôler la cohérence

    colonne = Colonne(
        cle=cle,
        nom=nom.strip(),
        type=type_,
        source=source,
        description=description.strip(),
        regle=regle.strip(),
        canonique=canonique,
        valeurs=valeurs,
    )
    _verifier_coherence(colonne, ou, erreurs)
    return colonne


def _valider_valeurs(brutes: Any, type_: Any, ou: str, erreurs: list[str]) -> tuple[Valeur, ...]:
    if type_ != "liste":
        if brutes is not None:
            erreurs.append(f"{ou} : « valeurs » n'a de sens que pour le type liste.")
        return ()

    if not isinstance(brutes, list) or not brutes:
        erreurs.append(f"{ou} : une colonne de type liste exige « valeurs » (liste non vide).")
        return ()

    valeurs: list[Valeur] = []
    codes_vus: set[str] = set()
    libelles_vus: set[str] = set()
    for rang, brute in enumerate(brutes, start=1):
        if not isinstance(brute, dict):
            erreurs.append(f"{ou}, valeur n°{rang} : objet attendu.")
            continue
        _cles_inconnues(brute, CLES_VALEUR, f"{ou}, valeur n°{rang}", erreurs)
        code, libelle = brute.get("code"), brute.get("libelle")
        description = brute.get("description", "")

        if not isinstance(code, str) or not MOTIF_CODE.match(code):
            erreurs.append(f"{ou}, valeur n°{rang} : « code » doit être en minuscules (lettres, chiffres, _), reçu {code!r}.")
            continue
        if not isinstance(libelle, str) or not libelle.strip():
            erreurs.append(f"{ou}, valeur « {code} » : « libelle » manquant ou vide.")
            continue
        if not isinstance(description, str):
            erreurs.append(f"{ou}, valeur « {code} » : « description » doit être un texte.")
            continue
        if code == NON_DETERMINABLE or plier(libelle) == plier(LIBELLE_NON_DETERMINABLE):
            erreurs.append(
                f"{ou}, valeur « {code} » : « {LIBELLE_NON_DETERMINABLE} » est ajoutée "
                f"d'office à chaque liste, ne pas l'écrire dans le fichier."
            )
            continue
        if code in codes_vus:
            erreurs.append(f"{ou} : code « {code} » en double.")
            continue
        if plier(libelle) in libelles_vus:
            erreurs.append(
                f"{ou} : libellé « {libelle} » en double (à la casse ou aux accents "
                f"près, il serait impossible à relire dans le fichier de l'expert)."
            )
            continue
        codes_vus.add(code)
        libelles_vus.add(plier(libelle))
        valeurs.append(Valeur(code=code, libelle=libelle.strip(), description=description.strip()))

    # Ajoutée d'office, jamais écrite dans le fichier (guide, étape 4.1).
    valeurs.append(
        Valeur(
            code=NON_DETERMINABLE,
            libelle=LIBELLE_NON_DETERMINABLE,
            description=DESCRIPTION_NON_DETERMINABLE,
        )
    )
    return tuple(valeurs)


def _verifier_coherence(colonne: Colonne, ou: str, erreurs: list[str]) -> None:
    """Ce que la colonne prétend doit être ce que le pipeline sait faire."""
    cle, source = colonne.cle, colonne.source

    if source == "systeme" and cle not in COLONNES_SYSTEME:
        erreurs.append(
            f"{ou} : l'outil ne sait pas calculer cette colonne système "
            f"(colonnes système connues : {', '.join(COLONNES_SYSTEME)})."
        )
    if cle in COLONNES_SYSTEME and source != "systeme":
        erreurs.append(f"{ou} : cette colonne est calculée par l'outil, sa source doit être « systeme ».")

    if cle == COLONNE_QUANTITE and (source != "expert" or colonne.type != "nombre"):
        erreurs.append(f"{ou} : la quantité est saisie par l'expert (source « expert », type « nombre ») — decisions.md 0017.")

    if colonne.envoyee_au_modele:
        if cle in CLES_RESERVEES_AU_PIPELINE:
            erreurs.append(f"{ou} : « {cle} » est réservé au pipeline, le modèle ne peut pas le remplir.")
        nature = NATURE_DES_CHAMPS.get(cle)
        if nature is not None and nature != colonne.type:
            erreurs.append(
                f"{ou} : « {cle} » est un champ {nature} du contrat Bouteille, la "
                f"config ne peut pas en faire un champ {colonne.type}."
            )
    elif source == "expert" and cle in NATURE_DES_CHAMPS:
        erreurs.append(
            f"{ou} : « {cle} » est extrait par le modèle ; une colonne expert du même "
            f"nom rendrait ambigu qui remplit quoi."
        )

    if colonne.canonique and cle not in NOYAU_CANONIQUE:
        erreurs.append(
            f"{ou} : seuls {', '.join(NOYAU_CANONIQUE)} forment le noyau canonique "
            f"(decisions.md 0021)."
        )
    if cle in NOYAU_CANONIQUE:
        if not colonne.canonique:
            erreurs.append(f"{ou} : champ du noyau canonique (decisions.md 0021), ajouter \"canonique\": true.")
        if not colonne.envoyee_au_modele:
            erreurs.append(f"{ou} : le noyau canonique est toujours extrait par le modèle, source « modele » ou « modele_best_effort » attendue.")


def _verifier_unicite(colonnes: list[Colonne], erreurs: list[str]) -> None:
    cles_vues: set[str] = set()
    noms_vus: dict[str, str] = {}
    for colonne in colonnes:
        if colonne.cle in cles_vues:
            erreurs.append(f"colonne « {colonne.cle} » : clé en double.")
        cles_vues.add(colonne.cle)

        nom = plier(colonne.nom)
        if nom in noms_vus:
            erreurs.append(
                f"colonnes « {noms_vus[nom]} » et « {colonne.cle} » : même en-tête "
                f"« {colonne.nom} » — impossible de relire le fichier de l'expert."
            )
        noms_vus.setdefault(nom, colonne.cle)


def _valider_regroupement(
    brut: Any, colonnes: list[Colonne], cles_declarees: set[Any], erreurs: list[str]
) -> tuple[str, ...]:
    if not isinstance(brut, list) or not all(isinstance(cle, str) for cle in brut):
        erreurs.append("« regroupement_export » : liste de clés de colonnes attendue.")
        return ()

    par_cle = {colonne.cle: colonne for colonne in colonnes}
    vus: set[str] = set()
    for cle in brut:
        colonne = par_cle.get(cle)
        if cle in vus:
            erreurs.append(f"« regroupement_export » : « {cle} » en double.")
        elif colonne is None:
            if cle not in cles_declarees:  # sinon déjà signalée comme invalide
                erreurs.append(f"« regroupement_export » : aucune colonne de clé « {cle} ».")
        elif not colonne.envoyee_au_modele:
            erreurs.append(
                f"« regroupement_export » : « {cle} » n'est pas une colonne lue sur la "
                f"bouteille — on ne regroupe que sur ce que le modèle extrait."
            )
        vus.add(cle)
    return tuple(brut)


def _reperer_exemples(colonnes: list[Colonne]) -> list[str]:
    """Textes envoyés au modèle qui contiennent un exemple de réponse."""
    avertissements: list[str] = []
    for colonne in colonnes:
        if not colonne.envoyee_au_modele:
            continue  # jamais envoyée : aucun risque de few-shot
        textes = [("description", colonne.description), ("regle", colonne.regle)]
        textes += [(f"valeur « {v.code} »", v.description) for v in colonne.valeurs]
        for ou, texte in textes:
            for motif in MOTIFS_EXEMPLE:
                trouve = motif.search(texte)
                if trouve:
                    avertissements.append(
                        f"colonne « {colonne.cle} », {ou} : contient ce qui ressemble "
                        f"à un exemple de réponse ({trouve.group(0)}). C'est du "
                        f"few-shot (CLAUDE.md : on mesure le zero-shot) — à retirer "
                        f"de la config si ce n'est pas voulu."
                    )
                    break
    return avertissements
