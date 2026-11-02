# Tour 10 — rapports des testeurs (2026-11-02)

## Testeur design (Opus)

0 bloquant, 0 majeur, 6 mineurs, 2 suggestions. Écrans ≈ 75 ms ; Ctrl+Entrée
vers la suivante 99 à 139 ms ; aucun 500, aucune erreur JavaScript, aucun
débordement ; rien de caché sous une barre fixe. Parcours P1 à P12 ✅. Aucune
régression des lots 41 et 42.

### Points du tour précédent

- [T9-D1] ✅ · [T9-D2] ✅ · [T9-D3] ✅ · [T9-D4] ✅ · [T9-D5] ✅ · [T9-D6] ✅
- [T9-D7] ✅ · [T9-D8] ✅ (hauteur : T10-S1) · [T9-D9] ✅ · [T9-D10] ✅
- [T9-S1] ✅ · [T9-S2] ✅

### Nouveaux points

- **T10-D1** mineur — Fichier non-image refusé pour le plafond quand la
  bouteille est pleine (mauvaise raison).
- **T10-D2** mineur — Pastille « Tout est enregistré » à côté de « Rien n'a été
  enregistré » (conflit), et sur un inventaire clos.
- **T10-D3** mineur — Récapitulatif : bouton principal à gauche.
- **T10-D4** mineur — « Analyse reprise. » encore affiché une fois l'analyse
  terminée.
- **T10-D5** mineur — « Retirer la colonne « nouvelle » » pour une colonne sans nom.
- **T10-D6** mineur — Guillemets séparés dans deux messages de configuration.
- **T10-S1** suggestion — Configuration au téléphone : cartes très hautes.
- **T10-S2** suggestion — Nouvel inventaire sans configuration : curseur dans
  un champ inutilisable.

## Testeur bugs (Sonnet)

0 bloquant, 0 majeur, 4 mineurs, 1 suggestion. Écrans ≈ 65 ms ; valider et
passer 115 ms ; export 104 ms ; aucun 500, aucune erreur JavaScript ; cibles
≥ 44 px. P10 non rejoué (couvert aux tours précédents). Aucune régression
(T7-D2, D3, D6, D12, T7-B4, T8-B2, B3, D5, D6, D7 revus).

### Points du tour précédent

- [T9-D1] ✅ · [T9-D2] ✅ · [T9-D3] ✅ · [T9-D4] ✅ · [T9-D5] ✅ · [T9-D6] ✅
- [T9-D7] ✅ · [T9-D8] ✅ · [T9-D9] ✅ · [T9-S1] ✅ (motif non borné : T10-B3)
- [T9-D10] ✅ (marque du testeur design ; non mesuré ici) · [T9-S2] ✅ (marque
  du testeur design ; non rejoué ici)

### Nouveaux points

- **T10-B1** mineur — Dépôt : quantité « 2.5 » ou « 1e3 » acceptée en silence
  (parseInt).
- **T10-B2** mineur — Vérifier : double clic sur « Couper » : deux coupes.
- **T10-B3** mineur — Motif de signalement ou de retrait sans limite de taille.
- **T10-B4** mineur — Suivi d'une réanalyse seule : temps écoulé et restant faux.
- **T10-S3** suggestion — Coupure pendant une correction au téléphone : l'erreur
  n'apparaît qu'en haut, hors de l'écran.
