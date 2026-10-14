"""Export d'une liste de `Bouteille` vers un .xlsx au format d'une maison.

Fond et forme séparés : ce module ne connaît QUE le contrat `Bouteille` et la
config de la maison (`src/config/maison.py`). Colonnes, en-têtes, ordre et
libellés viennent du JSON — changer de maison ou de libellé, c'est modifier un
fichier, jamais le code (decisions.md 0011, 0020).

Règles d'affichage (CLAUDE.md, decisions.md 0055) :
- une abstention (`non_lisible`, `non_determinable`) s'affiche en case VIDE et
  la ligne est SURLIGNÉE : l'abstention reste visible, sans être maquillée en
  valeur ;
- les colonnes expert affichent la saisie de l'expert, et seulement elle : le
  modèle ne remplit jamais l'estimation (CLAUDE.md, decisions.md 0082) ; la
  quantité vaut 1 par défaut ;
- aucune formule : le fichier livré doit être inerte et relisible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
    COLONNE_RELUE,
    Colonne,
    ConfigMaison,
)
from src.extract.schema import NATURE_DES_CHAMPS, Bouteille, est_abstention

# Mise en forme commune à toutes les maisons — pas des valeurs de maison.
POLICE = "Arial"
TAILLE_POLICE = 10
TITRE_FEUILLE = "Catalogue"
COULEUR_SURLIGNAGE = "FFF2CC"
COULEUR_ERREUR = "F4CCCC"  # bouteille dont l'analyse a échoué : à voir au premier coup d'œil
LARGEUR_MIN, LARGEUR_MAX = 8, 50
MENTION_ERREUR = "Erreur d'analyse"
MENTION_SAISIE_MANUELLE = "Saisie manuelle"


@dataclass(frozen=True)
class EtatLigne:
    """Ce que l'Excel dit d'une bouteille au-delà de ses valeurs (decisions.md 0170)."""

    erreur: bool = False  # l'analyse a échoué, et la bouteille n'a pas été validée en saisie manuelle
    saisie_manuelle: bool = False  # l'analyse a échoué ; l'expert a saisi ses champs et l'a validée
    relue: bool = False  # validée par l'expert


SANS_ETAT = EtatLigne()
Etats = Mapping[str, EtatLigne]  # par identifiant de bouteille


def valeur_stockee(bouteille: Bouteille, colonne: Colonne) -> Any:
    """La valeur interne d'une colonne : un CODE pour les listes, jamais un libellé."""
    if colonne.cle == COLONNE_ID:
        return bouteille.id
    if colonne.cle == COLONNE_A_VERIFIER:
        return list(bouteille.champs_a_verifier)
    if colonne.cle == COLONNE_QUANTITE:
        return bouteille.quantite
    if colonne.source == "expert":
        # Ce que l'EXPERT a saisi (estimation comprise), ou rien. Le modèle ne peut
        # pas écrire ici : sa lecture ne remplit que les colonnes lues (0082).
        return bouteille.valeurs_maison.get(colonne.cle)

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


def regrouper(bouteilles: Sequence[Bouteille], config: ConfigMaison, etats: Etats | None = None) -> list[list[Bouteille]]:
    """Fusionne, À L'EXPORT seulement, les bouteilles identiques sur les clés de
    `regroupement_export` (guide, étape 4.3 ; decisions.md 0017, 0066).

    En interne, une ligne reste une bouteille : la comparaison à l'expert et le
    journal ne voient jamais de regroupement.

    - Égalité STRICTE des codes et valeurs : pas de pliage casse/accents, ce
      serait déjà de la normalisation.
    - Une bouteille À RELIRE (abstention sur une case lue, code hors
      vocabulaire, doute précis) n'est jamais fusionnée : elle garde sa ligne,
      pour que ses cases vides restent visibles. En particulier, une abstention
      sur une clé n'est pas une égalité — « illisible » ne veut pas dire
      « identique », on fusionnerait sinon un magnum et une bouteille dont le
      format n'a pas pu être lu.
    - Une bouteille dont l'analyse a échoué (ou saisie à la main) n'est jamais
      fusionnée : sa ligne dit ce qui lui est arrivé (decisions.md 0170).
    - Ordre de première apparition conservé.
    """
    if not config.regroupement_export:
        return [[bouteille] for bouteille in bouteilles]

    colonnes = [config.colonne(cle) for cle in config.regroupement_export]
    groupes: dict[tuple[Any, ...], list[Bouteille]] = {}
    lignes: list[list[Bouteille]] = []
    for bouteille in bouteilles:
        cle = tuple(valeur_stockee(bouteille, colonne) for colonne in colonnes)
        etat = (etats or {}).get(bouteille.id, SANS_ETAT)
        if a_relire(bouteille, config) or etat.erreur or etat.saisie_manuelle:
            lignes.append([bouteille])
        elif cle in groupes:
            groupes[cle].append(bouteille)
        else:
            groupes[cle] = [bouteille]
            lignes.append(groupes[cle])
    return lignes


def valeur_affichee_ligne(
    groupe: Sequence[Bouteille], colonne: Colonne, etats: Etats | None = None, noms: Mapping[str, str] | None = None
) -> Any:
    """Ce qui s'écrit dans la case d'une ligne d'export, regroupée ou non.

    Quantités additionnées, identifiants tous listés, doutes réunis. Pour les
    autres colonnes : la valeur commune, ou les valeurs distinctes jointes par
    « / » — un regroupement ne doit rien faire disparaître.
    """
    if colonne.cle == COLONNE_QUANTITE:
        return sum(bouteille.quantite for bouteille in groupe)
    if colonne.cle == COLONNE_ID:
        return ", ".join(bouteille.id for bouteille in groupe if bouteille.id) or None
    lignes = [(etats or {}).get(bouteille.id, SANS_ETAT) for bouteille in groupe]
    if colonne.cle == COLONNE_A_VERIFIER:
        if any(etat.erreur for etat in lignes):
            return MENTION_ERREUR
        if any(etat.saisie_manuelle for etat in lignes):
            return MENTION_SAISIE_MANUELLE
        # Les doutes du modèle, par le nom de colonne de la maison (« État
        # étiquette »), jamais par la clé interne (rapport du testeur, T1-M2).
        # Une bouteille validée a été relue par l'expert : plus rien à vérifier (0183).
        champs = dict.fromkeys(
            (noms or {}).get(c, c)
            for bouteille, etat in zip(groupe, lignes, strict=True)
            if not etat.relue
            for c in bouteille.champs_a_verifier
        )
        return ", ".join(champs) or None
    if colonne.cle == COLONNE_RELUE:
        return "oui" if lignes and all(etat.relue for etat in lignes) else None

    distinctes = list(
        dict.fromkeys(
            valeur
            for valeur in (valeur_affichee(bouteille, colonne) for bouteille in groupe)
            if valeur is not None
        )
    )
    if not distinctes:
        return None
    if len(distinctes) == 1:
        return distinctes[0]
    return " / ".join(str(valeur) for valeur in distinctes)


def a_relire(bouteille: Bouteille, config: ConfigMaison) -> bool:
    """La ligne doit-elle être surlignée ? (decisions.md 0055 ; jamais pour une
    bouteille validée : `ecrire_excel` en tient compte, 0183)

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
    etats: Etats | None = None,
) -> Path:
    """Écrit le listing automatique et renvoie le chemin du fichier produit.
    `etats` : ce que l'Excel dit de chaque bouteille au-delà de ses valeurs
    (erreur d'analyse, saisie manuelle, relue), par identifiant."""
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
    erreur = PatternFill(start_color=COULEUR_ERREUR, end_color=COULEUR_ERREUR, fill_type="solid")

    largeurs = [len(colonne.nom) for colonne in config.colonnes]
    for index, colonne in enumerate(config.colonnes, start=1):
        cellule = feuille.cell(row=1, column=index, value=colonne.nom)
        cellule.font = police_entete
        cellule.alignment = Alignment(vertical="center", wrap_text=True)

    noms = {c.cle: c.nom for c in config.colonnes}
    for numero_ligne, groupe in enumerate(regrouper(bouteilles, config, etats), start=2):
        # Une ligne regroupée est à relire dès qu'une de ses bouteilles l'est —
        # une bouteille validée, jamais : l'expert l'a relue (decisions.md 0183).
        surligner = any(
            a_relire(bouteille, config) and not (etats or {}).get(bouteille.id, SANS_ETAT).relue
            for bouteille in groupe
        )
        en_erreur = any((etats or {}).get(bouteille.id, SANS_ETAT).erreur for bouteille in groupe)
        for index, colonne in enumerate(config.colonnes, start=1):
            valeur = valeur_affichee_ligne(groupe, colonne, etats, noms)
            cellule = feuille.cell(row=numero_ligne, column=index, value=valeur)
            if isinstance(valeur, str) and valeur.startswith("="):
                # Un texte lu sur une étiquette ne doit jamais devenir une
                # formule exécutée à l'ouverture du fichier.
                cellule.data_type = "s"
            cellule.font = police
            if en_erreur:
                cellule.fill = erreur
            elif surligner:
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
