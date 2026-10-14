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

## Testeur bugs (Sonnet)

0 bloquant, 3 majeurs, 9 mineurs, 3 suggestions. Parcours : P1 ✅ P2 ✅ P3 ⚠️
P4 ⚠️ P5 ✅ P6 ❌ P7 ✅ P8 ❌ P9 ✅ P10 ✅ P11 ✅. Écran moyen ≈ 107 ms (le plus
lent : Configuration, 295 ms) ; Excel de 60 bouteilles 546 ms ; aucune erreur
JavaScript ; aucun défilement horizontal ni cible < 40 px sur 12 écrans au
téléphone (mesure faite AVANT toute capture : une capture `full_page` fait
perdre `pointer: coarse` à Playwright).

### Points du tour précédent (revérifiés id par id)

- [T4-D1] ✅ · [T3-D5 / T4-B6] ✅ · [T4-D2] ✅ · [T4-D6] ✅ · [T4-D11] ✅
- [T3-D2 / T4-B11] ✅ · [T4-B1] ✅ · [T4-B2] ✅ · [T4-B3 / T4-D12] ✅
- [T4-B4] ✅ (inventaire mis à la corbeille ailleurs) · [T4-B5] ✅ (Vérifier,
  configuration, relecture)
- [T4-B7] ✅ · [T4-D5] ✅ (alignement : T5-B12) · [T4-D10] ✅ · [T4-B16] ✅
- [T4-D14] ⚠️ reste « photo(s) » / « bouteille(s) » au dépôt et à Vérifier
- [T4-D8] ✅ · [T4-D9 / T4-B15] ⚠️ galerie : doublon hors de la carte (T5-B7)
- [T4-B8] ✅ · [T4-B9] ✅ · [T4-D13 / T4-B23] ✅
- [T4-D3 / T4-D4 / T4-B24] ✅ avec réserve : clavier simulé (500 px de haut),
  le champ actif dépasse de ~12 px sous « Valider » ; à 420 px, plus aucun
  champ touchable
- [T4-B17] ✅ · [T4-B10] ⚠️ nouvelle colonne : identifiant figé (T5-B8)
- [T4-B12] ✅ · [T4-D7] ✅ · [T4-B22 / T4-DS5] ✅ · [T4-B25] ✅ · [T4-B13] ✅
- [T4-B14] ✅ · [T4-D16 / T4-B19] ✅ · [T4-D15] ✅ · [T4-B20] ✅
- [T4-DS1] ✅ · [T4-DS2] ✅ · [T4-DS3] ✅ · [T4-DS4] ✅ · [T4-DS6] ✅
- Non re-signalés : T4-B18 (choix n° 8), T4-B21 (écarté).

### Nouveaux points

- **T5-B1** MAJEUR — Valider pendant une (ré)analyse : « statut « a_extraire » »
  montré ; bandeau « la page se mettra à jour toute seule » pendant une pause ;
  « Réanalyse » pour une première analyse ; « Note du modèle : Extraction sans
  résultat » fabriquée. Proposé : Valider grisé avec la raison, bandeau juste.
- **T5-B2** MAJEUR — Configuration sans « À vérifier » : avertissement permanent
  avec clé interne et « decisions.md 0170 ». Retrait de « Qté », « N° »,
  « Domaine » sans avertissement.
- **T5-B3** MAJEUR — Refus de configuration en jargon (« photos_max_par_bouteille »,
  « contrat Bouteille », « noyau canonique », « modele_best_effort ») ; plusieurs
  phrases pour une cause.
- **T5-B4** mineur — Quantité de plus de 4 300 chiffres : 500 (Vérifier,
  Séparer, photos au plus de la configuration).
- **T5-B5** mineur — Vérifier sur une vente lancée ou close : page vide et
  muette.
- **T5-B6** mineur — Galerie : « Ajouter une bouteille » répété crée plusieurs
  cartes vides « Bouteille 4 ».
- **T5-B7** mineur — Galerie : « déjà dans la bouteille 1 » seulement en bas.
- **T5-B8** mineur — Nouvelle colonne : identifiant figé au premier « Vérifier ».
- **T5-B9** mineur — Import sans colonnes : onze phrases pour une cause.
- **T5-B10** mineur — Nom d'inventaire sans limite côté serveur (5 000
  caractères, caractère NUL).
- **T5-B11** mineur — Deux onglets sur le même dépôt : photos de deux bouteilles
  fondues en une (rien de perdu).
- **T5-B12** mineur — Vérifier : refus de quantité qui redit le numéro et casse
  l'alignement de la carte.
- **T5-B13** suggestion — Appui ignoré dans les 500 ms : aucun signe.
- **T5-B14** suggestion — Dépôt : barre de progression pleine visible après la
  fin des envois.
- **T5-B15** suggestion — Après « Réanalyser », aucune annonce de fin.

Avis P12 : inchangé (choix 1 à 6 aident ou sont acceptables ; 7 non retesté).
