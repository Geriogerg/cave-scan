"""Extraction par Gemini (Google), en sortie JSON contrainte par schéma.

Backend GRATUIT du projet. Il implémente le même `Protocol Extractor` et reçoit
les mêmes consignes que l'extracteur Anthropic (`src/extract/consignes.py`) :
seul le fournisseur change, pas ce qu'on demande au modèle.

Deux différences de fond avec le backend payant, à connaître avant de lire un
score produit ici (decisions.md 0050) :

- Le palier gratuit est **Flash uniquement**. Le chiffre qui décidera de la
  suite du projet mérite d'être rejoué sur un modèle de tête : un plancher
  mesuré avec un petit modèle sous-estime ce que la technologie sait faire.
- Google peut exploiter les entrées et sorties du palier gratuit. Pour des
  photos de bouteilles confiées par une maison de vente, c'est un point à
  trancher avec elle avant tout usage réel.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

import httpx
from google import genai
from google.genai import errors, types

from src.extract.base import (
    Limiteur,
    PhotosDUneBouteille,
    SortieModele,
    bouteille_depuis_sortie,
    liste_de_photos,
)
from src.extract.consignes import (
    INSTRUCTION_FINALE,
    LIBELLE_PHOTO,
    SYSTEM_PROMPT,
    consignes_systeme,
    LimitesEnvoi,
    preparer_photos,
    version_prompt,
)
from src.extract.schema import Bouteille, schema_extraction

try:  # le SDK passe par httpx ou par son fork httpx2, dont les erreurs ne sont pas des httpx
    import httpx2

    ERREURS_RESEAU: tuple[type[Exception], ...] = (httpx.TransportError, httpx2.TransportError)
except ImportError:  # pragma: no cover
    ERREURS_RESEAU = (httpx.TransportError,)

if TYPE_CHECKING:
    from src.config.maison import ConfigMaison

# Modèle Flash : le palier gratuit ne donne accès qu'à cette famille.
MODELE_DEFAUT = "gemini-3.6-flash"
VARIABLE_MODELE = "CAVE_SCAN_GEMINI_MODEL"

# Codes qui se reproduiront à l'identique sur chaque bouteille (clé invalide,
# modèle inexistant, requête malformée) : inutile de les répéter 200 fois.
CODES_SYSTEMATIQUES = {400, 401, 403, 404}

# Codes passagers qui valent une nouvelle tentative : délai dépassé, limite de
# débit. Les 5xx (serveur surchargé ou en erreur) aussi, via `ServerError`.
CODES_PASSAGERS = {408, 429}

# Le palier gratuit tourne autour de 15 requêtes/minute. Un 429 n'y est donc
# PAS un incident, c'est le régime nominal : on espace les appels et on
# réessaie, au lieu de transformer la moitié d'une campagne en abstentions.
PAUSE_ENTRE_APPELS_S = 4.5
TENTATIVES_MAX = 4

# Gemini refuse une requête de plus de 20 Mo, images comprises, encodées en
# base64 (un tiers de plus) : 13 Mo d'images laissent la marge (0165).
LIMITES_ENVOI = LimitesEnvoi(octets_total=13 * 1024 * 1024)


class GeminiExtractor:
    """Implémente `Extractor` via l'API Gemini, en JSON contraint par schéma."""

    def __init__(
        self,
        client: Any | None = None,
        modele: str | None = None,
        pause_s: float = PAUSE_ENTRE_APPELS_S,
        tentatives_max: int = TENTATIVES_MAX,
        config: ConfigMaison | None = None,
        limiteur: Limiteur | None = None,
    ) -> None:
        # Le client résout sa clé seul : GEMINI_API_KEY, sinon GOOGLE_API_KEY.
        self.client = client or genai.Client()
        self.modele = modele or os.environ.get(VARIABLE_MODELE) or MODELE_DEFAUT
        self.pause_s = pause_s
        self.tentatives_max = tentatives_max
        # Partagé en base entre workers (0114) ; sans lui, espacement local.
        self.limiteur = limiteur
        self.config = config  # la maison : vocabulaire et colonnes envoyées au modèle
        self._config = types.GenerateContentConfig(
            system_instruction=consignes_systeme(config),
            # Sortie contrainte par LE schéma du projet, pas par un schéma
            # recopié : `schema.py` reste la source unique (decisions.md 0001),
            # et il suit la config de la maison (guide, étape 4.2).
            response_mime_type="application/json",
            response_json_schema=schema_extraction(config)["input_schema"],
            # Aucun appel de fonction ici : on le dit explicitement, sinon le SDK
            # l'active par défaut et l'annonce par un avertissement à chaque run.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self._dernier_appel = 0.0
        self.version_prompt = version_prompt(schema_extraction(config), consignes_systeme(config))

    def extraire_brut(self, photos: PhotosDUneBouteille) -> SortieModele:
        """Une bouteille, un appel. Même politique d'erreur que le backend payant.

        Panne SYSTÉMATIQUE -> remonte et arrête l'inventaire. Panne PASSAGÈRE,
        une fois les nouvelles tentatives épuisées -> rendue comme une donnée
        (decisions.md 0079).
        """
        contenu = construire_contenu(photos)
        try:
            reponse = self._appeler(contenu)
        except errors.APIError as erreur:
            if _est_systematique(erreur):
                raise
            return self._sortie_en_erreur(erreur)
        except ERREURS_RESEAU as erreur:  # délai dépassé, connexion coupée
            return self._sortie_en_erreur(erreur)
        return sortie_depuis_reponse(reponse, self.modele, self.version_prompt)

    def extract(self, photos: PhotosDUneBouteille) -> Bouteille:
        return bouteille_depuis_sortie(self.extraire_brut(photos), self.config)

    def _sortie_en_erreur(self, erreur: Exception) -> SortieModele:
        return SortieModele(
            brut=None,
            modele=self.modele,
            version_prompt=self.version_prompt,
            erreur=f"{type(erreur).__name__} : {erreur}",
        )

    def _appeler(self, contenu: list[Any]) -> Any:
        """Appelle le modèle en respectant le quota ; nouvelles tentatives à délai
        croissant sur panne passagère (decisions.md 0079)."""
        for tentative in range(1, self.tentatives_max + 1):
            self._respecter_le_quota()
            try:
                return self.client.models.generate_content(
                    model=self.modele, contents=contenu, config=self._config
                )
            except (errors.APIError, *ERREURS_RESEAU) as erreur:
                dernier = tentative == self.tentatives_max
                if not _merite_reprise(erreur) or dernier:
                    raise
                # Attente croissante : 9 s, 18 s, 36 s avec la pause par défaut.
                # Partagée : tous les workers ralentissent ensemble au lieu de
                # multiplier les tentatives (0114).
                attente = self.pause_s * (2**tentative)
                if self.limiteur is not None:
                    self.limiteur.ralentir(attente)
                else:
                    time.sleep(attente)
        raise AssertionError("inatteignable")  # pragma: no cover

    def _respecter_le_quota(self) -> None:
        """Espace les appels pour rester sous la limite du palier gratuit."""
        if self.limiteur is not None:
            self.limiteur.attendre_mon_tour()
            return
        if self.pause_s <= 0:
            return
        attente = self.pause_s - (time.monotonic() - self._dernier_appel)
        if attente > 0:
            time.sleep(attente)
        self._dernier_appel = time.monotonic()


def _code(erreur: Exception) -> int | None:
    return getattr(erreur, "code", None)


def _est_systematique(erreur: Exception) -> bool:
    return _code(erreur) in CODES_SYSTEMATIQUES


def _merite_reprise(erreur: Exception) -> bool:
    """Panne passagère : limite de débit, délai dépassé, serveur surchargé ou en
    erreur, connexion coupée. Jamais une panne systématique."""
    if isinstance(erreur, ERREURS_RESEAU):
        return True
    if _est_systematique(erreur):
        return False
    return _code(erreur) in CODES_PASSAGERS or isinstance(erreur, errors.ServerError)


def construire_contenu(photos: PhotosDUneBouteille) -> list[Any]:
    """Assemble le message : toutes les photos d'UNE bouteille, ensemble,
    numérotées dans l'ordre de l'expert (decisions.md 0164).

    Mêmes libellés que le backend Anthropic — la comparabilité des deux backends
    en dépend.
    """
    photos = liste_de_photos(photos)
    contenu: list[Any] = []
    for numero, (octets, type_mime) in enumerate(preparer_photos(photos, LIMITES_ENVOI), start=1):
        contenu.append(LIBELLE_PHOTO.format(numero=numero, total=len(photos)))
        contenu.append(types.Part.from_bytes(data=octets, mime_type=type_mime))
    contenu.append(INSTRUCTION_FINALE)
    return contenu


def sortie_depuis_reponse(reponse: Any, modele: str = "", version: str = "") -> SortieModele:
    """La réponse Gemini, TELLE QUELLE : son texte JSON n'est pas relu ici.

    S'il est illisible, il est quand même enregistré, et c'est l'interprétation
    qui échouera (decisions.md 0078). Tokens de sortie = réponse + réflexion :
    les deux sont facturés (decisions.md 0076).
    """
    usage = getattr(reponse, "usage_metadata", None)
    reponse_tokens = getattr(usage, "candidates_token_count", None)
    reflexion = getattr(usage, "thoughts_token_count", None)
    trace = {
        "modele": modele,
        "version_prompt": version,
        "tokens_entree": getattr(usage, "prompt_token_count", None),
        "tokens_sortie": None
        if reponse_tokens is None and reflexion is None
        else (reponse_tokens or 0) + (reflexion or 0),
    }
    texte = getattr(reponse, "text", None)
    if not texte:
        return SortieModele(brut=None, erreur=_motif_vide(reponse), **trace)
    return SortieModele(brut=texte, **trace)


def bouteille_depuis_reponse(reponse: Any, config: ConfigMaison | None = None) -> Bouteille:
    """La `Bouteille` d'une réponse — même chemin que `extract()`, sans l'appel."""
    return bouteille_depuis_sortie(sortie_depuis_reponse(reponse), config)


def _motif_vide(reponse: Any) -> str:
    """Pourquoi la réponse est vide — bloquée, tronquée, ou simplement muette."""
    retour = getattr(reponse, "prompt_feedback", None)
    if getattr(retour, "block_reason", None):
        return f"requête bloquée ({retour.block_reason})"

    candidats = getattr(reponse, "candidates", None) or []
    if candidats:
        raison = getattr(candidats[0], "finish_reason", None)
        if raison:
            return f"génération interrompue ({raison})"

    return "réponse vide"
