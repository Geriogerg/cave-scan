"""Export d'une liste de `Bouteille` vers un .xlsx au format d'une maison.

Fond et forme séparés : ce module ne connaît QUE le contrat `Bouteille` et une
config. Les colonnes, en-têtes et libellés viennent d'un YAML — une nouvelle
maison est un fichier de config, jamais une sous-classe (decisions.md 0011).

Aucune formule n'est écrite : le fichier livré doit être inerte et relisible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.extract.schema import (
    CHAMPS,
    NON_DETERMINABLE,
    NON_LISIBLE,
    Bouteille,
)


@dataclass(frozen=True)
class Colonne:
    """Une colonne du fichier livré.

    `champ` vaut ``None`` pour une colonne que le modèle ne remplit pas : elle
    sort vide et reste à la main de la maison (typiquement lot et estimation).
    """

    entete: str
    champ: str | None = None
    largeur: int = 18


@dataclass(frozen=True)
class ConfigMaison:
    """Format de sortie d'une maison. Pures données, aucun comportement."""

    maison: str
    colonnes: list[Colonne]
    langue: str = "fr"
    titre_feuille: str = "Catalogue"
    police: str = "Arial"
    taille_police: int = 10
    figer_entetes: bool = True
    surlignage_a_verifier: str | None = None
    libelles: dict[str, str] = field(default_factory=dict)


def charger_config(chemin: str | Path) -> ConfigMaison:
    """Lit un YAML de maison et valide ses champs source.

    Une colonne qui référence un champ inexistant de `Bouteille` est une faute
    de frappe : on s'arrête ici plutôt que de livrer un fichier avec une colonne
    silencieusement vide.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"Config maison introuvable : {chemin}")

    brut = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    feuille = brut.get("feuille") or {}

    colonnes: list[Colonne] = []
    for index, entree in enumerate(brut.get("colonnes") or []):
        champ = entree.get("champ")
        if champ is not None and champ not in CHAMPS:
            raise ValueError(
                f"{chemin} : colonne {index} (« {entree.get('entete')} ») référence "
                f"le champ inconnu « {champ} ». Champs disponibles : {', '.join(CHAMPS)}."
            )
        colonnes.append(
            Colonne(
                entete=str(entree.get("entete", "")),
                champ=champ,
                largeur=int(entree.get("largeur", 18)),
            )
        )

    if not colonnes:
        raise ValueError(f"{chemin} : aucune colonne définie.")

    return ConfigMaison(
        maison=str(brut.get("maison", "")),
        colonnes=colonnes,
        langue=str(brut.get("langue", "fr")),
        titre_feuille=str(feuille.get("titre", "Catalogue")),
        police=str(feuille.get("police", "Arial")),
        taille_police=int(feuille.get("taille_police", 10)),
        figer_entetes=bool(feuille.get("figer_entetes", True)),
        surlignage_a_verifier=brut.get("surlignage_a_verifier"),
        libelles={str(k): str(v) for k, v in (brut.get("libelles") or {}).items()},
    )


def valeur_cellule(bouteille: Bouteille, colonne: Colonne, libelles: dict[str, str]) -> Any:
    """Valeur affichée d'une case, abstentions traduites selon la config.

    Les nombres restent des nombres (Excel doit pouvoir les trier), le texte
    reste du texte, et une abstention s'écrit avec le libellé de la maison.
    """
    if colonne.champ is None:
        return ""

    valeur = getattr(bouteille, colonne.champ)

    if isinstance(valeur, list):
        return ", ".join(str(element) for element in valeur)

    if isinstance(valeur, StrEnum):
        valeur = valeur.value

    if valeur is None:
        return libelles.get("numerique_absent", libelles.get(NON_LISIBLE, NON_LISIBLE))

    if isinstance(valeur, str) and valeur in (NON_LISIBLE, NON_DETERMINABLE):
        return libelles.get(valeur, valeur)

    return valeur


def ecrire_excel(
    bouteilles: Sequence[Bouteille],
    config: ConfigMaison,
    chemin: str | Path,
) -> Path:
    """Écrit le listing automatique et renvoie le chemin du fichier produit."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = config.titre_feuille
    classeur.properties.language = config.langue

    police = Font(name=config.police, size=config.taille_police)
    police_entete = Font(name=config.police, size=config.taille_police, bold=True)
    surlignage = (
        PatternFill(
            start_color=config.surlignage_a_verifier,
            end_color=config.surlignage_a_verifier,
            fill_type="solid",
        )
        if config.surlignage_a_verifier
        else None
    )
    alignement_entete = Alignment(vertical="center", wrap_text=True)

    for index, colonne in enumerate(config.colonnes, start=1):
        cellule = feuille.cell(row=1, column=index, value=colonne.entete)
        cellule.font = police_entete
        cellule.alignment = alignement_entete
        feuille.column_dimensions[get_column_letter(index)].width = colonne.largeur

    for numero_ligne, bouteille in enumerate(bouteilles, start=2):
        a_verifier = bool(bouteille.champs_a_verifier)
        for index, colonne in enumerate(config.colonnes, start=1):
            cellule = feuille.cell(
                row=numero_ligne,
                column=index,
                value=valeur_cellule(bouteille, colonne, config.libelles),
            )
            cellule.font = police
            if a_verifier and surlignage is not None:
                cellule.fill = surlignage

    if config.figer_entetes:
        feuille.freeze_panes = "A2"

    classeur.save(chemin)
    return chemin
