# Parcours de test de l'application web (agent testeur-web)

Chaque parcours : ce qu'on fait, ce qu'on doit obtenir. Tout écart est un
problème, classé selon la grille de `.claude/agents/testeur-web.md`. Format
téléphone = 390×844 (tactile), ordinateur = 1440×900. Sauf mention, faire le
parcours aux deux formats, en débutant puis en expert. Au-delà du « ça
marche », juger à chaque étape la clarté, le nombre de gestes, le design et la
vitesse.

## Vérifications à faire sur CHAQUE écran

- Console JavaScript : aucune erreur (`page.on("console")`, `page.on("pageerror")`).
- Réponses réseau : aucun 500 ; un 4xx doit s'accompagner d'un message clair à l'écran.
- Aucun texte en anglais ni message technique (exception, `None`, `null`, JSON brut, nom de champ interne comme `a_verifier`).
- Téléphone : pas de défilement horizontal (`document.documentElement.scrollWidth <= innerWidth`), boutons d'au moins ~40 px de haut.
- Chaque action dit ce qu'elle a fait (message, changement visible).

## P1 — Accueil et nouvel inventaire
- Ouvrir `/app`. Attendu : liste des inventaires (vide au début), bouton « Nouvel inventaire », lien « Configuration ».
- Créer un inventaire « Vente test » pour « Maison Test ». Attendu : arrivée sur « Photographier les bouteilles ».
- Créer un inventaire sans nom. Attendu : refus avec une raison en français.

## P2 — Dépôt, mode appareil photo (téléphone)
- Sur l'input `#camera`, envoyer 3 photos une par une (`set_input_files`). Attendu : compteur « 3 photos », 3 vignettes.
- Quantité : « + » → 2. « Bouteille suivante ». Attendu : la bouteille passe dans la liste des précédentes, avec ses 3 photos et « × 2 » (ou équivalent).
- Deuxième bouteille, 1 photo, « Bouteille suivante ».
- Dépasser le plafond (5 photos alors que le maximum est 4). Attendu : refus clair, rien de perdu.
- Envoyer un fichier non-image (.txt renommé .jpg). Attendu : refusé avec sa raison.
- Envoyer une photo HEIC (en générer une avec pillow-heif si possible). Attendu : acceptée.
- Recharger la page en cours de dépôt. Attendu : rien de perdu, les bouteilles déjà photographiées sont là.

## P3 — Dépôt, mode galerie ou ordinateur
- Onglet « Galerie ou ordinateur ». Attendu : « Bouteille 1 » prête à recevoir ses photos.
- Bouteille 1 : 2 photos ; « Ajouter une bouteille » ; bouteille 2 : 2 photos.
- Revenir à l'onglet appareil photo puis à la galerie. Attendu : rien de perdu, numérotation continue.

## P4 — Vérifier et lancer
- « Vérifier et lancer ». Attendu : une carte par bouteille, photos dans l'ordre, quantités visibles.
- « Nouvelle bouteille à partir d'ici » sur la 2e photo d'une bouteille. Attendu : la bouteille est coupée en deux.
- « Rattacher à la précédente ». Attendu : réunies à nouveau.
- Retirer une photo ; supprimer une bouteille en attente (confirmation attendue).
- « Lancer l'analyse ». Attendu : suivi, progression qui avance seule jusqu'à « terminée ».

## P5 — Suivi et gestion de l'inventaire
- Pendant l'analyse : « Mettre l'analyse en pause » puis « Reprendre l'analyse ». Attendu : la progression s'arrête puis reprend.
- Une fois terminée : « Télécharger l'Excel » présent. Ouvrir le fichier (openpyxl) : une ligne par bouteille (ou par groupe fusionné identique), quantités correctes, en-têtes de la maison.
- « Ajouter des bouteilles » : 1 bouteille, ne PAS lancer. Attendu : message « bouteille(s) ajoutée(s) pas encore lancée(s) », bouton Excel remplacé par la raison ; `GET /inventaires/{id}/export` → 409 avec message français.
- Lancer la bouteille ajoutée. Attendu : Excel de nouveau disponible, avec une ligne de plus.
- Renommer (nom vide → refus clair ; nom valide → affiché partout).
- Archiver → l'inventaire passe dans « Archives » de l'accueil → le sortir des archives.
- Mettre à la corbeille → page de confirmation → l'inventaire disparaît, « Corbeille » sur l'accueil → Restaurer.

## P6 — Relecture (ordinateur, clavier ; puis rapidement au téléphone)
- « Relire les bouteilles ». Attendu : photos à gauche (toutes celles de la bouteille, `E` / `Maj+E` pour passer de l'une à l'autre, `Z` zoom), champs à droite.
- Corriger un champ texte (millésime), un champ liste (couleur), la quantité. Attendu : « Tout est enregistré » ; la valeur du modèle visible au survol ; « Revenir à la valeur du modèle » fonctionne.
- Saisie invalide (quantité 0). Attendu : refus expliqué à côté du champ, validation bloquée.
- `Entrée` hors champ : valider et passer à la suivante. `J`/`K`, flèches : naviguer sans valider.
- `?` : aide des raccourcis.
- Autres actions : Séparer (après quantité 3 → séparer 1 : une nouvelle bouteille juste après), Signaler un problème de photos (validation alors refusée ; lever le signalement), Réanalyser (le worker la refait), Retirer cette bouteille (confirmation ; elle disparaît de la relecture et de l'Excel ; la remettre depuis le récapitulatif).
- Récapitulatif : chiffres cohérents (corrections, temps de relecture > 0 même pour une bouteille seulement regardée).

## P7 — Clore et rouvrir
- « Clore l'inventaire » sans tout valider. Attendu : confirmation qui liste ce qui n'est pas validé ; après : lecture seule partout (relecture désactivée, pas d'ajout de bouteilles, corrections refusées avec message), Excel toujours téléchargeable.
- Rouvrir (confirmation). Attendu : modifiable à nouveau.

## P8 — Configuration
- `/app/configuration`, ouvrir « Maison Test ». Attendu : les colonnes, leur source, l'aperçu de ce qui est envoyé au modèle.
- Modifier la description d'une colonne, réordonner, ajouter une colonne expert, enregistrer. Attendu : nouvelle version annoncée.
- Erreur volontaire (colonne sans nom, valeur de liste en double). Attendu : refus clair, rien d'enregistré.
- Exporter le JSON ; réimporter un JSON invalide (refus clair) puis valide.
- Un inventaire créé AVANT la modification garde son ancienne config (même colonnes dans son Excel).

## P9 — Robustesse
- URL d'un inventaire ou d'une bouteille qui n'existe pas (`/app/inventaires/9999/suivi`). Attendu : page d'erreur en français, pas de trace.
- Bouteille d'un autre inventaire dans l'URL de relecture. Attendu : 404 propre.
- Double clic rapide sur « Lancer l'analyse », sur « Valider ». Attendu : pas de doublon, pas d'erreur.
- Deux onglets sur la même bouteille, deux corrections différentes. Attendu : avertissement « modifiée ailleurs ».
