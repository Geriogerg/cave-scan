# Tour 3 — rapports (2026-10-13)

Trois passages : **bugs** (Sonnet, T3-B…), **design** (Opus, T3-D…),
**vérificateur** (Sonnet, T3-R…). Les sections des testeurs sont ajoutées à
réception.

## Vérificateur — verdicts

R1 ⚠️ · R2 ⚠️ · R2b ✅ · R3 ❌ · R4 ⏳ · R5 ❌ · R6 ⏳ (pas prêt)

- **T3-R1** R1 ⚠️ — Parcours P10–P12 présents, 0171 cité. Le rapport du tour 3
  (confirmation des 22 points « Corrigé » du tour 2) reste à écrire.
  Cosmétique : P12 placé avant P9 dans `parcours.md`.
- **T3-R2** R2 ⚠️ — La lettre du critère passe (`CONFIG_TEST` sous `tests/`,
  aucun chemin `config/maisons` en clair), mais 105 tests lisent encore
  `config/maisons/` INDIRECTEMENT : fixture `api` (`creer_app` sans `configs`),
  dry-runs de `test_run_v0` (`CONFIG_DEFAUT`), `dev.py`/`serveur.py` lancés
  par les tests navigateur et de lancement. Preuves : dossier `config/maisons`
  vide → 62 échecs, 43 erreurs ; colonne renommée → 2 échecs déterministes
  (`test_la_page_d_une_bouteille`, `test_relire_dix_bouteilles…`). Critère à
  durcir : la suite passe avec `config/maisons/` vide ET avec une colonne
  renommée.
- **T3-R3** R3 ❌ — 42 assertions sur des phrases d'interface de plus de 40
  caractères (liste fichier:ligne dans le rapport du vérificateur), dont ~12
  candidates « contrainte 5 » et 1 « contrainte 3 ». Critère à rendre
  exécutable : un test AST qui échoue au-delà d'une liste blanche.
- **T3-R4** R4 ⏳ — `choix_a_trancher.md` sans avis ni recommandation (attend
  l'avis P12 du testeur design). Le choix 6 mêle deux choix ; la config
  « première par ordre alphabétique » n'est pas dans P12 ; la dernière puce de
  P12 (textes réduits) n'est pas un choix de la boucle.
- **T3-R5** R5 ❌ — Rien ne signale des consignes modifiées dans le rapport de
  score ; aucun test. Prouvé par un dry-run avec consignes modifiées.
- **T3-R6** R6 ⏳ pas prêt — R1, R2, R3, R5 non validées. Suite verte (668),
  dry-run OK, `git merge-tree` dans `main` sans conflit (avance rapide). La
  branche principale est `main`, pas `master`.
- Commits : les totaux de tests annoncés correspondent aux tests collectés.
- **T3-R7** Documentation fausse : le message de e464954 et `tests.sh` disent
  que modifier la config de l'application ne touche plus les tests (faux, voir
  T3-R2).
- **T3-R8** Faux positif few-shot : les consignes d'origine contiennent
  « observee », « inferee » entre guillemets ; toute modification, même d'une
  phrase, déclenche l'avertissement few-shot.
- **T3-R9** `test_worker.py::test_arret_brutal…` : un échec sous forte charge
  (bouteille extraite deux fois), non reproduit (3/3 seul, 5/5 sous charge).
  À surveiller, ne pas affaiblir.
- **T3-R10** `verificateur.md` dit que `tests.sh` protège la config locale :
  périmé.

## Testeur design (Opus) — sur le commit f426e8c

1 bloquant, 4 majeurs, 19 mineurs, 8 suggestions. Pages ≈ 50 ms, relecture
244 ms au pire, aucune erreur JavaScript, aucun 500, aucun défilement
horizontal.

Points du tour 2 : tous ✅ sauf T2-D1 (bouteilles d'un autre navigateur :
seulement en mode appareil photo, quantité perdue), T2-D8 (refus pour
plafond de photos invisible), T2-D12 (« Corrections » compte les retours au
modèle ; « noyau » en infobulle).

- **T3-D1** BLOQUANT — Reprendre une bouteille depuis un autre navigateur
  remet sa quantité à 1, en silence (depot.js : `quantite: 1` en dur, quantité
  envoyée avec chaque photo).
- **T3-D2** MAJEUR — Avertissement few-shot en jargon (« few-shot »,
  « CLAUDE.md », clé de colonne), et déclenché à tort par « observee » (=T3-R8).
- **T3-D3** MAJEUR — Texte trop long : le refus cite `description_etat` ;
  pas de `maxlength`.
- **T3-D4** MAJEUR — « Télécharger l'Excel » quand l'écran n'est plus à jour :
  409 silencieux (téléchargement annulé), JSON brut si l'adresse est ouverte.
- **T3-D5** MAJEUR — Photo refusée pour le plafond (4) : ni dans la carte, ni
  dans le résumé (reste T2-D8).
- **T3-D6** La case « Je confirme… » reste visible (`[hidden]` écrasé par
  `display:flex`) : la double confirmation ne se lit plus.
- **T3-D7** Le refus « cochez Je confirme » s'affiche à 2 800 px de la case.
- **T3-D8** Quantité démesurée au dépôt : c'est la photo qui est refusée ;
  champ trop étroit pour 6 chiffres.
- **T3-D9** Une erreur d'import fait quitter l'éditeur (page « Aucune
  configuration »).
- **T3-D10** Sans configuration : « importez-la » alors qu'on peut la créer ;
  titre redondant ; bouton « Configuration » qui ramène sur place.
- **T3-D11** Pas de retour aux inventaires depuis la Configuration.
- **T3-D12** En galerie, les bouteilles reçues d'un autre appareil
  n'apparaissent pas (reste T2-D1).
- **T3-D13** Téléphone : « Valider » collé se superpose à la photo collée.
- **T3-D14** Récapitulatif : « Corrections » et « Champs les plus corrigés »
  comptent différemment ; aide de « Séparer » qui affiche une quantité périmée.
- **T3-D15** Archiver : message en double.
- **T3-D16** Refus de photo affiché deux fois ; nom de fichier coupé.
- **T3-D17** Textes : page « Impossible d'afficher cette page » au renommage
  vide ; « inventaire » / « vente » ; deux deux-points ; guillemet orphelin
  dans le conflit ; « (facultatif) » obscur à la clôture.
- **T3-D18** Dépôt à l'ordinateur : « Photographier », « Retirer cette
  carte », option « 4G » sans objet.
- **T3-D19** Ordre des bouteilles déjà photographiées instable.
- **T3-D20** Cibles tactiles < 40 px (filtre, Récapitulatif, Original, Autres
  actions, Historique, reprendre la relecture, ↑/↓, cases).
- **T3-D21** « Vérifier » à l'ordinateur : barre non alignée sur les cartes,
  8 boutons pour 4 photos.
- **T3-D22** Durée d'analyse : seul le dernier lancement compte.
- **T3-D23** Double clic sur « Lancer » : deux confirmations.
- **T3-D24** Configuration peu explicite : rien ne dit « colonnes de votre
  Excel » ; « noyau », « Code », « d'office » ; description « pour le modèle »
  proposée pour une colonne expert.
- **T3-DS1** Suivi titré « Analyse des photos » : titrer avec le nom de la vente.
- **T3-DS2** Excel nommé `inventaire_5.xlsx` ; position absente.
- **T3-DS3** Bouteille signalée : désactiver « Valider » avec la raison.
- **T3-DS4** Configuration : en-tête de colonne cliquable, « Tout ouvrir ».
- **T3-DS5** Consignes : prévenir que les mots entre « » et en MAJUSCULES sont
  attendus par l'outil.
- **T3-DS6** Fin de relecture : proposer « Clore l'inventaire » sur place.
- **T3-DS7** Dépôt au téléphone : une ligne d'enchaînement ; « bouteilles
  identiques ».
- **T3-DS8** Accueil : brouillons sans compte ; nom en double accepté sans
  avertissement.
