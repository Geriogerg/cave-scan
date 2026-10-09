"""Stockage des photos géré par l'outil (decisions.md 0074).

Les photos déposées sont COPIÉES ici, nommées par leur empreinte SHA-256 : la
base ne pointe jamais vers un fichier que l'utilisateur aurait déplacé ou
renommé, et une même photo n'est stockée qu'une fois, quel que soit le nombre
d'inventaires qui l'utilisent.

La base ne garde que le chemin RELATIF au stockage : déplacer le dossier de
stockage (avec `CAVE_SCAN_STOCKAGE`) ne casse rien. Aucune image n'entre jamais
dans la base.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

TAILLE_BLOC = 1024 * 1024


def empreinte_fichier(chemin: Path) -> str:
    """SHA-256 du contenu du fichier, lu par blocs (une photo peut peser 10 Mo)."""
    empreinte = hashlib.sha256()
    with Path(chemin).open("rb") as flux:
        for bloc in iter(lambda: flux.read(TAILLE_BLOC), b""):
            empreinte.update(bloc)
    return empreinte.hexdigest()


def stocker(source: Path, stockage: Path, empreinte: str | None = None) -> str:
    """Copie la photo dans le stockage et renvoie son chemin RELATIF au stockage.

    Le nom garde l'extension (en minuscules) : c'est elle qui donne le type
    d'image envoyé au modèle. Déjà présente (même contenu) : rien n'est recopié.
    La copie passe par un fichier temporaire renommé à la fin, pour qu'une
    coupure en pleine copie ne laisse jamais une photo tronquée sous un nom
    valide.
    """
    source = Path(source)
    empreinte = empreinte or empreinte_fichier(source)
    relatif = f"{empreinte}{source.suffix.lower()}"
    cible = Path(stockage) / relatif
    if not cible.exists():
        cible.parent.mkdir(parents=True, exist_ok=True)
        partiel = cible.with_name(cible.name + ".partiel")
        shutil.copyfile(source, partiel)
        os.replace(partiel, cible)
    return relatif


def chemin_stocke(stockage: Path, relatif: str) -> Path:
    """Chemin absolu d'une photo stockée."""
    return Path(stockage) / relatif
