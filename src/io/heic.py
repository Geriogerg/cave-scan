"""Photos HEIC / HEIF d'iPhone : lues par Pillow grâce à pillow-heif (decisions.md 0158).

Importer ce module suffit à les rendre lisibles partout : il inscrit le lecteur
HEIC auprès de Pillow, une seule fois. Tout module qui ouvre une photo
l'importe — dépôt, ligne de commande, affichage, envoi au modèle.

Le fichier reçu est stocké TEL QUEL. Seul ce qui part au modèle est converti en
JPEG (`en_jpeg`), au moment de l'appel : les deux fournisseurs reçoivent ainsi
la même image, et le fournisseur payant n'accepte pas le HEIC.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

EXTENSIONS_HEIC = (".heic", ".heif")
QUALITE_JPEG = 95  # conversion pour le modèle : pas de perte visible sur une étiquette

register_heif_opener()


def est_heic(chemin: str | Path) -> bool:
    return Path(chemin).suffix.lower() in EXTENSIONS_HEIC


def en_jpeg(chemin: str | Path) -> bytes:
    """La photo en JPEG, orientée, SANS aucune métadonnée (l'EXIF d'un iPhone
    porte la position GPS de la cave du client)."""
    with Image.open(chemin) as originale:
        image = ImageOps.exif_transpose(originale).convert("RGB")
    sortie = io.BytesIO()
    image.save(sortie, "JPEG", quality=QUALITE_JPEG)
    return sortie.getvalue()
