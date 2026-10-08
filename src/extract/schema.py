"""Contrat de données partagé de la v0.

`Bouteille` est produit par les extracteurs, traversé par la normalisation,
consommé par l'export Excel et par la comparaison. Tout le reste dépend de ce
module ; ce module ne dépend de rien d'autre que la stdlib.

Conventions d'abstention (decisions.md 0002, 0003) — ce ne sont pas des échecs,
on mesure l'abstention, on ne la punit pas :

- champs texte      -> ``NON_LISIBLE``
- enums fermés      -> ``non_determinable``
- champs numériques -> ``None``
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Any

# Sentinelle des champs texte illisibles sur la photo.
NON_LISIBLE = "non_lisible"

# Sentinelle des enums fermés : la valeur n'a pas pu être déterminée.
NON_DETERMINABLE = "non_determinable"


class Couleur(StrEnum):
    """Couleur du vin. Enum fermé (decisions.md 0002)."""

    ROUGE = "rouge"
    BLANC = "blanc"
    ROSE = "rose"
    NON_DETERMINABLE = NON_DETERMINABLE


class CouleurSource(StrEnum):
    """D'où vient la couleur : lue sur l'étiquette, ou déduite de l'appellation.

    L'expert doit pouvoir distinguer les deux en relisant (decisions.md 0004).
    """

    OBSERVEE = "observee"
    INFEREE = "inferee"
    NON_LISIBLE = NON_LISIBLE


class Effervescence(StrEnum):
    """Vin tranquille ou effervescent. Enum fermé, INDÉPENDANT de la couleur.

    Deux dimensions distinctes : un effervescent peut être blanc, rosé ou rouge.
    Les fusionner dans `couleur` obligerait à choisir et perdrait l'information
    (decisions.md 0041).

    La catégorie précise (champagne, crémant, mousseux...) n'est pas un enum ici :
    c'est une appellation, elle se lit et se range dans `appellation`.
    """

    TRANQUILLE = "tranquille"
    EFFERVESCENT = "effervescent"
    NON_DETERMINABLE = NON_DETERMINABLE


class Format(StrEnum):
    """Format de la bouteille. Enum fermé.

    ``non_determinable`` est la valeur par défaut attendue : le format est
    rarement déductible d'un gros plan d'étiquette (decisions.md 0003).
    Le format ne détermine PAS la contenance (un jéroboam bordelais et un
    jéroboam bourguignon n'ont pas le même volume) : les deux champs sont
    indépendants et lus séparément.
    """

    DEMI_BOUTEILLE = "demi_bouteille"
    BOUTEILLE = "bouteille"
    MAGNUM = "magnum"
    JEROBOAM = "jeroboam"
    REHOBOAM = "rehoboam"
    MATHUSALEM = "mathusalem"
    SALMANAZAR = "salmanazar"
    BALTHAZAR = "balthazar"
    NABUCHODONOSOR = "nabuchodonosor"
    NON_DETERMINABLE = NON_DETERMINABLE


@dataclass
class Bouteille:
    """Les champs de catalogage extraits d'une bouteille.

    Les valeurs par défaut sont toutes des abstentions : une `Bouteille()` vide
    n'affirme rien. C'est volontaire — un champ non renseigné ne doit jamais
    passer pour une lecture.
    """

    appellation: str = NON_LISIBLE
    domaine: str = NON_LISIBLE
    cuvee: str = NON_LISIBLE
    couleur: Couleur = Couleur.NON_DETERMINABLE
    couleur_source: CouleurSource = CouleurSource.NON_LISIBLE
    effervescence: Effervescence = Effervescence.NON_DETERMINABLE
    millesime: str = NON_LISIBLE
    region: str = NON_LISIBLE
    pays: str = NON_LISIBLE
    format: Format = Format.NON_DETERMINABLE
    contenance_cl: int | None = None
    degre: float | None = None
    importateur: str = NON_LISIBLE
    champs_a_verifier: list[str] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Vue dict sérialisable (enums réduits à leur valeur texte)."""
        sortie: dict[str, Any] = {}
        for f in fields(self):
            valeur = getattr(self, f.name)
            if isinstance(valeur, StrEnum):
                valeur = valeur.value
            elif isinstance(valeur, list):
                valeur = list(valeur)
            sortie[f.name] = valeur
        return sortie


# Ordre canonique des champs, tel que déclaré sur la dataclass.
CHAMPS: tuple[str, ...] = tuple(f.name for f in fields(Bouteille))

# Champs effectivement comparables au listing manuel de l'expert.
# `couleur_source`, `champs_a_verifier` et `notes` sont des métadonnées produites
# par le modèle : l'expert n'en produit pas d'équivalent, les comparer n'a pas
# de sens.
CHAMPS_COMPARABLES: tuple[str, ...] = (
    "appellation",
    "domaine",
    "cuvee",
    "couleur",
    "effervescence",
    "millesime",
    "region",
    "pays",
    "format",
    "contenance_cl",
    "degre",
    "importateur",
)


def est_abstention(valeur: Any) -> bool:
    """Le modèle a-t-il refusé de se prononcer sur ce champ ?

    Vrai pour ``None``, ``non_lisible``, ``non_determinable`` et la chaîne vide.
    C'est le seul endroit qui connaît les trois conventions d'abstention : tout
    le reste du code passe par ici.
    """
    if valeur is None:
        return True
    if isinstance(valeur, StrEnum):
        valeur = valeur.value
    if isinstance(valeur, str):
        return valeur.strip().casefold() in {"", NON_LISIBLE, NON_DETERMINABLE}
    return False


def tool_schema() -> dict[str, Any]:
    """Définition de l'outil Anthropic imposant une sortie `Bouteille` contrainte.

    Le VLM répond en appelant cet outil (tool_choice forcé) : la sortie est
    structurée par construction, pas par parsing d'un texte libre.

    Les descriptions ne contiennent AUCUN exemple de valeur : la v0 mesure le
    zero-shot, un exemple dans le schéma rendrait le score ininterprétable
    (decisions.md 0006).
    """
    texte_abstention = f"Si ce n'est pas lisible sur les photos, répondre exactement « {NON_LISIBLE} ». Ne jamais deviner."

    return {
        "name": "enregistrer_bouteille",
        "description": (
            "Enregistre les champs de catalogage lus sur les photos d'une "
            "bouteille de vin. Tous les champs sont obligatoires : quand une "
            "information n'est pas lisible, utiliser la valeur d'abstention "
            "prévue plutôt qu'une supposition."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "appellation": {
                    "type": "string",
                    "description": f"Appellation telle qu'écrite sur l'étiquette. {texte_abstention}",
                },
                "domaine": {
                    "type": "string",
                    "description": f"Producteur : domaine, château, maison ou négociant, tel qu'écrit. {texte_abstention}",
                },
                "cuvee": {
                    "type": "string",
                    "description": (
                        "Nom de cuvée, climat ou lieu-dit, tel qu'écrit, s'il est "
                        f"distinct de l'appellation. {texte_abstention}"
                    ),
                },
                "couleur": {
                    "type": "string",
                    "enum": [c.value for c in Couleur],
                    "description": "Couleur du vin.",
                },
                "couleur_source": {
                    "type": "string",
                    "enum": [c.value for c in CouleurSource],
                    "description": (
                        "Comment la couleur a été obtenue : « observee » si elle "
                        "est lue ou visible sur les photos, « inferee » si elle "
                        "est déduite de l'appellation ou du producteur, "
                        f"« {NON_LISIBLE} » si la couleur n'a pas pu être déterminée."
                    ),
                },
                "effervescence": {
                    "type": "string",
                    "enum": [e.value for e in Effervescence],
                    "description": (
                        "Vin effervescent ou tranquille, uniquement si ce qui est "
                        "visible l'établit : bouchon large maintenu par un muselet "
                        "métallique, mention d'effervescence sur l'étiquette, ou "
                        "appellation qui ne produit que de l'effervescent. Sinon "
                        f"« {NON_DETERMINABLE} ». Indépendant de la couleur : un "
                        "effervescent peut être blanc, rosé ou rouge."
                    ),
                },
                "millesime": {
                    "type": "string",
                    "description": (
                        "Millésime, uniquement s'il est LU sur l'étiquette ou la "
                        "capsule. Ne jamais le déduire d'un style, d'une gamme ni "
                        f"d'un contexte. Dans le moindre doute : « {NON_LISIBLE} »."
                    ),
                },
                "region": {
                    "type": "string",
                    "description": f"Région viticole. {texte_abstention}",
                },
                "pays": {
                    "type": "string",
                    "description": f"Pays d'origine. {texte_abstention}",
                },
                "format": {
                    "type": "string",
                    "enum": [f.value for f in Format],
                    "description": (
                        "Format du contenant, uniquement s'il est établi par ce "
                        "qui est visible. Un gros plan d'étiquette ne permet "
                        "généralement pas de le déterminer : dans ce cas répondre "
                        f"« {NON_DETERMINABLE} ». Ne jamais déduire le format d'une "
                        "impression de taille."
                    ),
                },
                "contenance_cl": {
                    "type": ["integer", "null"],
                    "description": (
                        "Contenance en centilitres, uniquement si elle est écrite "
                        "sur l'étiquette. Convertir en centilitres si elle est "
                        "exprimée dans une autre unité. Sinon : null."
                    ),
                },
                "degre": {
                    "type": ["number", "null"],
                    "description": (
                        "Titre alcoométrique en % vol., uniquement s'il est écrit "
                        "sur l'étiquette. Sinon : null."
                    ),
                },
                "importateur": {
                    "type": "string",
                    "description": (
                        "Importateur ou distributeur, généralement mentionné sur "
                        f"la contre-étiquette. {texte_abstention}"
                    ),
                },
                "champs_a_verifier": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Noms des champs ci-dessus sur lesquels subsiste un doute "
                        "et qu'un relecteur humain devrait contrôler : texte "
                        "partiellement masqué, abîmé, ambigu ou difficile à lire. "
                        "Liste vide s'il n'y a aucun doute."
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Observations libres utiles au catalogage et visibles sur "
                        "les photos (mentions particulières, état de l'étiquette). "
                        "Ne JAMAIS y mettre d'estimation, de prix ni de valeur "
                        "marchande. Chaîne vide s'il n'y a rien à signaler."
                    ),
                },
            },
            "required": list(CHAMPS),
        },
    }


def from_tool_input(charge: dict[str, Any]) -> Bouteille:
    """Construit une `Bouteille` à partir de la charge utile d'un appel d'outil.

    Tolérante par conception : une clé manquante retombe sur l'abstention, une
    valeur d'enum inconnue devient ``non_determinable``. Un modèle qui répond
    de travers doit produire une abstention, jamais une exception ni une valeur
    inventée.
    """
    return Bouteille(
        appellation=_texte(charge.get("appellation")),
        domaine=_texte(charge.get("domaine")),
        cuvee=_texte(charge.get("cuvee")),
        couleur=_enum(Couleur, charge.get("couleur"), Couleur.NON_DETERMINABLE),
        couleur_source=_enum(
            CouleurSource, charge.get("couleur_source"), CouleurSource.NON_LISIBLE
        ),
        effervescence=_enum(
            Effervescence, charge.get("effervescence"), Effervescence.NON_DETERMINABLE
        ),
        millesime=_texte(charge.get("millesime")),
        region=_texte(charge.get("region")),
        pays=_texte(charge.get("pays")),
        format=_enum(Format, charge.get("format"), Format.NON_DETERMINABLE),
        contenance_cl=_entier(charge.get("contenance_cl")),
        degre=_reel(charge.get("degre")),
        importateur=_texte(charge.get("importateur")),
        champs_a_verifier=[str(c) for c in charge.get("champs_a_verifier") or []],
        notes=str(charge.get("notes") or ""),
    )


def _texte(valeur: Any) -> str:
    if valeur is None:
        return NON_LISIBLE
    texte = str(valeur).strip()
    return texte or NON_LISIBLE


def _enum[E: StrEnum](enum_cls: type[E], valeur: Any, defaut: E) -> E:
    if valeur is None:
        return defaut
    try:
        return enum_cls(str(valeur).strip().casefold())
    except ValueError:
        return defaut


def _entier(valeur: Any) -> int | None:
    """Entier tolérant : « 75 », 75.0 et « 75.5 » donnent 75, 75 et 76.

    `int("75.5")` lève : un modèle répondant une contenance décimale se serait
    abstenu silencieusement alors qu'il avait lu quelque chose. On arrondit —
    le centilitre est l'unité utile, la demi-mesure n'a pas de sens ici.
    """
    try:
        return round(float(valeur))
    except (TypeError, ValueError):
        return None


def _reel(valeur: Any) -> float | None:
    try:
        return float(valeur)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
