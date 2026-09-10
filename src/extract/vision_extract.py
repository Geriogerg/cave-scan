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
from pathlib import Path
from typing import Any

import anthropic

from src.extract.base import CheminPhoto
from src.extract.schema import Bouteille, from_tool_input, tool_schema

MODELE_DEFAUT = "claude-opus-5"
VARIABLE_MODELE = "CAVE_SCAN_MODEL"

TYPES_MEDIA = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# La discipline d'abstention est la consigne centrale, pas une précaution de fin
# de prompt : c'est elle qu'on mesure (decisions.md 0002, 0003, 0005).
SYSTEM_PROMPT = """Tu catalogues des bouteilles de vin pour une maison de vente aux enchères, à partir de photos.

RÈGLE ABSOLUE : tu ne devines jamais. Tu ne rapportes que ce qui est effectivement lisible ou visible sur les photos fournies.

- Un champ texte illisible, masqué, absent ou douteux vaut exactement « non_lisible ».
- Une couleur ou un format que rien n'établit vaut exactement « non_determinable ».
- Une contenance ou un degré qui n'est pas écrit vaut null.

Ces valeurs d'abstention sont des réponses CORRECTES et attendues. S'abstenir n'est jamais un échec. Inventer une valeur plausible est une faute grave : un expert humain relit ton travail en te faisant confiance sur ce point, et une valeur inventée passe le contrôle alors qu'une abstention le déclenche.

MILLÉSIME : uniquement s'il est écrit et lisible sur l'étiquette, la contre-étiquette ou la capsule. Ne le déduis jamais du style du vin, de la gamme, de la mise en page, de l'usure de l'étiquette ni d'aucun contexte. Au moindre doute sur un seul chiffre : « non_lisible ».

FORMAT : ne le déduis jamais d'une impression de taille sur la photo — un gros plan d'étiquette ne permet pas de conclure. Sans élément qui l'établisse réellement, réponds « non_determinable ».

COULEUR : renseigne couleur_source pour dire d'où vient l'information. « observee » si tu vois la couleur du vin ou qu'elle est écrite, « inferee » si tu la déduis de l'appellation ou du producteur, « non_lisible » si tu ne peux pas conclure.

EFFERVESCENCE : indépendante de la couleur — un effervescent peut être blanc, rosé ou rouge, alors renseigne les deux séparément. Ne conclus « effervescent » que sur un signe réel : bouchon large maintenu par un muselet métallique, mention d'effervescence écrite, ou appellation qui ne produit que de l'effervescent. Sinon « non_determinable ».

CHAMPS_A_VERIFIER : liste-y le nom de chaque champ sur lequel un doute subsiste, même léger. C'est une file de relecture humaine, pas un aveu d'échec.

INTERDIT : tu ne produis aucune estimation, aucun prix, aucune cote, aucune valeur marchande, sous aucune forme, y compris dans les notes.

Réponds en appelant l'outil enregistrer_bouteille, et uniquement ainsi."""


# Pannes qui se répéteront à l'identique sur chaque bouteille : les avaler
# produirait 200 lignes vides en facturant 200 appels (decisions.md 0035).
ERREURS_SYSTEMATIQUES = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
    anthropic.BadRequestError,
)

# Le risque connu de la v0 : la combinaison thinking adaptatif + tool_choice
# forcé n'a jamais pu être testée contre l'API réelle (decisions.md 0019).
# Un 400 opaque au premier vrai run coûterait une demi-journée : on écrit
# directement la marche à suivre dans le message.
INDICE_400 = """L'API a refusé la requête (400) avec le modèle {modele}.

  {erreur}

Piste n°1 (decisions.md 0019) : la combinaison « thinking adaptatif +
tool_choice forcé » n'a jamais pu être vérifiée contre l'API réelle. Si le
message ci-dessus met en cause `thinking` ou `tool_choice`, la correction est
de passer tool_choice à {{"type": "auto"}} en nommant l'outil dans le prompt.

NE PAS désactiver le thinking pour contourner : sur cette famille de modèles,
le modèle écrit alors ses appels d'outil en texte visible, l'appel ne part
jamais et l'extraction sort vide sans lever d'erreur."""


def _type_media(chemin: Path) -> str:
    type_media = TYPES_MEDIA.get(chemin.suffix.lower())
    if type_media is None:
        raise ValueError(
            f"Format d'image non pris en charge : {chemin.name} "
            f"(acceptés : {', '.join(sorted(TYPES_MEDIA))})."
        )
    return type_media


def _bloc_image(chemin: CheminPhoto) -> dict[str, Any]:
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"Photo introuvable : {chemin}")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _type_media(chemin),
            "data": base64.standard_b64encode(chemin.read_bytes()).decode("utf-8"),
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
        {"type": "text", "text": "Photo — étiquette :"},
        _bloc_image(etiquette),
    ]

    if contre_etiquette is not None:
        contenu.append({"type": "text", "text": "Photo — contre-étiquette :"})
        contenu.append(_bloc_image(contre_etiquette))

    for index, autre in enumerate(autres or [], start=1):
        contenu.append({"type": "text", "text": f"Photo — vue complémentaire {index} :"})
        contenu.append(_bloc_image(autre))

    contenu.append(
        {
            "type": "text",
            "text": (
                "Ces photos montrent une seule et même bouteille. Relève les champs "
                "de catalogage lisibles et abstiens-toi sur les autres."
            ),
        }
    )
    return contenu


def bouteille_depuis_reponse(reponse: Any) -> Bouteille:
    """Extrait la `Bouteille` de la réponse, en s'abstenant si le modèle n'a rien rendu.

    Un refus ou une réponse sans appel d'outil ne doit pas casser une campagne
    d'extraction : on renvoie une bouteille entièrement en abstention, avec la
    raison dans `notes` pour qu'elle soit visible en relecture.
    """
    for bloc in reponse.content:
        if bloc.type == "tool_use":
            return from_tool_input(dict(bloc.input))

    motif = "aucun appel d'outil dans la réponse"
    if getattr(reponse, "stop_reason", None) == "refusal":
        details = getattr(reponse, "stop_details", None)
        motif = f"refus du modèle ({getattr(details, 'category', None) or 'sans catégorie'})"

    return Bouteille(
        champs_a_verifier=["tous"],
        notes=f"Extraction sans résultat : {motif}.",
    )


class VisionExtractor:
    """Implémente `Extractor` via l'API Anthropic, en tool-use forcé."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        modele: str | None = None,
        max_tokens: int = 16000,
    ) -> None:
        # Le client résout ses identifiants seul (ANTHROPIC_API_KEY, profil ant).
        self.client = client or anthropic.Anthropic()
        self.modele = modele or os.environ.get(VARIABLE_MODELE) or MODELE_DEFAUT
        self.max_tokens = max_tokens
        self._outil = tool_schema()

    def extract(
        self,
        etiquette: CheminPhoto,
        contre_etiquette: CheminPhoto | None = None,
        autres: Sequence[CheminPhoto] | None = None,
    ) -> Bouteille:
        """Une bouteille, un appel. Toutes les vues partent dans le même message.

        Politique d'erreur (decisions.md 0035) : une panne PASSAGÈRE sur une
        bouteille produit une abstention tracée et la campagne continue ; une
        panne SYSTÉMATIQUE (clé invalide, modèle inconnu, requête malformée)
        remonte et arrête tout — la répéter 200 fois ne ferait que produire
        200 lignes vides en facturant chaque échec.
        """
        try:
            reponse = self._appeler(etiquette, contre_etiquette, autres)
        except ERREURS_SYSTEMATIQUES:
            raise
        except anthropic.APIError as erreur:
            return Bouteille(
                champs_a_verifier=["tous"],
                notes=f"Extraction échouée ({type(erreur).__name__}) : {erreur}",
            )
        return bouteille_depuis_reponse(reponse)

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
