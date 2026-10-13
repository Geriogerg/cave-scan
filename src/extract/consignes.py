"""Les consignes d'extraction, INDÉPENDANTES du fournisseur de modèle.

Tout ce qui est ici est partagé par tous les extracteurs. C'est volontaire :
si deux backends recevaient des consignes différentes, leurs scores ne
seraient plus comparables et la v0 ne mesurerait plus rien (decisions.md 0049).

Ce module ne connaît aucun SDK. Chaque extracteur l'habille dans son propre
format de message.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from src.io.heic import en_jpeg, est_heic

journal = logging.getLogger(__name__)

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
# Les consignes en trois parties (decisions.md 0173). Les deux parties FIXES portent
# les contraintes dures de CLAUDE.md (ne jamais deviner ; millésime et format jamais
# devinés ; aucun prix) : toujours envoyées, jamais modifiables. Celle du milieu, la
# maison peut la réécrire depuis la page Configuration.
REGLES_FIXES_DEBUT = """Tu catalogues des bouteilles de vin pour une maison de vente aux enchères, à partir de photos.

RÈGLE ABSOLUE : tu ne devines jamais. Tu ne rapportes que ce qui est effectivement lisible ou visible sur les photos fournies.

- Un champ texte illisible, masqué, absent ou douteux vaut exactement « non_lisible ».
- Une couleur ou un format que rien n'établit vaut exactement « non_determinable ».
- Une contenance ou un degré qui n'est pas écrit vaut null.

Ces valeurs d'abstention sont des réponses CORRECTES et attendues. S'abstenir n'est jamais un échec. Inventer une valeur plausible est une faute grave : un expert humain relit ton travail en te faisant confiance sur ce point, et une valeur inventée passe le contrôle alors qu'une abstention le déclenche.

MILLÉSIME : uniquement s'il est écrit et lisible sur l'étiquette, la contre-étiquette ou la capsule. Ne le déduis jamais du style du vin, de la gamme, de la mise en page, de l'usure de l'étiquette ni d'aucun contexte. Au moindre doute sur un seul chiffre : « non_lisible ».

FORMAT : ne le déduis jamais d'une impression de taille sur la photo — un gros plan d'étiquette ne permet pas de conclure. Sans élément qui l'établisse réellement, réponds « non_determinable »."""

CONSIGNES_MODIFIABLES = """COULEUR : renseigne couleur_source pour dire d'où vient l'information. « observee » si tu vois la couleur du vin ou qu'elle est écrite, « inferee » si tu la déduis de l'appellation ou du producteur, « non_lisible » si tu ne peux pas conclure.

EFFERVESCENCE : un champ distinct de la couleur, à renseigner séparément. Pour la couleur, applique le vocabulaire et les définitions propres à ce champ, même s'il mêle couleur et type de vin. Ne conclus « effervescent » que sur un signe réel : bouchon large maintenu par un muselet métallique, mention d'effervescence écrite, ou appellation qui ne produit que de l'effervescent. Sinon « non_determinable ».

CHAMPS_A_VERIFIER : liste-y le nom de chaque champ sur lequel un doute subsiste, même léger. C'est une file de relecture humaine, pas un aveu d'échec."""

REGLES_FIXES_FIN = """INTERDIT : tu ne produis aucune estimation, aucun prix, aucune cote, aucune valeur marchande, sous aucune forme, y compris dans les notes."""

# Le texte d'origine, au caractère près : les trois parties dans l'ordre.
SYSTEM_PROMPT = f"{REGLES_FIXES_DEBUT}\n\n{CONSIGNES_MODIFIABLES}\n\n{REGLES_FIXES_FIN}"

# Un repère de position, SANS rôle imposé : l'expert photographie librement
# chaque bouteille (étiquette, contre-étiquette s'il y en a une, capsule,
# bouteille entière…) et le modèle n'utilise que ce qu'il voit (decisions.md
# 0164). Ce n'est pas un exemple de réponse.
LIBELLE_PHOTO = "Photo {numero} sur {total} :"

# Ne PRÉSUPPOSE pas que les photos montrent la même bouteille : l'expert les a
# regroupées, une erreur de regroupement doit pouvoir être signalée (0069).
INSTRUCTION_FINALE = (
    "Ces photos, regroupées par l'expert, sont censées montrer une seule et même "
    "bouteille : vérifie-le et dis-le dans photos_meme_bouteille. Relève les "
    "champs de catalogage lisibles ou visibles sur l'une ou l'autre des photos, "
    "et abstiens-toi sur les autres."
)


def consignes_systeme(config) -> str:
    """Les consignes générales envoyées au modèle (decisions.md 0173) : la partie
    modifiable est celle de la config si la maison l'a réécrite ; les règles
    fixes (contraintes dures) l'encadrent TOUJOURS."""
    propres = getattr(config, "consignes", None)
    if not propres:
        return SYSTEM_PROMPT
    return f"{REGLES_FIXES_DEBUT}\n\n{propres}\n\n{REGLES_FIXES_FIN}"


def version_prompt(schema: dict, systeme: str = SYSTEM_PROMPT) -> str:
    """Empreinte de TOUT ce qui part au modèle : consignes, libellés, schéma.

    Deux extractions de même version ont reçu exactement la même demande ; dès
    qu'un mot du prompt ou une colonne de la config change, la version change
    (decisions.md 0076). Les deux fournisseurs reçoivent la même demande, donc
    la même version pour une même maison.
    """
    contenu = json.dumps(
        {
            "systeme": systeme,
            "libelles": [LIBELLE_PHOTO],
            "instruction": INSTRUCTION_FINALE,
            "schema": schema,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()[:12]


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
    """Octets et type MIME d'une photo, avec une erreur claire si elle manque.

    Une photo HEIC d'iPhone part en JPEG (converti ici, au moment de l'appel ;
    le fichier stocké ne change pas) : même image pour les deux fournisseurs,
    dont l'un n'accepte pas le HEIC (decisions.md 0158).
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"Photo introuvable : {chemin}")
    if est_heic(chemin):
        return en_jpeg(chemin), "image/jpeg"
    return chemin.read_bytes(), type_media(chemin)


# --- garde-fou de taille (decisions.md 0165) ----------------------------------------------
#
# Toutes les photos d'une bouteille partent dans le même appel. Au-delà de la
# limite du fournisseur, l'appel est refusé (400) — refus classé « panne
# systématique », qui arrêterait TOUT l'inventaire. Seules les photos les plus
# lourdes sont alors réduites, pour cet appel seulement : le fichier stocké ne
# change jamais, et une bouteille sous la limite part telle quelle.

COTES_DE_REDUCTION = (3000, 2500, 2000, 1600, 1200)  # côté long, en pixels
QUALITE_REDUCTION = 90


@dataclass(frozen=True)
class LimitesEnvoi:
    """Ce qu'un fournisseur accepte en un appel, en octets d'image (avant
    l'encodage base64, qui ajoute un tiers)."""

    octets_total: int
    octets_par_photo: int | None = None


def preparer_photos(photos: Sequence[str | Path], limites: LimitesEnvoi) -> list[tuple[bytes, str]]:
    """Octets et type MIME de chaque photo, dans l'ordre, sous les limites."""
    contenus = [lire_photo(photo) for photo in photos]
    etapes = [0] * len(contenus)  # réduction déjà appliquée à chaque photo

    def depasse() -> int | None:
        """La photo à réduire : trop lourde seule, sinon la plus lourde."""
        if limites.octets_par_photo is not None:
            for index, (octets, _type) in enumerate(contenus):
                if len(octets) > limites.octets_par_photo and etapes[index] < len(COTES_DE_REDUCTION):
                    return index
        if sum(len(octets) for octets, _type in contenus) > limites.octets_total:
            candidates = [i for i in range(len(contenus)) if etapes[i] < len(COTES_DE_REDUCTION)]
            if candidates:
                return max(candidates, key=lambda i: len(contenus[i][0]))
        return None

    while (index := depasse()) is not None:
        cote = COTES_DE_REDUCTION[etapes[index]]
        etapes[index] += 1
        contenus[index] = (_reduire(Path(photos[index]), cote), "image/jpeg")
    reduites = [Path(photos[i]).name for i, etape in enumerate(etapes) if etape]
    if reduites:
        journal.warning(
            "Photos réduites pour tenir dans un appel (%s octets au plus) : %s",
            limites.octets_total, ", ".join(reduites),
        )
    return contenus


def _reduire(chemin: Path, cote: int) -> bytes:
    """La photo d'ORIGINE réduite (jamais une réduction de réduction), orientée,
    sans métadonnées."""
    from PIL import Image, ImageOps

    with Image.open(chemin) as originale:
        image = ImageOps.exif_transpose(originale).convert("RGB")
    image.thumbnail((cote, cote))
    sortie = io.BytesIO()
    image.save(sortie, "JPEG", quality=QUALITE_REDUCTION)
    return sortie.getvalue()
