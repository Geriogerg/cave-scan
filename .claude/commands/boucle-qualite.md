Boucle qualité de l'application web : tester → corriger → retester, sans
consulter l'utilisateur (décision du 2026-10-13).

1. **Tester.** Lancer l'agent `testeur-web` (consignes :
   `.claude/agents/testeur-web.md` ; parcours : `docs/tests/parcours.md` ;
   journal : `docs/tests/journal.md`) avec un dossier de travail neuf dans le
   scratchpad (`testeur/tourN`) et un port libre. À partir du tour 2, lui
   passer le rapport précédent.
2. **Corriger TOUT ce qu'il remarque**, du plus grave au moins grave :
   bloquants, majeurs, mineurs ET suggestions (ergonomie, clarté, design,
   fluidité).
   - Un commit par correction ou par petit groupe cohérent, uniquement avec la
     suite pytest complète verte et `python run_v0.py --dry-run` OK. Ajouter un
     test quand le point s'y prête.
   - Les contraintes dures de CLAUDE.md priment toujours. Ce qui exigerait de
     les enfreindre, de modifier un test existant, de changer le schéma de
     base ou le contrat `Bouteille`, ou qui relève du hors-champ (hébergement,
     connexion) : ne pas le faire, l'inscrire « écarté » dans le journal avec
     sa raison.
   - Pas de framework JavaScript ni d'infrastructure lourde (CLAUDE.md).
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
