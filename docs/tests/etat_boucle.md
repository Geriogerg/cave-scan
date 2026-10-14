# État de la boucle qualité

Seule source de vérité pour `/boucle-qualite` : mis à jour à chaque étape.

- Tour : 6
- Phase : corriger
- Agents lancés : rapports reçus (bugs, design, vérificateur)
- Rapport du tour : docs/tests/rapports/tour6.md
- À corriger : T6-X1, T6-D1 à T6-D12, T6-S1 à T6-S4, T6-B1 à T6-B10, T6-R4,
  T6-R5, T6-R7 (T6-R1, R2, R3, R6 faits : 7263ca7).
- Dernière mise à jour : 2026-10-14, rapports du tour 6 reçus, phase corriger.

## Recommandations (vérifiées par l'agent `verificateur` à chaque tour)

| Id | Recommandation | Qui la fait | Critère de vérification | Statut |
|---|---|---|---|---|
| R1 | Parcours des nouveautés, tour 3 qui valide les lots 7 à 12 | boucle | `parcours.md` a P10, P11, P12 et cite 0171 ; le rapport de chaque tour liste CHAQUE id « Corrigé » du tour précédent (journal.md) avec ✅ ou ❌ — contrôle : chaque id apparaît en grep dans `tourN.md` (critère durci au tour 5) ; un id en plusieurs lignes du journal (« partie ») prend la pire marque de ses parties | ✅ tour 6 (48 ids du tour 4 revérifiés un par un dans tour5.md) |
| R2 | Les tests ont leur propre config | boucle | la suite complète passe (0 échec, 0 erreur), lancée par `python -m pytest`, dans une copie du projet où `config/maisons/` est VIDE, et dans une copie où une colonne de `config/maisons/maison_test.json` est renommée (critère durci au tour 3, T3-R2) | ✅ vérifié au tour 6 (717 passed) |
| R2b | Sort du `maison_test.json` local (version 3) | **utilisateur** | `git status` ne le montre plus modifié : commité ou abandonné, sur décision de l'utilisateur | ✅ décidé : gardé et commité (version 3, « /village ») |
| R3 | Tests décollés du texte exact | boucle | `tests/test_style_des_tests.py` passe : aucune constante de plus de 40 caractères dans un `assert`, un `match=` ou `verifier_erreur`, hors liste blanche justifiée dans ce fichier (critère exécutable, T3-R3) | ✅ vérifié au tour 6 (717 passed) |
| R4 | Les choix faits sans validation | boucle prépare, **utilisateur** tranche | `docs/tests/choix_a_trancher.md` liste chaque choix, avec l'avis du testeur design (P12) et une recommandation ; la décision de l'utilisateur y est notée quand elle est prise | ✅ décidé par l'utilisateur (2026-10-14) : 1 à 6 gardés, 7 et 8 modifiés (option A) — à appliquer par la boucle |
| R5 | Le rapport de score signale des consignes modifiées | boucle | `run_v0.py --dry-run --maison <config avec consignes>` affiche l'avertissement, et ne l'affiche pas avec les consignes d'origine ; prouvé par un test | ✅ vérifié au tour 6 (717 passed) |
| R6 | Fusion de la branche quand le tour est propre | boucle (autorisée par l'utilisateur le 2026-10-14, decisions.md 0184) | prêt si : R1, R2, R3, R5 ✅ ; dernier tour sans bloquant ni majeur ; suite complète verte ; dry-run OK ; `git merge-tree` de `boucle-qualite` dans `main` sans conflit | ✅ fusion autorisée : avance rapide de `main` maintenant, puis à la fin de chaque tour corrigé et à l'arrêt |

## Historique
| Tour | Rapport | Points | Lots |
|---|---|---|---|
| 1 | rapports/tour1.md | 2 bloquants, 4 majeurs, 14 mineurs, 9 suggestions | 1–6 |
| 2 | rapports/tour2.md | 1 bloquant, 2 majeurs, 15 mineurs, 7 suggestions | 7–8 |
| 3 | rapports/tour3.md | vérificateur : R2b ✅, R1/R2 ⚠️, R3/R5 ❌ ; design : 1 bloquant, 4 majeurs, 19 mineurs, 8 suggestions ; bugs : sans rapport (limite de session) | 9–14 |
| 4 | rapports/tour4.md | bugs : 1 bloquant, 5 majeurs, 13 mineurs, 7 suggestions ; design : 0 bloquant, 2 majeurs, 16 mineurs, 6 suggestions ; vérificateur : sans rapport (limite de session) | 15–21 |
| 5 | rapports/tour5.md | bugs : 0 bloquant, 3 majeurs, 9 mineurs, 3 suggestions ; design : 0 bloquant, 0 majeur, 9 mineurs, 3 suggestions ; vérificateur : R1 ⚠️, R2/R3/R5 ✅ | 22–30 |
