# État de la boucle qualité

Seule source de vérité pour `/boucle-qualite` : mis à jour à chaque étape.

- Tour : 3
- Phase : tester
- Agents lancés : non
- Rapport précédent : docs/tests/rapports/tour2.md
- À tester en priorité : corrections du tour 2 (lots 7–8, jamais revérifiées)
  et nouveautés non vues par un agent — une instance = une maison (0171),
  configuration créée à la main (0172), consignes modifiables (0173), textes
  raccourcis (parcours P10, P11, P12).
- Dernière mise à jour : 2026-10-13, recommandations ajoutées, boucle non lancée.

## Recommandations (vérifiées par l'agent `verificateur` à chaque tour)

| Id | Recommandation | Qui la fait | Critère de vérification | Statut |
|---|---|---|---|---|
| R1 | Parcours des nouveautés, tour 3 qui valide les lots 7 à 12 | boucle | `parcours.md` a P10, P11, P12 et cite 0171 ; `rapports/tour3.md` existe et dit, pour chaque point « Corrigé » du tour 2 dans le journal, confirmé ✅ ou non ❌ | à faire |
| R2 | Les tests ont leur propre config | boucle | `CONFIG_TEST` (tests/conftest.py) désigne un fichier SOUS `tests/` ; aucun test ne lit `config/maisons/` (grep) ; la suite passe avec `config/maisons/maison_test.json` modifié localement, lancée par `python -m pytest` directement (sans `tests.sh`) | à faire |
| R2b | Sort du `maison_test.json` local (version 3) | **utilisateur** | `git status` ne le montre plus modifié : commité ou abandonné, sur décision de l'utilisateur | ⏳ décision |
| R3 | Tests décollés du texte exact | boucle | aucune assertion de test ne compare une phrase d'interface de plus de 40 caractères (recherche des `in …text` / `match=` sur des chaînes longues), hors messages qui portent une contrainte dure ; la liste des exceptions restantes est justifiée dans le journal | à faire |
| R4 | Les 6 choix faits sans validation | boucle prépare, **utilisateur** tranche | `docs/tests/choix_a_trancher.md` liste les 6 choix, avec pour chacun l'avis du testeur design (parcours P12) et une recommandation ; la décision de l'utilisateur y est notée quand elle est prise | à faire |
| R5 | Le rapport de score signale des consignes modifiées | boucle | `run_v0.py` (et `formater_rapport`) affiche un avertissement quand l'inventaire a été lu avec des consignes modifiées ; un test le prouve ; rien n'est affiché avec les consignes d'origine | à faire |
| R6 | Fusion de la branche quand le tour 3 est propre | **utilisateur** (la boucle ne fusionne pas) | prêt si : R1, R2, R3, R5 ✅ ; dernier tour sans bloquant ni majeur ; suite complète verte ; dry-run OK ; `git merge-tree` de `boucle-qualite` dans `master` sans conflit | ⏳ prêt / pas prêt |

## Historique
| Tour | Rapport | Points | Lots |
|---|---|---|---|
| 1 | rapports/tour1.md | 2 bloquants, 4 majeurs, 14 mineurs, 9 suggestions | 1–6 |
| 2 | rapports/tour2.md | 1 bloquant, 2 majeurs, 15 mineurs, 7 suggestions | 7–8 |
