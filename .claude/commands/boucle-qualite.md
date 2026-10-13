Boucle qualité de l'application web : tester → corriger → retester, sans
consulter l'utilisateur (décision du 2026-10-13). Cette commande fait l'étape
suivante d'après l'état ÉCRIT, puis enchaîne. Elle se relance seule avec
`/loop /boucle-qualite` (reprise après une interruption ou une coupure de
crédits).

## 0. Lire l'état
Lire `docs/tests/etat_boucle.md` (tour, phase, agents lancés ou non). C'est la
SEULE source de vérité : ne rien supposer de la conversation. Après chaque
étape, le mettre à jour et le committer avec l'étape.

## 1. Phase « tester »
- Agents pas encore lancés : lancer DEUX agents `testeur-web` en arrière-plan,
  chacun avec un dossier de travail neuf dans le scratchpad
  (`testeur/tourN-bugs`, `testeur/tourN-design`) et un port libre différent :
  - **bugs**, `model: sonnet` : bugs, robustesse, erreurs, fluidité mesurée ;
  - **design**, `model: opus` : clarté, ergonomie, design, affichage.
  Leur donner `docs/tests/parcours.md`, `docs/tests/journal.md` et le rapport
  du tour précédent (`docs/tests/rapports/tour<N-1>.md`) : revérifier d'abord
  chacun de ses points « corrigé ». Écrire dans l'état « Agents lancés : oui
  (date) ». Puis attendre leurs notifications (sous `/loop` : réveil de
  secours à 30 min).
- Rapports reçus : les fusionner dans `docs/tests/rapports/tourN.md`
  (identifiants TN-B… et TN-D…), passer en phase « corriger ».
- Agents marqués lancés, mais aucun rapport disponible (nouvelle session,
  coupure) : les relancer.

## 2. Phase « corriger »
Corriger TOUT ce que le rapport du tour signale, du plus grave au moins grave :
bloquants, majeurs, mineurs ET suggestions (ergonomie, clarté, design,
fluidité).
- Un commit par lot cohérent (6 points au plus), uniquement avec la suite
  pytest complète verte (`bash docs/tests/tests.sh`) et
  `python run_v0.py --dry-run` OK. Ajouter un test quand le point s'y prête ;
  pour un comportement JavaScript, un test navigateur.
- Ne jamais écrire dans un message de commit un résultat de tests qui n'a pas
  été obtenu tel quel sur la version commitée.
- Levé par l'utilisateur pour cette boucle (2026-10-13) : changer le schéma
  (toujours par une migration Alembic, sans perte de données), le contrat
  `Bouteille`, modifier un test existant devenu faux, ajouter une
  bibliothèque JavaScript légère si elle apporte vraiment. Chaque cas est
  noté dans `decisions.md`.
- Restent intouchables : les contraintes dures n° 1 à 6 de CLAUDE.md (ne
  jamais deviner, pas de prix par le modèle, colonnes expert/système jamais
  envoyées au modèle, sortie du modèle immuable, aucune perte en silence,
  format piloté par la config) et les tests qui les vérifient ; le hors-champ
  (hébergement, connexion). Ce qui les heurterait : « écarté » dans le
  journal, avec sa raison.
- Une proposition du testeur qui dégraderait autre chose : l'écarter, raison
  écrite.
- Tenir `docs/tests/journal.md` à jour (corrigé / écarté, commit) et, si un
  comportement change, la doc (README, règles) et `decisions.md`.
- Les directives (`testeur-web.md`, `parcours.md`, ce fichier) peuvent être
  améliorées si un tour montre qu'elles sont floues ou incomplètes ; toute
  fonction nouvelle entre dans les parcours.
- Tous les points du tour corrigés ou écartés : tour + 1, phase « tester »,
  agents « non ».

## 3. Arrêt
Quand le rapport d'un tour n'apporte RIEN de nouveau (chaque point signalé est
déjà corrigé et confirmé, ou écarté avec sa raison) : phase « arrêt ». Faire
le rapport final dans la conversation (tours, commits, corrigé, écarté et
pourquoi) et, sous `/loop`, arrêter la boucle.

## Interruptions
Une question de l'utilisateur pendant la boucle : y répondre, PUIS reprendre
l'étape en cours dans le même tour de conversation. Ne jamais finir un tour de
conversation en phase « tester » ou « corriger » sans avoir lancé l'étape
suivante (ou programmé le réveil sous `/loop`), sauf si l'utilisateur demande
d'arrêter.

$ARGUMENTS
