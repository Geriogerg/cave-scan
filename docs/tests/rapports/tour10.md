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
