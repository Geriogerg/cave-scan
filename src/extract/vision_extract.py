"""Extraction par modèle vision-langage, en tool-use à sortie contrainte.

Seul module qui parle au réseau. Le VLM lit ET range en une passe : pas d'OCR
en amont, pas de parsing de texte libre en aval (decisions.md 0001).

Zero-shot assumé : ni exemple de vin, ni cas résolu dans le prompt. La v0 mesure
ce que sait faire un modèle générique sans aide ; un exemple rendrait le score
ininterprétable (decisions.md 0006).
"""

from __future__ import annotations

import base64
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import anthropic

from src.extract.base import CheminPhoto, SortieModele, bouteille_depuis_sortie
from src.extract.consignes import (
    INSTRUCTION_FINALE,
    LIBELLE_AUTRE,
    LIBELLE_CONTRE_ETIQUETTE,
    LIBELLE_ETIQUETTE,
    SYSTEM_PROMPT,
    lire_photo,
    version_prompt,
)
from src.extract.schema import Bouteille, schema_extraction

if TYPE_CHECKING:
    from src.config.maison import ConfigMaison

MODELE_DEFAUT = "claude-opus-5"
VARIABLE_MODELE = "CAVE_SCAN_MODEL"

# Nouvelles tentatives du SDK sur panne passagère, à délai croissant.
NOUVELLES_TENTATIVES = 3

# Pannes qui se répéteront à l'identique sur chaque bouteille : les avaler
# produirait 200 lignes vides en facturant 200 appels (decisions.md 0045).
ERREURS_SYSTEMATIQUES = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
    anthropic.BadRequestError,
)

# Le risque connu de la v0 : la combinaison thinking adaptatif + tool_choice
# forcé n'a jamais pu être testée contre l'API réelle (decisions.md 0029).
# Un 400 opaque au premier vrai run coûterait une demi-journée : on écrit
# directement la marche à suivre dans le message.
INDICE_400 = """L'API a refusé la requête (400) avec le modèle {modele}.

  {erreur}

Piste n°1 (decisions.md 0029) : la combinaison « thinking adaptatif +
tool_choice forcé » n'a jamais pu être vérifiée contre l'API réelle. Si le
message ci-dessus met en cause `thinking` ou `tool_choice`, la correction est
de passer tool_choice à {{"type": "auto"}} en nommant l'outil dans le prompt.

NE PAS désactiver le thinking pour contourner : sur cette famille de modèles,
le modèle écrit alors ses appels d'outil en texte visible, l'appel ne part
jamais et l'extraction sort vide sans lever d'erreur."""


def _bloc_image(chemin: CheminPhoto) -> dict[str, Any]:
    octets, type_mime = lire_photo(chemin)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": type_mime,
            "data": base64.standard_b64encode(octets).decode("utf-8"),
        },
    }


def construire_contenu(
    etiquette: CheminPhoto,
    contre_etiquette: CheminPhoto | None = None,
    autres: Sequence[CheminPhoto] | None = None,
) -> list[dict[str, Any]]:
    """Assemble les blocs du message : toutes les vues d'UNE bouteille, ensemble.

    Chaque image est précédée d'une étiquette de rôle : sans elle, le modèle ne
    sait pas laquelle est la contre-étiquette (où se lisent importateur et
    degré). Ce sont des repères de position, pas des exemples de réponse.
    """
    contenu: list[dict[str, Any]] = [
        {"type": "text", "text": LIBELLE_ETIQUETTE},
        _bloc_image(etiquette),
    ]

    if contre_etiquette is not None:
        contenu.append({"type": "text", "text": LIBELLE_CONTRE_ETIQUETTE})
        contenu.append(_bloc_image(contre_etiquette))

    for index, autre in enumerate(autres or [], start=1):
        contenu.append({"type": "text", "text": LIBELLE_AUTRE.format(index=index)})
        contenu.append(_bloc_image(autre))

    contenu.append({"type": "text", "text": INSTRUCTION_FINALE})
    return contenu


def sortie_depuis_reponse(reponse: Any, modele: str = "", version: str = "") -> SortieModele:
    """La réponse Anthropic, TELLE QUELLE, avec les tokens facturés.

    Appel d'outil -> son contenu est la réponse brute. Sinon (refus, réponse en
    texte libre), on garde quand même ce que le modèle a dit, et `erreur` dit
    pourquoi ce n'est pas exploitable (decisions.md 0078).
    """
    usage = getattr(reponse, "usage", None)
    trace = {
        "modele": modele,
        "version_prompt": version,
        "tokens_entree": getattr(usage, "input_tokens", None),
        "tokens_sortie": getattr(usage, "output_tokens", None),
    }
    for bloc in reponse.content:
        if bloc.type == "tool_use":
            return SortieModele(brut=dict(bloc.input), **trace)

    motif = "aucun appel d'outil dans la réponse"
    if getattr(reponse, "stop_reason", None) == "refusal":
        details = getattr(reponse, "stop_details", None)
        motif = f"refus du modèle ({getattr(details, 'category', None) or 'sans catégorie'})"
    textes = [bloc.text for bloc in reponse.content if getattr(bloc, "type", None) == "text"]
    brut = {"stop_reason": getattr(reponse, "stop_reason", None), "texte": textes}
    return SortieModele(brut=brut, erreur=motif, **trace)


def bouteille_depuis_reponse(reponse: Any, config: ConfigMaison | None = None) -> Bouteille:
    """La `Bouteille` d'une réponse — même chemin que `extract()`, sans l'appel."""
    return bouteille_depuis_sortie(sortie_depuis_reponse(reponse), config)


class VisionExtractor:
    """Implémente `Extractor` via l'API Anthropic, en tool-use forcé."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        modele: str | None = None,
        max_tokens: int = 16000,
        config: ConfigMaison | None = None,
    ) -> None:
        # Le client résout ses identifiants seul (ANTHROPIC_API_KEY, profil ant).
        # Pannes passagères (débit, délai, surcharge, 5xx) : le SDK réessaie
        # lui-même, à délai croissant (decisions.md 0079).
        self.client = client or anthropic.Anthropic(max_retries=NOUVELLES_TENTATIVES)
        self.modele = modele or os.environ.get(VARIABLE_MODELE) or MODELE_DEFAUT
        self.max_tokens = max_tokens
        # Le schéma suit la config de la maison (guide, étape 4.2) : colonnes
        # expert et système jamais envoyées.
        self.config = config
        self._outil = schema_extraction(config)
        self.version_prompt = version_prompt(self._outil)

    def extraire_brut(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> SortieModele:
        """Une bouteille, un appel ; toutes ses vues dans le même message.

        Panne SYSTÉMATIQUE (clé invalide, modèle inconnu, requête mal formée) :
        remonte et arrête l'inventaire — la répéter 200 fois ne ferait que
        produire 200 erreurs. Panne PASSAGÈRE, une fois les nouvelles tentatives
        du SDK épuisées : rendue comme une donnée (decisions.md 0079).
        """
        try:
            reponse = self._appeler(etiquette, contre_etiquette, autres)
        except ERREURS_SYSTEMATIQUES:
            raise
        except anthropic.APIError as erreur:
            return SortieModele(
                brut=None,
                modele=self.modele,
                version_prompt=self.version_prompt,
                erreur=f"{type(erreur).__name__} : {erreur}",
            )
        return sortie_depuis_reponse(reponse, self.modele, self.version_prompt)

    def extract(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> Bouteille:
        return bouteille_depuis_sortie(
            self.extraire_brut(etiquette, contre_etiquette, autres), self.config
        )

    def _appeler(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None,
        autres: Sequence[CheminPhoto] | None,
    ) -> Any:
        try:
            return self.client.messages.create(
                model=self.modele,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                # Lire une étiquette abîmée et savoir renoncer demande de la
                # réflexion : c'est précisément ce qu'on mesure, on laisse le
                # thinking adaptatif.
                thinking={"type": "adaptive"},
                tools=[self._outil],
                # Sortie contrainte : le modèle ne peut répondre qu'en remplissant
                # le schéma, il n'y a pas de texte libre à parser (0001).
                tool_choice={"type": "tool", "name": self._outil["name"]},
                messages=[
                    {
                        "role": "user",
                        "content": construire_contenu(
                            etiquette, contre_etiquette, autres
                        ),
                    }
                ],
            )
        except anthropic.BadRequestError as erreur:
            raise RuntimeError(INDICE_400.format(modele=self.modele, erreur=erreur)) from erreur
