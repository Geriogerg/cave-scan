# Tour 5 — rapports (2026-10-14)

Trois passages : **bugs** (Sonnet, T5-B…), **design** (Opus, T5-D…),
**vérificateur** (Sonnet, T5-R…). Sections ajoutées à réception.

## Testeur design (Opus)

0 bloquant, 0 majeur, 9 mineurs, 3 suggestions. Écrans 16 à 143 ms à
l'ordinateur (« Vérifier » au téléphone 277 ms), bouteille suivante 150–230 ms ;
aucun 500, aucune erreur JavaScript, aucun débordement.

Points du tour 4 : tous ✅, sauf T4-D10 ❌ (régression : le ✕ cache le nom du
domaine sur la vignette), T4-D4 ❌ en partie (aucun champ lu au premier écran
au téléphone), T4-D14 ❌ en partie (« (s) » restants), T3-D2 ❌ en partie
(alerte loin des consignes). Non retestés : T4-B4, T4-B9, T4-B16, ligne T4-B19.

- **T4-D10** (régression du lot 17) — Le ✕ voile le haut de la photo (nom du
  domaine illisible) : au téléphone, bandeau de toute la largeur ; à
  l'ordinateur, carré de 44 px.
- **T4-D4** (reste) — Relecture au téléphone : 3 rangées de navigation, photo,
  2 rangées de vignettes : aucun champ lu sans défiler.
- **T5-D2** — Coupure réseau sur « Vérifier » : le champ garde « 4 », le serveur
  a « 1 » ; « Lancer » partirait avec 1.
- **T5-D1** — Refus de quantité au téléphone : carte déformée, guillemet
  séparé, « Bouteille 2 — » redondant, champ remis à 3 alors que le message
  parle de « 0 ».
- **T5-D3** — Bouteilles faites en galerie invisibles en mode « Appareil photo ».
- **T4-D14** (reste) — « (s) » partout ; « 0 / 4 photo » ; « Corrections : 0 sur
  0 » ; « Son analyse s'arrête » à la corbeille même finie.
- **T5-D4** — Récapitulatif à l'ordinateur mal aligné ; cases à cocher bleues
  (pas d'`accent-color`) ; téléphone : « bouteilles identiques » seul, libellés
  de barre sur 2 lignes, nom de vente coupé dans l'en-tête de relecture ;
  versions : point isolé, lien qui passe à la ligne.
- **T5-D5** — Configuration : après « Ajouter une colonne », le champ Nom n'est
  pas en vue ni en focus ; « Vérifier » referme les aperçus ; « colonne n°17
  sans nom » sans lien vers la colonne.
- **T3-D2** (reste) — Alerte « exemple de réponse » en haut, loin des consignes.
- **T5-DS1** — Glisser-déposer : l'annoncer ; un dépôt hors carte ouvre la photo
  dans le navigateur.
- **T5-DS2** — Inventaire clos : « Télécharger l'Excel » en action principale.
- **T5-DS3** — Versions : « (reprise de la version 3) ».

Avis P12 : 1 à 6 GARDER ; 7 MODIFIER (principe) ; 8 MODIFIER : « validée »
doit vouloir dire « relue », le jaune ne doit pas survivre à la validation —
en échange, prévenir à la validation si un champ « toujours à vérifier » est
vide.

## Vérificateur (Sonnet)

R1 ⚠️ · R2 ✅ · R2b ✅ · R3 ✅ · R4 ⏳ · R5 ✅ · R6 ⏳ (pas prêt)

- **T5-R1** R1 ⚠️ — Parcours P10–P12 dans l'ordre, 0171 cité. Les rapports
  confirment les points du tour précédent globalement (« tous ✅ sauf… ») et non
  identifiant par identifiant ; les points T2-B… et ceux du lot 9 n'avaient été
  confirmés par personne avant ce rapport. Critère proposé : chaque id
  « Corrigé » du tour N-1 apparaît dans `tourN.md` avec ✅ ou ❌.
- **T5-R2** R2 ✅ — 690 passed sur le dépôt, sur une copie avec `config/maisons/`
  vide, sur une copie avec une colonne renommée (clé et libellés), en série ;
  aucun test sauté ; `test_arret_brutal` vert trois fois.
- **T5-R3** R3 ✅ — `test_style_des_tests.py` vert ; liste blanche : 3 données ;
  aucun contournement trouvé. Faiblesses : phrases en variable ou concaténées
  non vues ; exemptions larges (`<`, `http`, `="`, ` FROM `).
- **T5-R5** R5 ✅ — Code, test et dry-run réel (avertissement avec consignes
  modifiées, aucun sans). Réserves : une config écrite à la main avec le texte
  d'origine exact déclenche l'avertissement ; la branche « sans listing »
  n'a pas de test.
- **T5-R6** R6 ⏳ pas prêt — R1 ⚠️, et le tour 4 avait 1 bloquant et des majeurs ;
  suite verte, dry-run OK, `merge-tree` dans `main` sans conflit (avance
  rapide, 38 commits).
- Commits 95fc8a0..HEAD : les totaux annoncés correspondent aux tests collectés ;
  HEAD 690 passed. Lot 21 : « seule règle CSS ajoutée après la suite » est
  imprécis (plusieurs règles CSS dans le lot), sans conséquence (HEAD vert).
  Lot 16 : « ; test navigateur » laisse croire que T4-B4 et T4-B5 sont testés —
  ils ne le sont pas.
- Échantillon de 16 points « Corrigé » des lots 15 à 21 : tous confirmés dans le
  code.
- **T5-R7** `etat_boucle.md` : statuts périmés (R2, R3, R5 « à confirmer au tour
  4 », R4 « avis attendus », R6 « tour 3 »).
- **T5-R8** `decisions.md` sans ligne pour les lots 15 à 21 (garde de 500 ms,
  `no-store`, « revenir à cette version », restauration qui remet l'analyse, 404
  au-delà de 18 chiffres).
- **T5-R9** Sans test : T4-B4 (404 en relecture, contrainte 5), T4-B5 (coupure
  réseau), T4-DS1, T4-DS2.
- **T5-R10** Choix n°7 ni traité ni tranché (décision de l'utilisateur).
