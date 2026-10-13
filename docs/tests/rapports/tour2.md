# Tour 2 — rapports des testeurs (2026-10-13)

Deux passages : **bugs** (Sonnet, identifiants T2-B…) et **design** (Opus,
T2-D…). Tous les points « corrigés » du tour 1 ont été revérifiés : corrigés,
sauf T1-m7 (aide des photos au téléphone, phrase à trous) et une régression de
T1-S3 (colonnes de configuration qui se replient), repris ci-dessous.

## Mesures
Pages entre 20 et 200 ms (moyenne ≈ 45–58 ms) ; valider et passer 84–650 ms ;
Séparer ≈ 1,2 s. Aucune erreur JavaScript hors T2-B1, aucun défilement
horizontal.

## Passage bugs
- **T2-B1** BLOQUANT — Quantité démesurée (99999999999999999999) : 500 sur
  « Vérifier », en relecture et au dépôt (OverflowError SQLite) ; « Lancer »
  muet ; en relecture, faux « connexion interrompue ».
- **T2-B2** MAJEUR — Configuration : toutes les colonnes se replient après
  chaque action (régression T1-S3).
- **T2-B3** MINEUR — Téléphone : phrase d'aide des photos à trous (reste T1-m7).
- **T2-B4** MINEUR — Durée d'analyse allongée par une réanalyse.
- **T2-B5** MINEUR — Texte sans plafond de longueur ; estimation « abc » acceptée.
- **T2-B6** MINEUR — Dépôt : la bouteille vide s'appelle « Bouteille 1 » alors
  que la galerie a déjà une « Bouteille 1 ».
- **T2-B7** SUGGESTION — Cibles tactiles : « Revenir à la valeur du modèle »
  (19 px), sélecteur de fichier (21 px).
- **T2-B8** SUGGESTION — Textes cités qui ressemblent à des boutons.
- (Incident du testeur : `lancer_appli_isolee.py --help` a créé un dossier
  `--help/` dans le dépôt, supprimé par lui ; le lanceur doit refuser `-…`.)

## Passage design
- **T2-D1** MINEUR — Dépôt ouvert dans un autre navigateur : numérotation qui
  repart à 1, bouteilles en attente non listées, résumé écrasé.
- **T2-D2** MINEUR — Configuration : après ↑/↓, la page saute et la colonne
  déplacée disparaît (même cause que T2-B2).
- **T2-D3** = T2-B3.
- **T2-D4** = T2-B4.
- **T2-D5** MINEUR — Conflit : le message s'affiche sous un autre champ ; la
  saisie de ce champ est perdue ; indicateur incohérent.
- **T2-D6** MINEUR — « Donner un nom » à la création ; « entier ≥ 1 attendu » ;
  sur « Vérifier », le refus ne dit pas quelle bouteille.
- **T2-D7** MINEUR — « à saisir » / « — à remplir — » pour une liste expert.
- **T2-D8** MINEUR — Dépôt : refus de photo caché sous la barre ; « voir la
  raison » n'est pas un lien ; nom de fichier coupé.
- **T2-D9** MINEUR — Incohérences : nom d'inventaire lien ou texte selon
  l'écran ; « Quantité / × / Qté » ; barre de « Vérifier » ; bouton grisé
  pleine largeur au suivi ; « ses 1 photo(s) » ; guillemet orphelin.
- **T2-D10** MINEUR — État « archivé » invisible ; cartes d'archives sans
  avancement ; « se met à jour toute seule » faux en pause.
- **T2-D11** MINEUR — Relecture : pas de confirmation après validation, focus
  perdu.
- **T2-D12** MINEUR — Récapitulatif : un retour au modèle compté comme
  correction ; nom de fichier JSON montré ; « noyau » non expliqué ; libellé de
  « Séparer » coupé ; message de doublon de liste obscur.
- **T2-DS1** SUGGESTION — Ordinateur : ouvrir le dépôt en mode galerie.
- **T2-DS2** SUGGESTION — « Vérifier » plus compact à l'ordinateur.
- **T2-DS3** SUGGESTION — Relecture au téléphone : photo visible pendant la
  saisie ; Valider recouvre le champ en cours.
- **T2-DS4** SUGGESTION — Dépôt : « Vérifier et lancer » secondaire tant
  qu'aucune bouteille n'est terminée.
- **T2-DS5** SUGGESTION — Barres d'actions moins hautes au téléphone
  (configuration : 290 px).
