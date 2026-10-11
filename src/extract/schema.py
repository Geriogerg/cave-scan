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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # import de typage seul : la config dépend de ce module, pas l'inverse
    from src.config.maison import Colonne, ConfigMaison

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
    """Une bouteille physique : ce que le modèle a lu, et ce que posent l'outil
    et l'expert. Une ligne interne = une bouteille (decisions.md 0016).

    Les valeurs par défaut des champs lus sont toutes des abstentions : une
    `Bouteille()` vide n'affirme rien. C'est volontaire — un champ non renseigné
    ne doit jamais passer pour une lecture.

    Champs de liste (couleur, effervescence, format) : un CODE stable. C'est la
    valeur de l'enum v0, ou le code du vocabulaire de la maison quand sa config
    redéfinit le champ (decisions.md 0054). Les membres d'enum étant des `str`,
    les deux s'écrivent et se comparent de la même façon.
    """

    # Système : posé par le pipeline, jamais par le modèle (decisions.md 0016).
    id: str = ""

    appellation: str = NON_LISIBLE
    domaine: str = NON_LISIBLE
    cuvee: str = NON_LISIBLE
    couleur: str = Couleur.NON_DETERMINABLE
    couleur_source: CouleurSource = CouleurSource.NON_LISIBLE
    effervescence: str = Effervescence.NON_DETERMINABLE
    millesime: str = NON_LISIBLE
    region: str = NON_LISIBLE
    pays: str = NON_LISIBLE
    format: str = Format.NON_DETERMINABLE
    contenance_cl: int | None = None
    degre: float | None = None
    importateur: str = NON_LISIBLE
    champs_a_verifier: list[str] = field(default_factory=list)
    notes: str = ""

    # Expert : jamais envoyé au modèle, 1 par défaut (decisions.md 0017).
    quantite: int = 1

    # Colonnes propres à la maison (sa config), par clé ; codes pour les listes.
    valeurs_maison: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Vue dict sérialisable (enums réduits à leur valeur texte)."""
        sortie: dict[str, Any] = {}
        for f in fields(self):
            valeur = getattr(self, f.name)
            if isinstance(valeur, StrEnum):
                valeur = valeur.value
            elif isinstance(valeur, list):
                valeur = list(valeur)
            elif isinstance(valeur, dict):
                valeur = dict(valeur)
            sortie[f.name] = valeur
        return sortie


# Ordre canonique des champs, tel que déclaré sur la dataclass.
CHAMPS: tuple[str, ...] = tuple(f.name for f in fields(Bouteille))

# Champs que le pipeline pose lui-même : jamais demandés au modèle, et ignorés
# s'il les renvoie quand même (decisions.md 0059).
CHAMPS_HORS_MODELE: tuple[str, ...] = ("id", "quantite", "valeurs_maison")

# Champs que le modèle remplit : ce sont eux, et eux seuls, que le schéma exige.
CHAMPS_MODELE: tuple[str, ...] = tuple(c for c in CHAMPS if c not in CHAMPS_HORS_MODELE)

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

# Questions posées au modèle qui ne sont pas des champs de `Bouteille` : elles
# pilotent le pipeline. Réponse « non » à la cohérence de la paire de photos ->
# DOUTE_PAIRE_PHOTOS dans `champs_a_verifier` (guide, étape 4.4).
PHOTOS_MEME_BOUTEILLE = "photos_meme_bouteille"
CHAMPS_TECHNIQUES: tuple[str, ...] = (PHOTOS_MEME_BOUTEILLE,)
DOUTE_PAIRE_PHOTOS = "paire_photos"

# Nature des champs v0 que le modèle remplit et qu'une config de maison peut
# redéfinir (description, vocabulaire). Sert à refuser une config qui en
# changerait la nature — un millésime ne devient pas une liste par mégarde.
NATURE_DES_CHAMPS: dict[str, str] = {
    "appellation": "texte",
    "domaine": "texte",
    "cuvee": "texte",
    "couleur": "liste",
    "effervescence": "liste",
    "millesime": "texte",
    "region": "texte",
    "pays": "texte",
    "format": "liste",
    "contenance_cl": "nombre",
    "degre": "nombre",
    "importateur": "texte",
    "notes": "texte",
}


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
                PHOTOS_MEME_BOUTEILLE: {
                    "type": "string",
                    "enum": ["oui", "non", NON_DETERMINABLE],
                    "description": (
                        "Les photos fournies montrent-elles bien la MÊME bouteille ? "
                        "Elles ont été regroupées par l'expert, une erreur de "
                        "regroupement est possible. « non » si elles semblent "
                        "appartenir à deux bouteilles différentes (producteur, "
                        "appellation ou millésime incompatibles, bouteilles "
                        "visiblement distinctes) ; « oui » si rien ne s'y oppose ; "
                        f"« {NON_DETERMINABLE} » s'il n'y a qu'une photo ou si rien "
                        "ne permet de trancher."
                    ),
                },
            },
            "required": [*CHAMPS_MODELE, *CHAMPS_TECHNIQUES],
        },
    }


def schema_extraction(config: ConfigMaison | None = None) -> dict[str, Any]:
    """Le schéma réellement envoyé au modèle pour une maison (guide, étape 4.2).

    = les champs v0 (CLAUDE.md, « Champs à extraire ») + les colonnes de la
    config dont la source est `modele` ou `modele_best_effort` (decisions.md
    0061). Conséquences :
    - le noyau canonique fait partie des champs v0 : il est toujours extrait,
      même si la config ne l'affiche pas (0021) ;
    - une colonne de config qui porte le nom d'un champ v0 en redéfinit la
      description et, pour une liste, le vocabulaire (ses codes) ;
    - les colonnes `expert` et `systeme` ne sont JAMAIS ajoutées ;
    - la consigne d'abstention est ajoutée par le code à chaque colonne : la
      règle « ne jamais deviner » ne dépend pas de la rédaction de la maison.

    Sans config : le schéma v0, inchangé.
    """
    outil = tool_schema()
    if config is None:
        return outil

    proprietes = outil["input_schema"]["properties"]
    for colonne in config.colonnes_modele:
        proprietes[colonne.cle] = propriete_modele(colonne)
    outil["input_schema"]["required"] = list(proprietes)
    return outil


def propriete_modele(colonne: Colonne) -> dict[str, Any]:
    """Une colonne de config traduite en propriété du schéma : EXACTEMENT ce que
    le modèle reçoit pour elle (montré tel quel par la page Configuration)."""
    morceaux = [colonne.description] if colonne.description else []
    if colonne.regle:
        morceaux.append(f"Consigne : {colonne.regle}")
    if colonne.source == "modele_best_effort":
        morceaux.append(
            "Proposition fondée UNIQUEMENT sur ce qui est visible sur les photos, "
            "qu'un expert relira : ne rien décrire de non visible."
        )

    if colonne.type == "liste":
        valeurs = " | ".join(
            f"{valeur.code} — {valeur.description}" if valeur.description else valeur.code
            for valeur in colonne.valeurs
        )
        morceaux.append(f"Valeurs possibles : {valeurs}.")
        morceaux.append(
            f"Si rien de visible ne permet de trancher : « {NON_DETERMINABLE} ». Ne jamais deviner."
        )
        return {"type": "string", "enum": list(colonne.codes), "description": " ".join(morceaux)}

    if colonne.type == "nombre":
        morceaux.append("Uniquement si c'est écrit ou visible. Sinon : null. Ne jamais deviner.")
        return {"type": ["number", "null"], "description": " ".join(morceaux)}

    morceaux.append(
        f"Si ce n'est pas lisible ou visible sur les photos : « {NON_LISIBLE} ». Ne jamais deviner."
    )
    return {"type": "string", "description": " ".join(morceaux)}


def from_tool_input(charge: dict[str, Any], config: ConfigMaison | None = None) -> Bouteille:
    """Construit une `Bouteille` à partir de la charge utile d'un appel d'outil.

    Tolérante par conception : une clé manquante retombe sur l'abstention, une
    valeur d'enum inconnue devient ``non_determinable``. Un modèle qui répond
    de travers doit produire une abstention, jamais une exception ni une valeur
    inventée.

    Source NON FIABLE : seuls les champs du modèle sont lus. `id`, `quantite`
    ou une colonne expert renvoyés par le modèle sont ignorés — il ne décide
    jamais de ce que posent l'outil ou l'expert (decisions.md 0059).

    Avec la config d'une maison : son vocabulaire fait foi pour les listes
    qu'elle redéfinit, ses colonnes propres vont dans `valeurs_maison`, et
    chaque colonne best effort est ajoutée à `champs_a_verifier` — par le code,
    toujours, sans dépendre du modèle (CLAUDE.md, decisions.md 0062).
    """
    redefinies = {colonne.cle: colonne for colonne in config.colonnes_modele} if config else {}

    def liste[E: StrEnum](champ: str, enum_cls: type[E], defaut: E) -> str:
        colonne = redefinies.get(champ)
        if colonne is not None:
            return colonne.code_depuis(charge.get(champ)) or NON_DETERMINABLE
        return _enum(enum_cls, charge.get(champ), defaut)

    bouteille = Bouteille(
        appellation=_texte(charge.get("appellation")),
        domaine=_texte(charge.get("domaine")),
        cuvee=_texte(charge.get("cuvee")),
        couleur=liste("couleur", Couleur, Couleur.NON_DETERMINABLE),
        couleur_source=_enum(
            CouleurSource, charge.get("couleur_source"), CouleurSource.NON_LISIBLE
        ),
        effervescence=liste("effervescence", Effervescence, Effervescence.NON_DETERMINABLE),
        millesime=_texte(charge.get("millesime")),
        region=_texte(charge.get("region")),
        pays=_texte(charge.get("pays")),
        format=liste("format", Format, Format.NON_DETERMINABLE),
        contenance_cl=_entier(charge.get("contenance_cl")),
        degre=_reel(charge.get("degre")),
        importateur=_texte(charge.get("importateur")),
        champs_a_verifier=[str(c) for c in charge.get("champs_a_verifier") or []],
        notes=str(charge.get("notes") or ""),
    )

    for colonne in redefinies.values():
        if colonne.cle not in NATURE_DES_CHAMPS:
            bouteille.valeurs_maison[colonne.cle] = _valeur_de_colonne(colonne, charge.get(colonne.cle))
        if colonne.source == "modele_best_effort" and colonne.cle not in bouteille.champs_a_verifier:
            bouteille.champs_a_verifier.append(colonne.cle)

    # Photos d'une autre bouteille selon le modèle : signalées pour relecture,
    # jamais corrigée en silence (guide, étape 4.4 ; decisions.md 0069).
    if str(charge.get(PHOTOS_MEME_BOUTEILLE) or "").strip().casefold() == "non":
        if DOUTE_PAIRE_PHOTOS not in bouteille.champs_a_verifier:
            bouteille.champs_a_verifier.append(DOUTE_PAIRE_PHOTOS)
        signalement = (
            "Le modèle signale que ces photos ne semblent pas montrer la même "
            "bouteille : vérifier le regroupement des photos."
        )
        bouteille.notes = f"{bouteille.notes} {signalement}".strip()

    return bouteille


def _valeur_de_colonne(colonne: Colonne, brute: Any) -> Any:
    """Valeur d'une colonne propre à la maison, avec sa convention d'abstention."""
    if colonne.type == "liste":
        return colonne.code_depuis(brute) or NON_DETERMINABLE
    if colonne.type == "nombre":
        return _reel(brute)
    return _texte(brute)


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
