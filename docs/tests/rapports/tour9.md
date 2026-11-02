# Tour 9 — rapports des testeurs (2026-11-02)

## Testeur bugs (Sonnet)

0 bloquant, 0 majeur, 0 mineur, 1 suggestion. Écrans ≈ 130 ms ; valider et
passer 199 ms ; aucun 500, aucune erreur JavaScript, aucun défilement
horizontal ; cibles tactiles ≥ 44 px de haut. Tous les parcours P1 à P12 ✅.
Aucune régression des tours 5 à 7 (T7-D3, T7-D6, T7-B4, T7-D12, T7-D7, T7-D8
revus).

### Points du tour précédent

- [T8-D1] ✅ · [T8-D2] ✅ · [T8-D3] ✅ · [T8-D4] ✅ · [T8-B2] ✅ · [T8-D5] ✅
- [T8-B3] ✅ · [T8-D6] ✅ · [T8-D7] ✅ · [T8-S1] ✅
- [T8-R1] ✅ (vérifié par le vérificateur : lignes du journal, ids en entier)
- [T8-R2] ✅ (vérifié par le vérificateur et par `docs/tests/verifier_r1.py`)
- T7-D4, T7-D10 et T7-D11, marqués ❌ au tour 8, ont été rouverts en T8-D1,
  T8-D2 et T8-D3 : ✅ ci-dessus (T9-R2).

### Nouveaux points

- **T9-B1** suggestion — Appui dans les 500 ms de garde ignoré sans rien dire.
  Écarté (voir journal).

## Vérificateur (Sonnet)

R1 ❌ · R2 ✅ · R2b ✅ · R3 ✅ · R4 ✅ · R5 ✅ · R6 ✅ (HEAD bef120d)

- 733 passed (dépôt, copie `config/maisons/` vide) ; dry-run OK ; totaux des
  lots 39 et 40 égaux aux tests collectés ; lignes « 8 | Corrigé » confirmées
  dans le code ; 0198 et 0199 présentes ; écarts T8-B1, T8-R3, T8-S2 justifiés.
- **T9-R1** — tour8.md sans marque pour T7-R1, R2, R3, R6 ; tour7.md:38 abrégé.
  Corrigé après le rapport : `python docs/tests/verifier_r1.py 6` et `… 7`
  passent (0 id sans marque).
- **T9-R2** — T7-D4, T7-D10, T7-D11 « Corrigé » au journal mais ❌ au tour 8 :
  rouverts en T8-D1 à D3, retestés ✅ ci-dessus.
- **T9-R3** — Critère R1 à rendre exécutable : fait (`docs/tests/verifier_r1.py`).
- **T9-R4** — Suites d'environ 8 min : toujours lancées en arrière-plan.
