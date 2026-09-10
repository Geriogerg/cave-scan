# CLAUDE.md — Contexte v0

> Lu à chaque session. Fait autorité. En cas de doute métier, ce fichier tranche ;
> s'il est muet, demande — n'invente pas. Décisions techniques → `decisions.md`.
> La stratégie long terme est dans `ROADMAP.md` : **pas besoin de la lire pour
> coder la v0**, et on ne construit rien qui n'y soit pas explicitement demandé.

## Ce qu'on construit (v0, rien d'autre)

À partir des photos d'une bouteille (étiquette(obligatoire) et/ou contre-étiquette), extraire les
champs de catalogage, exporter un Excel au format d'une maison, et COMPARER ce
listing automatique au listing manuel de l'expert, champ par champ.

**Le livrable de la v0 est le tableau de scores par champ.** Pas un produit, pas
une interface, pas d'estimation, pas de notation d'état.

Champs à extraire : appellation, domaine/producteur, cuvée, couleur,
couleur_source, millésime, région, pays, format, contenance_cl, degré,
importateur, champs_a_verifier, notes.

## Le pipeline

photos → **extraction VLM** (sortie contrainte) → **normalisation** (identité en
v0) → **export Excel** (format maison, piloté par config) → **comparaison** au
listing manuel → tableau de scores.

Doit tourner **hors ligne en `--dry-run`** (fixtures, sans clé API) pour valider
la plomberie sans les vraies photos.

## Contraintes dures (ne jamais violer)

- **Extraction par modèle vision-langage (tool-use, sortie contrainte)**, pas
  d'OCR classique. Le VLM lit ET range dans le bon champ en une passe.
- **Ne jamais deviner.** `non_lisible` (texte) et `non_determinable` (couleur,
  format) sont des valeurs correctes, pas des échecs. Millésime et format ne sont
  JAMAIS devinés : dans le doute → non lisible.
- **Millésime** : lu, jamais déduit d'un style. **Format** : `non_determinable`
  par défaut (illisible sur un gros plan d'étiquette). **couleur_source** :
  observee | inferee | non_lisible, pour distinguer lu et déduit.
- Le modèle liste ses incertitudes dans `champs_a_verifier` (file de relecture).
- **Colonne estimation : existe mais reste VIDE.** Le modèle ne produit aucun prix.
- **Normalisation = identité en v0** (pass-through + TODO). On écrira les règles
  en regardant les VRAIS écarts, pas à l'avance : les conventions dépendent de la
  maison, les inventer serait deviner.

## Pièges attendus (à connaître pour ne pas mal conclure)

- Une grande part des « erreurs » que la comparaison affichera seront des **écarts
  de convention, pas de lecture** : « Domaine Rossignol-Trapet » vs
  « Rossignol-Trapet », cuvée fondue ou non dans l'appellation, accents. La
  comparaison doit donc être insensible casse/accents, et on ne conclut rien sur
  la qualité de lecture avant d'avoir la couche de normalisation (plus tard).
- Le **format** sortira `non_determinable` presque partout s'il n'y a que des
  gros plans d'étiquette. C'est normal, pas un bug.

## Principes de conception (maintenabilité sans sur-ingénierie)

Objectif : pouvoir remplacer une brique sans casser le reste. Il vient d'abord du
**contrat de données partagé** (`Bouteille`, produit et consommé par tous) et du
**harnais de comparaison**, pas de l'empilement de patterns.

- **Une interface (`typing.Protocol`) là où la variation est certaine, du code
  plat ailleurs.** Règle : interface au 2e cas d'usage réel, jamais au 1er — sauf
  l'extracteur, dont le 2e cas est déjà acté (voir decisions.md).
- **Extracteur** : Protocol `Extractor` (`extract(...) -> Bouteille`).
  `run_v0` et les tests dépendent du Protocol, pas de l'implémentation VLM.
- **Format par maison** : piloté par DONNÉES (config YAML), jamais une sous-classe
  par maison. Une nouvelle maison = un fichier de config.
- **Normalisation** : liste de fonctions pures `Bouteille -> Bouteille` composées
  en pipeline (vide en v0), pas une fabrique de stratégies.
- **Chargeur de listing manuel** : simple `load_manual(path)`, pas d'abstraction
  de formats tant qu'il n'y en a qu'un.
- **Schéma et comparaison** : code plat, aucune abstraction spéculative.
- Type hints partout ; fonctions pures quand possible ; I/O et appels API isolés
  dans leurs modules dédiés.

## Règles de session

- Une tâche, un commit. **Rien ne se merge sans repasser la comparaison / les
  tests.** On raisonne en score, jamais à l'œil.
- `non_lisible` / `non_determinable` ne sont pas des bugs à faire disparaître.
- Ne remplis pas la colonne estimation. N'écris pas de règles de normalisation.
  Pas de few-shot. Si tu dois changer le contrat de `Bouteille`, arrête-toi et
  demande.
- Toute décision technique tranchée en cours de route → une ligne dans
  `decisions.md`.
