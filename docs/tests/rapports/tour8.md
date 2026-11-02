# Tour 8 — rapports des testeurs (2026-11-02)

## Testeur bugs (Sonnet)

0 bloquant, 0 majeur, 2 mineurs, 1 suggestion. Écrans ≈ 120 ms ; valider d'un
appui puis changement de page ≈ 0,9 s ; aucun 500, aucune erreur JavaScript ;
aucun défilement horizontal.

### Points du tour précédent

- [T7-B1 / T7-D1] ✅ · [T7-B2 / T7-D9] ✅ · [T7-B3 / T7-D5] ✅ · [T7-D2] ✅
- [T7-D3] ✅ · [T7-D4] ✅ · [T7-D6] ✅ · [T7-D7] ✅ · [T7-D8] ✅ · [T7-D12] ✅
- [T7-B4] ✅ · non retestés : T7-D10, T7-D11, T7-S1, T7-S3, T7-R4, T7-R5

### Nouveaux points

- **T8-B1** mineur — Séparer refusé : la page de refus vit à l'adresse du POST.
  Déjà écarté (T4-B20 : Séparer et l'import gardent leur page de refus, leurs
  messages dépendent de la saisie) ; pas d'élément nouveau.
- **T8-B2** mineur — Dépôt : l'avertissement « ouvert dans un autre onglet »
  reste après la fermeture de l'autre onglet.
- **T8-B3** suggestion — Renommage de plus de 200 caractères (hors du champ
  limité) : page « Action impossible » au lieu du suivi.

## Vérificateur (Sonnet)

R1 ⚠️ · R2 ✅ · R2b ✅ · R3 ✅ · R4 ✅ · R5 ✅ · R6 ✅

- HEAD a4093cc : 729 passed (dépôt, copie `config/maisons/` vide) ; dry-run OK ;
  totaux des lots 36 à 38 égaux aux tests collectés ; 18 lignes « 7 | Corrigé »
  confirmées dans le code ; 0189 bis, 0194, 0191 réparées ; 0195 à 0197 présentes.
- **T8-R1** — Journal sans ligne pour T7-R1, R2, R3, R6 ; tour7.md abrège T6-R2,
  R3, R6 (le grep échoue).
- **T8-R2** — Statut R1 de etat_boucle.md périmé.
- **T8-R3** — depot.py : « Quantité invalide » pour une quantité vide (lecture du
  code ; chemin typé en entier).
