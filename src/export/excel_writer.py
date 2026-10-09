"""Export d'une liste de `Bouteille` vers un .xlsx au format d'une maison.

Fond et forme séparés : ce module ne connaît QUE le contrat `Bouteille` et la
config de la maison (`src/config/maison.py`). Colonnes, en-têtes, ordre et
libellés viennent du JSON — changer de maison ou de libellé, c'est modifier un
fichier, jamais le code (decisions.md 0011, 0020).

Règles d'affichage (CLAUDE.md, decisions.md 0055) :
- une abstention (`non_lisible`, `non_determinable`) s'affiche en case VIDE et
  la ligne est SURLIGNÉE : l'abstention reste visible, sans être maquillée en
  valeur ;
- les colonnes expert restent vides — l'estimation n'est jamais remplie —, sauf
  la quantité, 1 par défaut ;
- aucune formule : le fichier livré doit être inerte et relisible.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.config.maison import (
    COLONNE_A_VERIFIER,
    COLONNE_ID,
    COLONNE_QUANTITE,
    Colonne,
    ConfigMaison,
)
from src.extract.schema import NATURE_DES_CHAMPS, Bouteille, est_abstention

# Mise en forme commune à toutes les maisons — pas des valeurs de maison.
POLICE = "Arial"
TAILLE_POLICE = 10
TITRE_FEUILLE = "Catalogue"
COULEUR_SURLIGNAGE = "FFF2CC"
LARGEUR_MIN, LARGEUR_MAX = 8, 50


def valeur_stockee(bouteille: Bouteille, colonne: Colonne) -> Any:
    """La valeur interne d'une colonne : un CODE pour les listes, jamais un libellé."""
    if colonne.cle == COLONNE_ID:
        return bouteille.id
    if colonne.cle == COLONNE_A_VERIFIER:
        return list(bouteille.champs_a_verifier)
    if colonne.cle == COLONNE_QUANTITE:
        return bouteille.quantite
    if colonne.source == "expert":
        return None  # saisi par l'expert : l'outil n'y écrit rien (decisions.md 0005)

    if colonne.cle in NATURE_DES_CHAMPS:
        valeur = getattr(bouteille, colonne.cle)
    else:
        valeur = bouteille.valeurs_maison.get(colonne.cle)
    return valeur.value if isinstance(valeur, StrEnum) else valeur


def valeur_affichee(bouteille: Bouteille, colonne: Colonne) -> Any:
    """Ce qui s'écrit dans la case. `None` = case vide.

    Les nombres restent des nombres (Excel doit pouvoir les trier), un code de
    liste s'affiche avec son libellé de maison, une abstention laisse la case
    vide — et c'est `a_relire()` qui surligne la ligne.
    """
    valeur = valeur_stockee(bouteille, colonne)

    if colonne.cle == COLONNE_A_VERIFIER:
        return ", ".join(valeur) or None
    if colonne.envoyee_au_modele and est_abstention(valeur):
        return None
    if valeur is None or valeur == "":
        return None
    if colonne.type == "liste":
        libelle = colonne.libelle(valeur)
        # Un code hors du vocabulaire de la maison s'affiche tel quel : jamais
        # masqué, et la ligne est surlignée.
        return libelle if libelle is not None else valeur
    return valeur


def a_relire(bouteille: Bouteille, config: ConfigMaison) -> bool:
    """La ligne doit-elle être surlignée ? (decisions.md 0055)

    Oui si une case lue par le modèle est vide pour cause d'abstention, si un
    code sort du vocabulaire de la maison, ou si le modèle a signalé un doute
    PRÉCIS. Les champs best effort, eux, sont à vérifier par principe : les
    compter surlignerait toutes les lignes et le surlignage ne dirait plus rien.
    """
    for colonne in config.colonnes_modele:
        valeur = valeur_stockee(bouteille, colonne)
        if est_abstention(valeur):
            return True
        if colonne.type == "liste" and colonne.libelle(valeur) is None:
            return True

    systematiques = {colonne.cle for colonne in config.colonnes_best_effort}
    return any(champ not in systematiques for champ in bouteille.champs_a_verifier)


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
    feuille.title = TITRE_FEUILLE

    # Version de la config copiée dans le fichier : savoir quelle nomenclature a
    # produit un export donné (guide, étape 4.1 ; decisions.md 0056).
    classeur.properties.title = f"{config.maison} — config v{config.version}"
    classeur.properties.version = str(config.version)
    classeur.properties.subject = config.chemin.name
    classeur.properties.language = config.langue

    police = Font(name=POLICE, size=TAILLE_POLICE)
    police_entete = Font(name=POLICE, size=TAILLE_POLICE, bold=True)
    surlignage = PatternFill(
        start_color=COULEUR_SURLIGNAGE, end_color=COULEUR_SURLIGNAGE, fill_type="solid"
    )

    largeurs = [len(colonne.nom) for colonne in config.colonnes]
    for index, colonne in enumerate(config.colonnes, start=1):
        cellule = feuille.cell(row=1, column=index, value=colonne.nom)
        cellule.font = police_entete
        cellule.alignment = Alignment(vertical="center", wrap_text=True)

    for numero_ligne, bouteille in enumerate(bouteilles, start=2):
        surligner = a_relire(bouteille, config)
        for index, colonne in enumerate(config.colonnes, start=1):
            valeur = valeur_affichee(bouteille, colonne)
            cellule = feuille.cell(row=numero_ligne, column=index, value=valeur)
            if isinstance(valeur, str) and valeur.startswith("="):
                # Un texte lu sur une étiquette ne doit jamais devenir une
                # formule exécutée à l'ouverture du fichier.
                cellule.data_type = "s"
            cellule.font = police
            if surligner:
                cellule.fill = surlignage
            if valeur is not None:
                largeurs[index - 1] = max(largeurs[index - 1], len(str(valeur)))

    for index, largeur in enumerate(largeurs, start=1):
        feuille.column_dimensions[get_column_letter(index)].width = min(
            max(largeur + 2, LARGEUR_MIN), LARGEUR_MAX
        )
    feuille.freeze_panes = "A2"

    classeur.save(chemin)
    return chemin
