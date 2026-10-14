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
