# État de la boucle qualité

Seule source de vérité pour `/boucle-qualite` : mis à jour à chaque étape.

- Tour : 3
- Phase : corriger (tour 3 : rapports vérificateur et design ; le passage bugs s'est arrêté sur la limite de session, sans rapport — non relancé : le tour 4 complet revérifiera)
- Agents lancés : oui (2026-10-13 — bugs, design, vérificateur)
- Rapport précédent : docs/tests/rapports/tour2.md
- À tester en priorité : corrections du tour 2 (lots 7–8, jamais revérifiées)
  et nouveautés non vues par un agent — une instance = une maison (0171),
  configuration créée à la main (0172), consignes modifiables (0173), textes
  raccourcis (parcours P10, P11, P12).
- Dernière mise à jour : 2026-10-13, boucle lancée par /loop ; tour 3 en cours de test.

## Recommandations (vérifiées par l'agent `verificateur` à chaque tour)

| Id | Recommandation | Qui la fait | Critère de vérification | Statut |
|---|---|---|---|---|
| R1 | Parcours des nouveautés, tour 3 qui valide les lots 7 à 12 | boucle | `parcours.md` a P10, P11, P12 et cite 0171 ; `rapports/tour3.md` existe et dit, pour chaque point « Corrigé » du tour 2 dans le journal, confirmé ✅ ou non ❌ | à faire |
| R2 | Les tests ont leur propre config | boucle | la suite complète passe (0 échec, 0 erreur), lancée par `python -m pytest`, dans une copie du projet où `config/maisons/` est VIDE, et dans une copie où une colonne de `config/maisons/maison_test.json` est renommée (critère durci au tour 3, T3-R2) | fait (lot 9, 671 passed) — à confirmer par le vérificateur au tour 4 |
| R2b | Sort du `maison_test.json` local (version 3) | **utilisateur** | `git status` ne le montre plus modifié : commité ou abandonné, sur décision de l'utilisateur | ✅ décidé : gardé et commité (version 3, « /village ») |
| R3 | Tests décollés du texte exact | boucle | `tests/test_style_des_tests.py` passe : aucune constante de plus de 40 caractères dans un `assert`, un `match=` ou `verifier_erreur`, hors liste blanche justifiée dans ce fichier (critère exécutable, T3-R3) | fait (lot 9, 671 passed) — à confirmer par le vérificateur au tour 4 |
| R4 | Les choix faits sans validation | boucle prépare, **utilisateur** tranche | `docs/tests/choix_a_trancher.md` liste chaque choix, avec l'avis du testeur design (P12) et une recommandation ; la décision de l'utilisateur y est notée quand elle est prise | ⏳ avis P12 attendus |
| R5 | Le rapport de score signale des consignes modifiées | boucle | `run_v0.py --dry-run --maison <config avec consignes>` affiche l'avertissement, et ne l'affiche pas avec les consignes d'origine ; prouvé par un test | fait (lot 9, 671 passed) — à confirmer par le vérificateur au tour 4 |
| R6 | Fusion de la branche quand le tour est propre | **utilisateur** (la boucle ne fusionne pas) | prêt si : R1, R2, R3, R5 ✅ ; dernier tour sans bloquant ni majeur ; suite complète verte ; dry-run OK ; `git merge-tree` de `boucle-qualite` dans `main` sans conflit | ⏳ pas prêt (tour 3) |

## Historique
| Tour | Rapport | Points | Lots |
|---|---|---|---|
| 1 | rapports/tour1.md | 2 bloquants, 4 majeurs, 14 mineurs, 9 suggestions | 1–6 |
| 2 | rapports/tour2.md | 1 bloquant, 2 majeurs, 15 mineurs, 7 suggestions | 7–8 |
