# Tour 1 — rapports des testeurs (2026-10-13)

Synthèse fusionnée des deux passages (bugs : Sonnet ; design : Opus). Les
doublons entre les deux rapports sont réunis sous un seul identifiant. Captures
dans le scratchpad de la session (non versionnées).

## Mesures
Pages entre 15 et 250 ms (moyenne ≈ 55–60 ms). Relecture : 223 ms au
chargement, 849 ms du clic « Relire » à l'affichage ; enregistrer un champ
≈ 125 ms ; valider et passer ≈ 680 ms. Export Excel ≈ 500 ms. Aucune erreur
JavaScript, aucune perte de données constatée hors T1-B1.

## Bloquants
- **T1-B1** Vérifier les bouteilles : une quantité tapée dans « × » sans cliquer
  « Enregistrer » est perdue en silence au lancement (Excel Qté = 1). Piste :
  `_en_attente.html`, formulaire `quantite-attente`. Proposition : enregistrer
  au changement, supprimer le bouton.
- **T1-B2** Configuration : importer le JSON identique à la version active →
  500 (`ConfigInchangee` non interceptée dans `importer_un_fichier`).

## Majeurs
- **T1-M1** Relecture bloquée après « Revenir à la valeur du modèle » ou une
  saisie revenue à l'identique : indicateur figé, J/K/flèches inactifs 15 s,
  faux message « vérifiez la connexion », alerte en quittant. Piste :
  `relecture.js` (`cleDe(elt)` nul après échange ; `input` pose « modifié »
  sans `change`).
- **T1-M2** Excel, colonne « À vérifier » : clés internes (`etat_etiquette`…)
  au lieu des noms de colonnes de la maison.
- **T1-M3** Configuration : un refus d'enregistrement s'affiche en haut d'une
  page de ~10 000 px, hors écran ; la colonne fautive n'est pas signalée.
- **T1-M4** Configuration : messages techniques ou en anglais (« Expecting
  value », « « cle » doit être un identifiant… » alors que la clé découle du
  nom, colonnes désignées par leur clé).

## Mineurs
- **T1-m1** « Analyse terminée en X s » augmente à chaque affichage (durée non
  figée à la fin).
- **T1-m2** Restauré de la corbeille : « L'analyse est en pause » alors que tout
  est analysé.
- **T1-m3** Téléphone : barres d'actions qui débordent (suivi : « Récapitulatif »
  coupé ; configuration : défilement horizontal, « Enregistrer la version N »
  hors écran).
- **T1-m4** Galerie : première carte « Bouteille 2 » ; numéros différents entre
  dépôt et vérification.
- **T1-m5** Dépôt : compteur faux juste après une reprise d'envoi ; photos déjà
  reçues sans miniature ; vignette HEIC cassée.
- **T1-m6** Badges d'origine faux : Qté saisie au dépôt marquée « par défaut » ;
  après « Revenir », badge « corrigée » conservé.
- **T1-m7** Relecture au téléphone : en-tête écrasé, touches clavier affichées,
  Valider tout en bas (2645 px).
- **T1-m8** Relecture à l'ordinateur : Valider sous le bas de l'écran (y ≈ 1017
  pour 900).
- **T1-m9** Inventaire clos : « Valider / Déjà validée — passer » refusé (409)
  au lieu de simplement passer à la suivante.
- **T1-m10** Double clic sur Valider : 2e envoi en 409, reste sur la bouteille.
- **T1-m11** Messages en double (pause, clôture, signalement, réanalyse) ; pas de
  message après « Remettre dans l'inventaire ».
- **T1-m12** Noms techniques : conflit « « millesime » », URL invalide
  « inventaire_id », adresse inconnue en JSON brut, historique « Qté : vide → 1 ».
- **T1-m13** Renommer avec un nom vide : page d'erreur générique (contexte perdu)
  ; infinitif « Donner un nom ».
- **T1-m14** Incohérences visuelles : couleurs de liens, alignement du
  récapitulatif, barre d'actions loin de la colonne, barre de progression
  terne, « à saisir » vs « — à remplir — ».

## Suggestions
- **T1-S1** Vérifier au téléphone : vignettes plus petites, plusieurs par rangée.
- **T1-S2** Vocabulaire : « analysée(s) » plutôt qu'« extraite(s) » ; dépôt vide
  « 0 photo(s) … » ; « Quantité » à côté de « × ».
- **T1-S3** Configuration plus compacte (colonnes repliables) ; aperçu modèle
  lisible.
- **T1-S4** Dépôt : replier les envois réussis.
- **T1-S5** Accueil : avancement de la relecture (« 3 validées sur 6 »).
- **T1-S6** Configuration : clé dans un détail avancé.
- **T1-S7** Quantité > 100 : confirmation.
- **T1-S8** Clôture : lister les bouteilles non validées (lien récapitulatif).
- **T1-S9** Export d'un inventaire sans bouteille : refuser (409).
