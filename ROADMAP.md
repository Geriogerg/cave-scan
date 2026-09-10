# ROADMAP — stratégie et suites (hors v0)

> Claude Code n'a PAS besoin de lire ce fichier pour coder la v0. Il garde la
> trace des décisions stratégiques et de ce qui vient après, pour nous deux. On
> ne construit rien d'ici tant que la v0 n'a pas livré son tableau de scores.

## Positionnement

- B2B d'abord : le mur d'entrée est l'accès aux maisons et aux données annotées,
  pas la technique. Cycle lent mais compatible side project.
- Grand public plus tard, comme canal d'acquisition (modèle iDealwine), pas comme
  business, et seulement une fois la notation d'état bonne.
- Wedge = extraction/lotting (se vend, douleur quotidienne). Moat = notation
  d'état (nous rend durs à copier). On entre par le wedge, on greffe le moat.
- Livraison manuelle assistée avant toute automatisation.

## Les 3 briques

1. Identification (étiquette → référence). Se rattache au LWIN (Liv-ex), pas à un
   référentiel maison.
2. Valorisation (prix conditionnel à l'état). Problème de données, jamais produit
   depuis une photo. Après la v1.
3. Notation d'état (niveau, étiquette, capsule, bouchon). Best-effort en v1,
   fiabilisée ensuite. Niveau = candling requis ; bouchon quasi invisible.

## Après la v0 (ordre indicatif)

1. Sur données réelles : câbler load_manual() + la vraie config maison, lancer
   l'extraction, lire les scores.
2. Écrire la couche de normalisation en regardant les vrais écarts + rattachement
   LWIN pour les entités (déterministe, préféré au few-shot).
3. Few-shot en contexte seulement pour le flou de convention irréductible, avec
   exemples réels tenus hors du set d'éval. Fine-tuning au frigo tant que ce
   chemin n'a pas plafonné.
4. v1 : assistant de lotting livré à une maison pilote, externe/asynchrone,
   colonne état best-effort. Estimation toujours exclue de la photo.
5. Plus tard : estimation conditionnelle à l'état, regroupement de lots, visuels
   de catalogue, intégration SI (nécessite de sortir du mode side project).

## Pièges stratégiques

- Estimation par la photo : jamais.
- « Apprend tout seul » vendu à un client : non, c'est un template de config.
- Authentification : jamais « certifié » ; détection d'anomalie avec expert.
- Pas de client en production tant qu'on ne peut pas assurer support/correctifs.
- Pilotes gratuits : en échange du droit de garder la donnée annotée, avec une
  date où l'on pose la question du prix.

## Signal qui compte

Pour la v1 : une maison pilote qui renvoie une DEUXIÈME consignation sans qu'on
la relance. Pas le chiffre d'affaires.
