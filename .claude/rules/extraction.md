---
paths:
  - "src/extract/**"
  - "src/normalize/**"
  - "src/compare/**"
  - "src/config/**"
  - "config/**"
  - "src/export/**"
  - "src/io/**"
  - "src/mesure/**"
  - "run_v0.py"
  - "mesurer_reduction.py"
---

# Règles : extraction, config, comparaison

## Champs
- Extraits : appellation, domaine/producteur, cuvée, couleur, couleur_source,
  effervescence, millésime, région, pays, format, contenance_cl, degré,
  importateur, champs_a_verifier, notes.
- Pilote : `id` (système), `quantite` (expert, 1 par défaut),
  `etat_etiquette` et `description_etat` (source `modele_best_effort` : proposés
  à partir de ce qui est VISIBLE, toujours ajoutés à `champs_a_verifier`).
- Niveau, capsule, bouchon : hors pilote. Le modèle ne décrit jamais ce qu'il ne
  voit pas.

## Lecture
- Extraction par modèle vision-langage en tool-use, sortie contrainte. Pas d'OCR
  classique.
- Millésime : lu, jamais déduit d'un style. Format : `non_determinable` par
  défaut sur un gros plan d'étiquette. `couleur_source` : observee | inferee |
  non_lisible.
- Le modèle liste ses incertitudes dans `champs_a_verifier` : c'est la file
  de relecture. `non_lisible` / `non_determinable` ne sont pas des bugs à faire
  disparaître (un format `non_determinable` presque partout sur des gros plans
  d'étiquette est normal).
- Noyau canonique (domaine, appellation, millésime, format) toujours extrait,
  quelle que soit la config ; la config ne change que l'affichage.
- À l'export, `non_lisible` / `non_determinable` = case vide + ligne surlignée.

## Extracteur
- Protocol `Extractor` : `run_v0`, le worker et les tests dépendent du
  Protocol, jamais d'une implémentation (VLM, fixtures, factice).

## Config par maison
- JSON versionné ; listes avec `code` stable + `libelle` affiché + description ;
  « Non déterminable » ajouté automatiquement ; sources modele |
  modele_best_effort | expert | systeme.
- Un inventaire reste lié à la version de config avec laquelle il a été créé.

## Comparaison et normalisation
- La comparaison mesure la sortie du modèle seule, sans les corrections, et est
  insensible à la casse et aux accents.
- Beaucoup d'écarts sont des conventions (« Domaine X » vs « X », cuvée dans
  l'appellation), pas des erreurs de lecture : on ne conclut rien sur la
  qualité de lecture avant d'avoir la couche de normalisation. On raisonne en
  score, jamais à l'œil.
- Listing manuel : un simple `load_manual(path)`, pas d'abstraction de formats
  tant qu'il n'y en a qu'un.
- Normalisation : fonctions pures `Bouteille -> Bouteille` composées ; vide tant
  qu'une session ne la demande pas.
