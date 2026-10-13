Boucle qualité de l'application web : tester → corriger → retester, sans
consulter l'utilisateur (décision du 2026-10-13).

1. **Tester, en deux passages parallèles** (décision du 2026-10-13) : l'agent
   `testeur-web` (consignes : `.claude/agents/testeur-web.md` ; parcours :
   `docs/tests/parcours.md` ; journal : `docs/tests/journal.md`), lancé deux
   fois, chacun avec son dossier de travail neuf dans le scratchpad
   (`testeur/tourN-bugs`, `testeur/tourN-design`) et son port :
   - **bugs**, modèle Sonnet : bugs, robustesse, erreurs, fluidité mesurée ;
   - **design**, modèle Opus : clarté, ergonomie, design, affichage.
   À partir du tour 2, passer à chacun son rapport précédent.
2. **Corriger TOUT ce qu'il remarque**, du plus grave au moins grave :
   bloquants, majeurs, mineurs ET suggestions (ergonomie, clarté, design,
   fluidité).
   - Un commit par correction ou par petit groupe cohérent, uniquement avec la
     suite pytest complète verte et `python run_v0.py --dry-run` OK. Ajouter un
     test quand le point s'y prête.
   - Levé par l'utilisateur pour cette boucle (2026-10-13) : changer le schéma
     (toujours par une migration Alembic, sans perte de données), le contrat
     `Bouteille`, modifier un test existant devenu faux, ajouter une
     bibliothèque JavaScript légère si elle apporte vraiment. Chaque cas est
     noté dans `decisions.md`.
   - Restent intouchables : les contraintes dures n° 1 à 6 de CLAUDE.md (ne
     jamais deviner, pas de prix par le modèle, colonnes expert/système jamais
     envoyées au modèle, sortie du modèle immuable, aucune perte en silence,
     format piloté par la config) et les tests qui les vérifient ; le
     hors-champ (hébergement, connexion). Ce qui les heurterait : « écarté »
     dans le journal, avec sa raison.
   - Une proposition du testeur qui dégraderait autre chose : l'écarter, raison
     écrite.
   - Mettre à jour `docs/tests/journal.md` (corrigé / écarté, commit) et, si
     un comportement change, la doc (README, règles) et `decisions.md`.
   - Les directives (`testeur-web.md`, `parcours.md`, ce fichier) peuvent être
     améliorées si un tour montre qu'elles sont floues ou incomplètes.
3. **Retester** avec le rapport précédent.
4. **Arrêt** : un tour où le testeur n'a plus rien de nouveau à signaler (tout
   est corrigé ou écarté avec raison).
5. **Rapport final** dans la conversation : tours effectués, commits, ce qui a
   été corrigé, ce qui a été écarté et pourquoi.

$ARGUMENTS
