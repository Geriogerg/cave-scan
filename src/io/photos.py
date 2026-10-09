"""Regroupement des photos par bouteille.

Convention v0, à confirmer avec l'expert (question ouverte de decisions.md) :

- **un sous-dossier par bouteille**, triés par nom — c'est cet ordre qui doit
  correspondre à l'ordre du listing manuel (decisions.md 0010) ;
- dans un sous-dossier, le rôle vient du nom de fichier : un nom contenant
  « contre » est la contre-étiquette, sinon le premier fichier trié est
  l'étiquette et le reste part dans `autres` ;
- si `--photos` ne contient aucun sous-dossier, chaque image du dossier est
  traitée comme une bouteille à étiquette seule.

Aucune correspondance n'est devinée au-delà de ça : si la vraie arborescence
diffère, c'est ici que ça se corrige, en un seul endroit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

EXTENSIONS_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@dataclass(frozen=True)
class PhotosBouteille:
    """Les vues d'UNE bouteille."""

    etiquette: Path
    contre_etiquette: Path | None = None
    autres: list[Path] = field(default_factory=list)

    @property
    def nom(self) -> str:
        return self.etiquette.parent.name or self.etiquette.stem

    @property
    def identifiant(self) -> str:
        """Identifiant stable de la bouteille : empreinte du CONTENU de ses photos.

        Le même d'un run à l'autre, insensible au renommage des fichiers — c'est
        ce qui permet de reprendre une campagne ou de retrouver une bouteille
        (decisions.md 0016, 0065). Une photo absente du disque (dry-run sur
        fixtures) contribue par son chemin.
        """
        empreinte = hashlib.sha256()
        for chemin in (self.etiquette, self.contre_etiquette, *self.autres):
            if chemin is None:
                continue
            chemin = Path(chemin)
            empreinte.update(chemin.read_bytes() if chemin.is_file() else str(chemin).encode())
            empreinte.update(b"\0")
        return f"B-{empreinte.hexdigest()[:10].upper()}"


def _images_triees(dossier: Path) -> list[Path]:
    return sorted(
        (c for c in dossier.iterdir() if c.suffix.lower() in EXTENSIONS_IMAGE),
        key=lambda c: c.name.casefold(),
    )


def _grouper_dossier(dossier: Path) -> PhotosBouteille | None:
    images = _images_triees(dossier)
    if not images:
        return None

    contre = next((i for i in images if "contre" in i.stem.casefold()), None)
    restantes = [i for i in images if i != contre]

    if not restantes:
        # Dossier ne contenant qu'une contre-étiquette : elle devient la vue
        # principale, faute de mieux. Le modèle s'abstiendra sur ce qui ne s'y
        # lit pas — c'est le comportement voulu, pas une dégradation à masquer.
        assert contre is not None  # garanti : `images` n'est pas vide
        return PhotosBouteille(etiquette=contre)

    return PhotosBouteille(
        etiquette=restantes[0], contre_etiquette=contre, autres=restantes[1:]
    )


def grouper_photos(racine: str | Path) -> list[PhotosBouteille]:
    """Liste les bouteilles trouvées sous `racine`, dans l'ordre du listing."""
    racine = Path(racine)
    if not racine.is_dir():
        raise NotADirectoryError(f"Dossier de photos introuvable : {racine}")

    sous_dossiers = sorted(
        (c for c in racine.iterdir() if c.is_dir()), key=lambda c: c.name.casefold()
    )

    if sous_dossiers:
        groupes = [_grouper_dossier(d) for d in sous_dossiers]
        bouteilles = [g for g in groupes if g is not None]
    else:
        bouteilles = [PhotosBouteille(etiquette=i) for i in _images_triees(racine)]

    if not bouteilles:
        raise ValueError(
            f"Aucune photo exploitable sous {racine} "
            f"(extensions reconnues : {', '.join(sorted(EXTENSIONS_IMAGE))})."
        )
    return bouteilles
