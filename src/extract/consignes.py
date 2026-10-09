"""Les consignes d'extraction, INDÉPENDANTES du fournisseur de modèle.

Tout ce qui est ici est partagé par tous les extracteurs. C'est volontaire :
si deux backends recevaient des consignes différentes, leurs scores ne
seraient plus comparables et la v0 ne mesurerait plus rien (decisions.md 0049).

Ce module ne connaît aucun SDK. Chaque extracteur l'habille dans son propre
format de message.
"""

from __future__ import annotations

from pathlib import Path

TYPES_MEDIA = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# La discipline d'abstention est la consigne centrale, pas une précaution de fin
# de prompt : c'est elle qu'on mesure (decisions.md 0002, 0003, 0005).
# Zero-shot assumé : aucun exemple de vin, aucun cas résolu (decisions.md 0006).
SYSTEM_PROMPT = """Tu catalogues des bouteilles de vin pour une maison de vente aux enchères, à partir de photos.

RÈGLE ABSOLUE : tu ne devines jamais. Tu ne rapportes que ce qui est effectivement lisible ou visible sur les photos fournies.

- Un champ texte illisible, masqué, absent ou douteux vaut exactement « non_lisible ».
- Une couleur ou un format que rien n'établit vaut exactement « non_determinable ».
- Une contenance ou un degré qui n'est pas écrit vaut null.

Ces valeurs d'abstention sont des réponses CORRECTES et attendues. S'abstenir n'est jamais un échec. Inventer une valeur plausible est une faute grave : un expert humain relit ton travail en te faisant confiance sur ce point, et une valeur inventée passe le contrôle alors qu'une abstention le déclenche.

MILLÉSIME : uniquement s'il est écrit et lisible sur l'étiquette, la contre-étiquette ou la capsule. Ne le déduis jamais du style du vin, de la gamme, de la mise en page, de l'usure de l'étiquette ni d'aucun contexte. Au moindre doute sur un seul chiffre : « non_lisible ».

FORMAT : ne le déduis jamais d'une impression de taille sur la photo — un gros plan d'étiquette ne permet pas de conclure. Sans élément qui l'établisse réellement, réponds « non_determinable ».

COULEUR : renseigne couleur_source pour dire d'où vient l'information. « observee » si tu vois la couleur du vin ou qu'elle est écrite, « inferee » si tu la déduis de l'appellation ou du producteur, « non_lisible » si tu ne peux pas conclure.

EFFERVESCENCE : un champ distinct de la couleur, à renseigner séparément. Pour la couleur, applique le vocabulaire et les définitions propres à ce champ, même s'il mêle couleur et type de vin. Ne conclus « effervescent » que sur un signe réel : bouchon large maintenu par un muselet métallique, mention d'effervescence écrite, ou appellation qui ne produit que de l'effervescent. Sinon « non_determinable ».

CHAMPS_A_VERIFIER : liste-y le nom de chaque champ sur lequel un doute subsiste, même léger. C'est une file de relecture humaine, pas un aveu d'échec.

INTERDIT : tu ne produis aucune estimation, aucun prix, aucune cote, aucune valeur marchande, sous aucune forme, y compris dans les notes."""

# Repères de position, pas des exemples de réponse : sans eux le modèle ne sait
# pas laquelle est la contre-étiquette (où se lisent importateur et degré).
LIBELLE_ETIQUETTE = "Photo — étiquette :"
LIBELLE_CONTRE_ETIQUETTE = "Photo — contre-étiquette :"
LIBELLE_AUTRE = "Photo — vue complémentaire {index} :"

INSTRUCTION_FINALE = (
    "Ces photos montrent une seule et même bouteille. Relève les champs de "
    "catalogage lisibles et abstiens-toi sur les autres."
)


def type_media(chemin: Path) -> str:
    """Type MIME d'une photo, d'après son extension."""
    valeur = TYPES_MEDIA.get(chemin.suffix.lower())
    if valeur is None:
        raise ValueError(
            f"Format d'image non pris en charge : {chemin.name} "
            f"(acceptés : {', '.join(sorted(TYPES_MEDIA))})."
        )
    return valeur


def lire_photo(chemin: str | Path) -> tuple[bytes, str]:
    """Octets et type MIME d'une photo, avec une erreur claire si elle manque."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"Photo introuvable : {chemin}")
    return chemin.read_bytes(), type_media(chemin)
