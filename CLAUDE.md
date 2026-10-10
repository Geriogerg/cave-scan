# CLAUDE.md — Contexte (v0 → version pilote)

> Lu à chaque session. Fait autorité. En cas de doute métier, ce fichier tranche ;
> s'il est muet, demande — n'invente pas. Décisions techniques → `decisions.md`.
> La stratégie et la séquence des sessions sont dans `ROADMAP.md` : **pas besoin
> de le lire pour coder**. On ne construit que le périmètre du guide de session en
> cours (`docs/sessions/`).

## Ce qu'on construit

À partir des photos d'une bouteille (étiquette + contre-étiquette), extraire les
champs de catalogage, exporter un Excel au format d'une maison, et COMPARER ce
listing automatique au listing manuel de l'expert, champ par champ.

La v0 a livré son tableau de scores par champ. On la fait évoluer vers une
version pilote utilisée directement par l'expert d'une maison de vente (voir
decisions.md, section « Produit pilote »). Pas d'écran web tant qu'une session ne
le demande pas, et jamais d'estimation par le modèle.

Champs à extraire : appellation, domaine/producteur, cuvée, couleur,
couleur_source, effervescence, millésime, région, pays, format, contenance_cl,
degré, importateur, champs_a_verifier, notes.

Champs pilote ajoutés :
- `id` (système, stable) et `quantite` (expert, 1 par défaut) ;
- `etat_etiquette` et `description_etat` : **source `modele_best_effort`**. Le
  modèle propose une valeur à partir de ce qui est VISIBLE, et ces champs sont
  TOUJOURS ajoutés à `champs_a_verifier`. Il ne décrit jamais ce qu'il ne voit
  pas (bouchon, niveau sans rétroéclairage) : dans le doute, non déterminable.
- Niveau, capsule, bouchon : hors pilote.

## Le pipeline

photos → **extraction VLM** (sortie contrainte) → **normalisation** (identité pour
l'instant) → **stockage en base** (extraction + corrections de l'expert) →
**export Excel** (format maison, piloté par config) → **comparaison** au listing
manuel → tableau de scores.

Doit tourner **hors ligne en `--dry-run`** (fixtures, sans clé API) pour valider
la plomberie sans les vraies photos. La ligne de commande reste un point d'entrée
valide à chaque session, même quand l'application web existera.

**Travail par sessions** : chaque session a son guide dans `docs/sessions/`. Il
précise le périmètre de la session ; ce fichier-ci donne les règles permanentes.

## Données et persistance (règles permanentes)

- **La sortie brute du modèle est immuable.** Une correction de l'expert est un
  enregistrement séparé (champ, ancienne valeur, nouvelle valeur, auteur, date),
  jamais un écrasement. Valeur affichée = modèle, remplacée par la dernière
  correction.
- **Un inventaire est lié à une version figée de la config** : modifier le JSON
  ne change jamais l'export d'un inventaire existant.
- **Les images restent sur disque**, dans un stockage géré par l'outil (nommées
  par leur hash). La base ne stocke que les chemins et les empreintes.
- **Chaque extraction trace** le modèle, la version du prompt, les tokens et la
  durée : c'est la base du coût par bouteille.
- **Le schéma de base évolue par migrations versionnées**, jamais par
  suppression-recréation : on ne perd jamais les données d'un inventaire.
- Logique métier dans des **fonctions de service** sans état caché ; la ligne de
  commande et la future application web ne font que les appeler.

## API et tâches de fond (règles permanentes)

- **L'API est une couche fine** : chaque route valide l'entrée, appelle une
  fonction de service, met en forme la réponse. Aucune logique métier dans les
  routes ni dans le worker.
- **Le travail en attente vit dans la base**, pas en mémoire : un redémarrage du
  serveur ou du worker ne perd rien, et une bouteille restée « en cours » après
  un arrêt brutal est remise à extraire.
- **Une bouteille n'est jamais extraite deux fois en même temps.** Elle est
  réservée de façon atomique avant traitement.
- **Parallélisme borné et configurable** (quelques extractions simultanées), avec
  respect des limites de débit de l'API du modèle.
- **Les erreurs suivent la classification déjà décidée** (systématique → arrêt de
  l'inventaire ; passagère → nouvelles tentatives puis erreur sur la bouteille ;
  réponse inexploitable → erreur sur la bouteille).
- **Pas d'infrastructure lourde** pour le pilote (pas de Redis, pas de Celery) :
  une file d'attente en base et un processus worker suffisent pour 300
  bouteilles.
- **Les photos ne sont jamais servies comme un dossier statique** : une route
  vérifie que la photo appartient à l'inventaire demandé. Les métadonnées EXIF
  (dont la position GPS de la cave du client) ne sont jamais renvoyées par l'API.
- Tant que la connexion n'existe pas (session 7), le serveur n'écoute qu'en local
  par défaut. Seule exception : une option de développement explicite permet
  l'écoute sur le réseau local pour tester depuis un téléphone. Elle n'est
  jamais active par défaut et affiche un avertissement au démarrage.

## Écrans web (règles permanentes)

- **Pages générées côté serveur + HTMX**, dans la même application que l'API.
  Pas de framework JavaScript (React, Vue…). Du JavaScript simple seulement là
  où le navigateur l'impose : préparation des photos avant envoi, envoi fichier
  par fichier, progression.
- **Les pages appellent les fonctions de service**, comme l'API. Aucune logique
  métier dans les gabarits ni dans le JavaScript : un garde-fou (nombre impair,
  doublon, valeur hors liste) est toujours vérifié côté serveur, même s'il est
  aussi affiché côté navigateur.
- **Dépôt des photos pensé pour le téléphone** (une main, gros boutons, réseau
  instable) ; **relecture pensée pour l'ordinateur** (clavier, grand écran).
- **Interface en français, messages compréhensibles par l'expert**, jamais de
  message technique brut affiché.
- **Aucune photo n'est perdue en silence** : un envoi interrompu se reprend, un
  fichier refusé est signalé avec la raison.
- **L'ordre des photos est visible et corrigeable avant le lancement** : c'est le
  seul moyen d'éviter un décalage de toutes les paires.

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
- **Estimation : jamais remplie par le modèle.** Elle est vide à l'extraction et
  seul l'expert peut la saisir (comme toute colonne de source `expert`). Le
  modèle ne produit aucun prix.
- **Colonnes de source `expert` ou `systeme` : jamais envoyées au modèle.**
- **À l'export**, `non_lisible` et `non_determinable` s'affichent en case vide
  et la ligne est surlignée.
- **Pas de few-shot en v0** : on mesure le zero-shot. Des exemples dans le prompt
  rendraient le score du plancher ininterprétable.
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
- **Format par maison** : piloté par DONNÉES (config JSON dans `config/maisons/`,
  voir decisions.md, section « Produit pilote »), jamais une sous-classe par
  maison. Une nouvelle maison =
  un fichier de config.
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
- Ne fais jamais remplir l'estimation par le modèle. N'écris pas de règles de normalisation
  tant qu'une session ne le demande pas. Pas de few-shot. Si tu dois changer le
  contrat de `Bouteille` ou le schéma de base, arrête-toi et demande.
- Ne modifie jamais un test pour le faire passer sans accord, et n'affaiblis
  jamais un test qui vérifie une contrainte dure.
- Ne construis que le périmètre du guide de session en cours.
- Toute décision technique tranchée en cours de route → une ligne dans
  `decisions.md`.