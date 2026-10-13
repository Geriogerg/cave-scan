Boucle qualité de l'application web : tester → corriger → retester.

1. Lancer l'agent testeur-web (consignes : `.claude/agents/testeur-web.md`,
   parcours : `docs/tests/parcours.md`) avec un dossier de travail neuf dans le
   scratchpad. Au tour suivant, lui passer le rapport précédent.
2. Trier son rapport. BLOQUANT et MAJEUR : corriger, en respectant CLAUDE.md —
   un commit par correction, suite pytest complète verte et `--dry-run` OK
   avant chaque commit, ajouter un test quand c'est possible, jamais modifier
   un test existant ni le schéma ni le contrat `Bouteille`, jamais trancher un
   choix métier (les noter pour l'utilisateur). MINEUR et SUGGESTION : corriger
   seulement si c'est sûr et local, sinon les lister.
3. Relancer le testeur avec le rapport précédent.
4. Arrêter quand deux passages de suite n'ont plus aucun BLOQUANT ni MAJEUR,
   ou après 5 tours, ou si la suite de tests ne peut plus être remise au vert.
5. Rapport final : ce qui a été corrigé (commits), ce qui reste, ce qui attend
   une décision de l'utilisateur.

$ARGUMENTS
