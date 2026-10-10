# Session 6 — Configuration par maison, groupes de photos, corrections

Prérequis : session 5 terminée, produit analysé (2026-10-10). Consigne de
l'utilisateur, puis les choix tranchés avec lui avant l'exécution
(2026-10-10 / 2026-10-11).

---

## 1. Configuration par maison

- La maison peut importer son fichier JSON de config, OU utiliser une page
  « Configuration » dans l'application pour ajouter, modifier, réordonner et
  supprimer des colonnes : nom, type, source, valeurs possibles avec leur
  description, règle éventuelle.
- La page génère automatiquement une nouvelle version de la config, validée
  comme aujourd'hui, puis utilisée par l'application. Export du JSON possible.
- Un inventaire reste lié à la version de config avec laquelle il a été créé.
- Afficher un aperçu de ce qui sera envoyé au modèle pour chaque colonne.
- Retirer l'exemple de réponse présent dans la description d'état de la config
  de test (c'est du few-shot, interdit par CLAUDE.md).
- Ajouter à la config de test : niveau et état de la capsule (best effort,
  « non déterminable » sans photo adaptée), caisse (CBO, carton, sans) et
  numéro de lot (saisi par l'expert).

## 2. Une bouteille = un groupe de photos

On abandonne l'appariement étiquette / contre-étiquette par ordre.

- Nombre de photos libre par bouteille (étiquette, contre-étiquette si elle
  existe, bouchon, capsule, bouteille entière…), avec un plafond configurable
  pour maîtriser le coût.
- Mode appareil photo : prise de photos en continu pour la bouteille en cours,
  compteur visible, bouton « Bouteille suivante », saisie de la quantité
  (« × N ») au moment de la capture.
- Mode galerie ou ordinateur : « Bouteille 1 → ajouter ses photos »,
  « Bouteille 2 → ajouter ses photos », etc.
- Toutes les photos d'une bouteille sont envoyées au modèle dans le même appel,
  numérotées ; le modèle n'utilise que ce qu'il voit.
- L'option « étiquettes seules » et le tri par date de prise de vue
  disparaissent.
- Migration des inventaires existants : chaque paire devient un groupe de deux
  photos, sans toucher aux extractions ni aux corrections existantes.
- L'écran de relecture affiche toutes les photos de la bouteille.

## 3. Problèmes identifiés à corriger

- Photos HEIC de l'iPhone refusées : les lire.
- Une bouteille dont l'analyse a échoué ne peut jamais être validée : la rendre
  validable une fois ses champs obligatoires saisis à la main, pour ne plus
  bloquer l'inventaire.
- Le temps de relecture n'est compté qu'à la validation : le compter aussi
  pour les bouteilles ouvertes mais pas encore validées.
- Une séparation décale la comparaison ligne à ligne avec le listing de
  l'expert : rendre la comparaison indépendante de ces lignes ajoutées.
- Inventaires non modifiables : permettre d'ajouter des bouteilles après le
  lancement, de renommer, d'archiver et de supprimer un inventaire (avec
  confirmation).
- Conflit de port au démarrage avec un message technique en anglais : passer
  sur un port libre ou expliquer le problème en français.

## 4. Cycle de vie d'un inventaire (ajouté en cours de cadrage)

On peut commencer un inventaire, l'arrêter, le reprendre, le modifier, enlever
des bouteilles, en rajouter… et le CLORE quand on est sûr que c'est bon.

- Dépôt interruptible à tout moment, repris plus tard (même appareil ou un
  autre). Analyse : « Mettre en pause » / « Reprendre ».
- Ajouter des bouteilles à tout moment ; « Retirer la bouteille » (rien n'est
  effacé : elle sort de la relecture, de l'export et des comptes, reste dans
  l'historique, peut être remise).
- « Clore l'inventaire » : lecture seule ensuite (plus de correction, d'ajout
  ni de retrait), export toujours possible. Rouvrir est permis, avec
  confirmation et trace.
- Valider bouteille par bouteille reste FACULTATIF.

## 5. Export Excel

- Un Excel contient TOUJOURS une ligne par bouteille (retirées exceptées).
- Bouteille en erreur d'analyse : sa ligne, surlignée d'une couleur distincte,
  « Erreur d'analyse » dans la colonne « À vérifier », jamais fusionnée ;
  saisie à la main par l'expert : « Saisie manuelle ».
- Export REFUSÉ, avec un message, tant qu'une bouteille n'est pas encore
  analysée (à extraire, en cours) ou qu'une bouteille ajoutée n'est pas lancée.
  Vérifié côté serveur (écran, API, ligne de commande).
- Clore suit la même condition ; clore sans avoir tout validé est permis, avec
  un avertissement qui dit ce qui reste.
- Option de config : une colonne calculée « Relue » (oui / vide).

## 6. Choix tranchés

1. Supprimer un inventaire = corbeille : il disparaît des listes et du worker,
   rien n'est effacé, il se restaure.
2. Champs obligatoires d'une bouteille en erreur = colonnes du noyau canonique
   présentes dans la config de la maison (domaine, appellation, millésime,
   format).
3. Plafond de photos : `photos_max_par_bouteille` dans la config de la maison,
   4 par défaut, de 1 à 10, modifiable dans la page Configuration.
4. Caisse : saisie par l'expert.
5. Regroupement de l'export : colonnes expert autorisées ; la config de test
   regroupe aussi sur lot, caisse, niveau, capsule.
6. Ligne de commande : un sous-dossier par bouteille ; une photo posée à la
   racine = une bouteille d'une photo. `--sans-contre` devient une option
   remplacée (message).
7. Clore : à tout moment, avec un avertissement (toutes les bouteilles doivent
   avoir leur ligne, cf. §5).
8. Rouvrir un inventaire clos : permis, avec confirmation et trace.

## 7. Ne pas traiter dans cette session

Hébergement, connexion, HTTPS, sauvegardes, accès payant à l'API, vue tableau,
suggestions d'orthographe, ligne de catalogue, lots (au-delà de la colonne
« numéro de lot »), recherche entre ventes.

## 8. Règles

- Respecter CLAUDE.md et `.claude/rules/`. Les passages devenus faux
  (« étiquette + contre-étiquette », « ordre des paires », « date de prise de
  vue ») sont mis à jour à l'étape qui les rend faux, après accord sur le diff.
  Étape 0 : seulement le cycle de vie de l'inventaire et l'export (demande du
  2026-10-11).
- Chaque décision dans `decisions.md`, celles qu'elle remplace archivées avec
  un renvoi.
- Toute modification du schéma passe par une migration ; aucune extraction ni
  correction existante n'est modifiée ou perdue.
- Un commit par étape, avec diff et sortie des tests.
- Tests existants adaptés : seulement ceux listés dans le plan validé
  (appariement, signature de l'extracteur, HEIC, migration, inverser les
  photos, libellés « paire », bouteille en erreur validable). Aucun test d'une
  contrainte dure n'est affaibli ; tout autre test qui casse : arrêt et
  explication.

## 9. Étapes

0. Cadre (ce guide, diff de CLAUDE.md et des règles).
1. Démarrage : port libre ou message en français ; worker lancé après le port.
2. HEIC.
3. Format de la config, config de test, service de configuration.
4. Page Configuration.
5. Groupes de photos : données (migration), extraction, ligne de commande.
6. Groupes de photos : dépôt sur téléphone et ordinateur.
7. Relecture avec toutes les photos.
8. Cycle de vie : ajouter, retirer, renommer, archiver, corbeille, clore,
   rouvrir, pause.
9. Relecture : bouteille en erreur validable, temps sans validation,
   comparaison sans les bouteilles séparées ; export (une ligne par bouteille).
10. README, decisions.md, tests complets, dry-run, vérifications.
