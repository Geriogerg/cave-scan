# Tour 6 — rapports des testeurs (2026-10-14)

## Testeur design (Opus)

0 bloquant, 1 majeur, 11 mineurs, 4 suggestions. Écrans 15 à 90 ms (moyenne
≈ 40 ms), bouteille suivante < 300 ms, Excel de 29 bouteilles 163 ms ; aucun
500, aucune erreur JavaScript. Mesures tactiles prises avant toute capture.

### Points du tour précédent

- [T4-D10] ❌ régression au téléphone (✕ en ellipse pleine largeur) ; ✅ à l'ordinateur
- [T4-D4] ✅ · [T4-D14] ❌ en partie (T6-D6) · [T5-D1] ❌ en partie (carte déformée)
- [T5-D2] ✅ (reste : T6-D10) · [T5-D3] ✅ · [T5-DS1] ✅
- [T5-D4] ❌ en partie (T6-D7, T6-D8, régression T6-D1, « bouteilles identiques » seul)
- [T5-DS2] ✅ · [T5-D5] ✅ · [T3-D2] ✅ · [T5-DS3] ✅ · [T5-B6] ✅
- [T5-B7] ✅ (après rechargement : T6-D11) · [T5-B12] ❌ (T6-D3)
- [T5-B13] ✅ · [T5-B14] ✅ · [T5-B15] ✅
- [Choix n° 7] ✅ · [Choix n° 8] ✅ sauf la dernière bouteille (T6-X1)

### Nouveaux points

- **T6-X1** MAJEUR — L'avis « format / millésime vides » de la dernière bouteille
  se perd (récapitulatif) puis s'affiche dans une autre vente (sessionStorage).
- **T6-D1** mineur (régression lot 27) — Libellés longs coupés au téléphone
  (« Clore l'inventaire quand même », « Enregistrer la version 10 ») ; page
  élargie à 397 px.
- **T6-D2** mineur (régression) — ✕ de Vérifier au téléphone : ellipse
  106×40 px qui voile l'étiquette (règle « bouton pleine largeur » qui l'écrase).
- **T6-D3** mineur — Refus de quantité sur Vérifier : la carte se réorganise.
- **T6-D4** mineur — Dépôt au téléphone : refus de quantité qui casse la rangée
  et efface la saisie.
- **T6-D5** mineur — Après « Clore », succès affiché en jaune avec le texte du
  renvoi, en double avec le bandeau.
- **T6-D6** mineur — Accords oubliés (page Clore, « Lancer l'analyse de 1
  bouteille ? Leurs photos… », « les vérifier »).
- **T6-D7** mineur — Récapitulatif à l'ordinateur collé à gauche, barre centrée.
- **T6-D8** mineur — Nom de vente coupé sans « … » au toucher (inline-flex).
- **T6-D9** mineur — Guillemets séparés de leur mot en fin de ligne (suivi en
  pause, configuration).
- **T6-D10** mineur — Vérifier : retaper la même quantité après une coupure
  n'envoie rien, « réessayez » reste.
- **T6-D11** mineur — Galerie : photo déjà reçue rechoisie après rechargement :
  vignette grise sans explication.
- **T6-D12** mineur — Configuration : fil d'Ariane et sous-titre qui changent
  selon l'état.
- **T6-S1** suggestion — « ex. » : écrire « exemplaire(s) ».
- **T6-S2** suggestion — Motif avant son bouton (Signaler, Retirer).
- **T6-S3** suggestion — Récapitulatif au téléphone : libellé et valeur l'un
  sous l'autre.
- **T6-S4** suggestion — Dépôt au téléphone : « bouteilles identiques » seul.

P12 : décisions 1 à 6 sans défaut ; 7 ✅ ; 8 ✅ sauf T6-X1.

## Vérificateur (Sonnet)

R1 ✅ (réserves) · R2 ✅ · R2b ✅ · R3 ✅ · R4 ✅ · R5 ✅ · R6 ✅

- HEAD 404c453 : 717 passed (dépôt, copie `config/maisons/` vide, copie avec
  colonne renommée) ; dry-run OK ; totaux des commits des lots 22 à 30 égaux
  aux tests collectés ; 18 points « Corrigé » du tour 5 confirmés dans le code.
- R1 : les 48 identifiants du tour 4 sont dans tour5.md, id par id.
- R4 : décisions n° 7 et 8 appliquées et testées (mutations faites : les tests
  échouent).
- R6 : `main` avancé en avance rapide uniquement, aucun commit de fusion, aucun
  push ; `merge-tree` sans conflit.
- **T6-R1** — Ids en plusieurs lignes du journal (T4-D14, T4-DS5, T4-B19) : une
  seule marque ; statut R1 de etat_boucle.md périmé.
- **T6-R2** — decisions.md sans ligne pour les choix des lots 22 à 28 (répète
  T5-R8).
- **T6-R3** — etat_boucle.md : historique sans le tour 5.
- **T6-R4** — Choix n° 7 : import (409) et mesurer_reduction.py sans test ;
  bandeau qui cite « CAVE_SCAN_MAISON » ; « Ou indiquez-la avec --maison. »
  maladroit.
- **T6-R5** — Choix n° 8 : pas de test navigateur de l'avis ; test qui se saute
  en silence si les fixtures changent ; assertion « À vérifier » sous condition.
- **T6-R6** — 0171 non annoté (remplacé par 0182) ; README imprécis.
- **T6-R7** — « photo(s) » dans src/io/photos.py (messages pouvant atteindre
  l'expert).

## Testeur bugs (Sonnet)

0 bloquant, 1 majeur, 7 mineurs, 2 suggestions. Écrans ≈ 110 ms (le plus lent :
accueil à l'ordinateur, 228 à 409 ms avec 15 inventaires) ; Excel de 41
bouteilles 601 ms ; aucune erreur JavaScript ; aucun défilement horizontal ;
cibles ≥ 39 px (mesurées avant capture).

### Points du tour précédent

- [T5-B1] ✅ · [T5-B2] ✅ · [T5-B3] ✅ · [T5-B4] ✅ · [T5-B5] ✅ · [T5-B6] ✅
- [T5-B7] ✅ · [T5-B8] ✅ · [T5-B9] ✅ · [T5-B10] ✅ · [T5-B11] ✅ · [T5-B12] ✅
- [T5-B13] ✅ · [T5-B14] ✅ · [T5-B15] ✅ · [T5-D1] ✅ · [T5-D2] ✅ · [T5-D3] ✅
- [T5-D4] ✅ · [T5-D5] ✅ · [T5-DS1] ✅ · [T5-DS2] ✅ · [T5-DS3] ✅ · [T5-R5] ✅
- [T5-R1], [T5-R7], [T5-R8], [T5-R9] : non retestés (processus, documentation,
  tests ; comportements de T5-R9 vus sans défaut)
- [T4-D10] ❌ au téléphone (T6-B3) · [T4-D4] ❌ en partie (T6-B4) ·
  [T4-D14] ❌ en partie (T6-B6) · [T3-D2] ✅
- [Choix n° 7] ✅ (API : T6-B8) · [Choix n° 8] ✅

### Nouveaux points

- **T6-B1** MAJEUR — Au téléphone, le premier appui sur « Valider » ne valide
  pas quand un champ a le focus : la rangée de vignettes réapparaît à la perte
  du focus, le bouton bouge de 152 px entre l'appui et le relâchement, aucun
  `click`.
- **T6-B2** mineur — Message « Bouteille non validée : une saisie est refusée »
  qui reste après correction.
- **T6-B3** mineur — ✕ de Vérifier en ellipse au téléphone (= T6-D2).
- **T6-B4** mineur — Barre de navigation plus haute sur la première et la
  dernière bouteille (boutons inactifs sans mots courts).
- **T6-B5** mineur — « Bouteille suivante » sans photo : aucun effet, aucun
  message.
- **T6-B6** mineur — « (s) » restants (Clore, Séparer, historique, API export).
- **T6-B7** mineur — « Leurs photos » pour 1 bouteille ; « Ctrl+Entrée » au
  téléphone ; « doute du modèle » sur une bouteille pas lue ; galerie : quantité
  refusée remise à 1.
- **T6-B8** mineur — Plusieurs configurations : l'API crée quand même un
  inventaire (la maison y est désignée explicitement).
- **T6-B9** suggestion — « Ajouter une valeur » sans focus sur la nouvelle ligne.
- **T6-B10** suggestion — Inventaire clos : deux encadrés presque identiques ;
  clôture sans la liste des non validées.
