# Journal de décisions — v0

Décisions techniques qui cadrent la v0. Une ligne chacune :
`NNNN — décision — raison — alternative écartée`. Les décisions stratégiques
(marché, suite) sont dans ROADMAP.md, pas ici.

---

- 0001 — Extraction par VLM en tool-use (sortie contrainte), pas OCR classique —
  étiquettes = pire-cas OCR, et c'est la structuration qui est dure ; le VLM lit
  et range en une passe — OCR gardé seulement en option future pour re-vérifier
  le millésime.

- 0002 — `non_lisible` / `non_determinable` = valeurs de première classe — on
  mesure l'abstention, on ne la punit pas — écarté : forcer une valeur par champ.

- 0003 — Ne jamais deviner millésime ni format ; format = non_determinable par
  défaut — illisibles de manière fiable sur un gros plan d'étiquette — écarté :
  laisser le modèle estimer.

- 0004 — `couleur_source` (observee | inferee | non_lisible) — la couleur est
  souvent déduite de l'appellation, pas lue ; l'expert doit le savoir en relisant.

- 0005 — Colonne estimation présente mais VIDE, jamais remplie par le modèle — un
  VLM sort un prix inventé, ce qui grille la crédibilité — l'estimation viendra
  d'une couche données plus tard.

- 0006 — Zero-shot en v0, aucun exemple dans le prompt — des exemples rendraient
  le score du plancher ininterprétable (modèle ou exemples ?) — écarté : few-shot
  dès le départ.

- 0007 — Normalisation = identité en v0 (pass-through + TODO) — les règles de
  convention (préfixe Domaine, cuvée, accents) doivent s'écrire en regardant les
  VRAIS écarts ; les inventer serait deviner — écarté : normaliser à l'avance.

- 0008 — Comparaison auto vs manuel insensible casse/accents — beaucoup d'« erreurs »
  seront des écarts de convention, pas de lecture ; sans ça on sous-estime le
  modèle.

- 0009 — Métriques de comparaison : accuracy (hors abstention et hors manuel vide),
  abstention, desaccord (les 2 renseignés mais différents = vrais ratés),
  manuel_vide — séparer « le modèle s'abstient » de « le modèle se trompe ».

- 0010 — Hypothèse d'alignement ligne à ligne photos <-> listing manuel en v0 —
  simple et suffisant pour mesurer ; si l'ordre n'est pas garanti, appariement par
  clé (domaine + millésime) à ajouter.

- 0011 — [format précisé par 0020 : JSON] Format de sortie piloté par config YAML par maison (fond/forme séparés) —
  changer de maison = changer de config, pas de code — écarté : une sous-classe
  formatter par maison.

- 0012 — Doit tourner hors ligne en --dry-run sur fixtures — valider la plomberie
  sans clé API ni vraies photos, avant leur arrivée.

## Conception

- 0013 — Interface (typing.Protocol) seulement où la variation est certaine, code
  plat ailleurs ; interface au 2e cas d'usage, pas au 1er — évite l'indirection
  spéculative qu'il faudrait défaire — exception : l'extracteur (2e cas déjà acté).

- 0014 — Protocol `Extractor` (extract(...) -> Bouteille) ; run_v0 et tests
  dépendent du Protocol, pas du VLM concret — un 2e extracteur (OCR millésime,
  comparaison de modèles) est déjà prévisible.

- 0015 — Normalisation = fonctions pures composées en pipeline, pas une fabrique
  de stratégies — testable unitairement, extensible en ajoutant une fonction.

## Produit pilote (décisions du 2026-10-09)

- 0016 — Une ligne = une bouteille physique en interne, avec un identifiant
  stable — permet de distinguer des bouteilles identiques d'état différent et
  servira de base au lotting — écarté : une ligne par lot dès la saisie.

- 0017 — Quantité = champ saisi par l'expert ; à l'export, regroupement
  automatique des bouteilles identiques ET de même état (ex. 5 × bon état +
  1 × étiquette abîmée) — écarté : quantité lue par le modèle.

- 0018 — Lotting automatique reporté ; seul l'identifiant stable est prévu
  maintenant.

- 0019 — Champs du pilote : identifiant, domaine, appellation, cuvée,
  millésime, couleur, format, quantité, état de l'étiquette, description
  générale de l'état. Niveau, capsule, bouchon : hors pilote.

- 0020 — Format de sortie par maison décrit dans une config versionnée :
  colonnes, type (texte | liste | nombre), source (modele | modele_best_effort |
  expert), valeurs possibles avec description. Valeur « non déterminable »
  ajoutée automatiquement à chaque liste. Édition en JSON pour le pilote,
  éditeur dans l'interface plus tard.

- 0021 — Noyau canonique fixe (domaine, appellation, millésime, format) extrait
  à l'identique pour toutes les maisons ; la config ne change que l'affichage —
  sans ça, chaque maison casserait le rattachement LWIN et l'estimation future.

- 0022 — L'expert utilise l'outil lui-même : application web utilisable sur
  téléphone, écran de relecture comme pièce centrale — écarté : application
  native iOS/Android pour le pilote.

- 0023 — Pas de réseau en cave : photos prises au téléphone dans l'ordre
  (étiquette, contre-étiquette, bouteille suivante), puis dépôt au bureau ;
  appariement par ordre, paires affichées côte à côte en relecture, paires
  incohérentes signalées. Mode hors ligne dans l'application : plus tard.

- 0024 — Traitement en tâche de fond et en parallèle ; coût et temps par
  bouteille mesurés (session 2). Volume cible pilote : 300 bouteilles max.

- 0025 — Estimation : saisie par l'expert dans le pilote. Méthode future par
  comparables (même vin, millésime, format), clé = LWIN + millésime + format,
  fourchette + ventes affichées avec source et date. Ni lecture de sites à la
  volée, ni modèle entraîné à ce stade. Source de données à choisir (historique
  de la maison pilote, cotes publiques, API payantes) : conditions à vérifier.

## Mise en œuvre (squelette v0)

> Décisions 0026 à 0051 : prises pendant la construction de la v0 sous les
> numéros 0016 à 0041, renumérotées le 2026-10-09 (+10) quand les décisions
> « Produit pilote » ont pris les numéros 0016 à 0025. Les messages de commit
> antérieurs à cette date citent donc les anciens numéros.

- 0026 — Troisième convention d'abstention : `None` pour les champs numériques
  (`contenance_cl`, `degre`), à côté de `non_lisible` (texte) et
  `non_determinable` (enums) — garder 75 et 13.5 typés en nombres pour qu'Excel
  puisse trier et qu'on puisse calculer dessus ; `est_abstention()` centralise
  les trois conventions en un seul endroit — écarté : mettre « non_lisible »
  partout (aurait transformé toutes les colonnes numériques en texte).

- 0027 — Enum `Couleur` = rouge | blanc | rose | non_determinable — les trois
  couleurs incontestables d'un catalogue ; « effervescent » est un type, pas une
  couleur (un champagne est blanc ou rosé) — écarté : ajouter orange/effervescent
  sans avoir vu de vrai catalogue. **Complété par 0041** (effervescence sortie en
  champ propre). La question « orange / vin doux » reste ouverte.

- 0028 — Modèle par défaut `claude-opus-5`, surchargeable par `CAVE_SCAN_MODEL` —
  le plancher doit être mesuré avec un modèle générique de haut de gamme, sinon
  on mesure la contrainte de coût, pas la capacité — écarté : figer le modèle.

- 0029 — Thinking adaptatif + `tool_choice` forcé sur l'appel VLM — lire une
  étiquette abîmée et savoir renoncer demande de la réflexion, et c'est
  exactement la compétence mesurée ; thinking désactivé fait écrire au modèle
  ses appels d'outil en texte visible — écarté : thinking désactivé.
  ⚠ **Combinaison non vérifiée contre l'API réelle** (aucune clé dans
  l'environnement de développement) : à valider au premier vrai run.

- 0030 — Pas de `strict: true` sur l'outil ; `from_tool_input()` tolérant à la
  place — le schéma utilise des types nullables (`["integer", "null"]`) dont la
  compatibilité avec le mode strict n'a pas pu être testée, et une réponse de
  travers doit produire une abstention plutôt qu'une exception — écarté :
  strict non testé, à reconsidérer dès qu'une clé permet de le vérifier.

- 0031 — Longueurs différentes entre photos et listing manuel = `ValueError`,
  pas une comparaison tronquée — comparer des bouteilles décalées produit un
  score faux ET crédible, le pire des résultats — écarté : comparer sur le
  minimum des deux longueurs.

- 0032 — Le pliage de comparaison s'arrête à casse + accents + espaces — retirer
  la ponctuation ou le préfixe « Domaine » serait normaliser, or la v0 doit
  laisser ces écarts VISIBLES pour qu'on écrive plus tard les bonnes règles
  (0007, 0008). Conséquence assumée : `13.0` vs `13` sortira en désaccord — c'est
  une information sur les conventions, pas un bug.

- 0033 — `FixtureExtractor` vit dans `src/`, pas dans `tests/` — `run_v0
  --dry-run` est un chemin de production ; le faire dépendre du code de test
  aurait inversé la dépendance — écarté : extracteur factice côté tests.

- 0034 — Champs comparés = 11 (hors `couleur_source`, `champs_a_verifier`,
  `notes`) — ce sont des métadonnées produites par le modèle, l'expert n'en
  produit pas d'équivalent : les comparer n'aurait aucun sens.

- 0035 — [remplacée par 0020] Colonne de config à `champ: null` = colonne vide — un seul mécanisme
  générique couvre le lot ET l'estimation, plutôt qu'un cas particulier codé en
  dur pour l'estimation (0005) — écarté : traiter l'estimation à part.

- 0036 — Une colonne de config qui référence un champ inexistant lève une erreur
  au chargement — une faute de frappe doit s'arrêter là, pas livrer une colonne
  silencieusement vide à une maison de vente.

- 0037 — [remplacée par 0023] Regroupement des photos : un sous-dossier par bouteille, « contre » dans
  le nom de fichier = contre-étiquette, dossier plat = une image par bouteille —
  convention v0 isolée dans `src/io/photos.py`, **à confirmer avec l'expert** ;
  si la vraie arborescence diffère, un seul fichier change.

- 0038 — Le paquet `src/io` porte le nom d'un module stdlib : ne jamais ajouter
  `src/` au `sys.path` (seulement la racine) — sinon `src/io` masque le module
  `io` de la stdlib et casse openpyxl. Verrouillé par `tests/conftest.py`.

- 0039 — `sys.stdout` forcé en UTF-8 dans `run_v0` — la console Windows est en
  cp1252 et mutilait les accents du rapport, qui est le livrable.

- 0040 — `requirements.txt` recentré sur la v0 (anthropic, openpyxl, pyyaml,
  pytest) — `requests`, `beautifulsoup4` et `rapidfuzz` servaient au scraping et
  au matching LWIN d'un périmètre antérieur, hors v0.

- 0041 — Effervescence = champ propre `effervescence` (tranquille | effervescent |
  non_determinable), orthogonal à `couleur` — un effervescent peut être blanc,
  rosé ou rouge : fusionner les deux dimensions dans `couleur` aurait forcé un
  champagne rosé à choisir entre « rose » et « effervescent », donc à perdre une
  information lisible. La catégorie précise (champagne, crémant, mousseux) n'est
  PAS un enum : c'est une appellation, elle se lit et se range dans `appellation`,
  sinon on demande au modèle de classer, donc de deviner (contre 0002/0003) —
  écarté : `effervescent` ajouté à `Couleur`, et enum détaillé par catégorie.
  Seul changement de contrat `Bouteille` depuis le squelette, validé avec le
  propriétaire du projet (CLAUDE.md l'exige).

## Robustesse (correctifs après revue du squelette)

- 0042 — `plier()` canonicalise les valeurs de type NUMÉRIQUE (75.0 → « 75»,
  12.50 → « 12.5 ») — openpyxl rend les entiers d'un .xlsx en float : sans ça,
  TOUTES les contenances et TOUS les degrés du listing expert seraient sortis en
  désaccord (accuracy 0.0), un faux signal massif. Ne s'applique JAMAIS aux
  chaînes : une cuvée « 890 » ou « 007 » reste le texte qu'elle est — écarté :
  parser aussi les chaînes numériques (aurait transformé « 007 » en « 7 »).

- 0043 — Le rapport publie deux chiffres hors accuracy : répartition de
  `couleur_source` et taux de relecture (`champs_a_verifier`) — « la couleur
  est-elle lue ou déduite ? » et « quelle charge humaine ce pipeline crée-t-il ? »
  sont des questions de décision que l'accuracy ne peut pas trancher, et les
  données étaient collectées sans être jamais agrégées.

- 0044 — `load_manual()` refuse un listing dont AUCUNE colonne ne correspond aux
  champs canoniques, et `colonnes_toujours_vides()` signale les colonnes vides
  partout — un en-tête mal mappé (« Producteur » vs `domaine`) produisait un
  rapport « manuel_vide » partout : propre, crédible et entièrement faux. Pour un
  outil de MESURE c'est la pire panne possible, elle ne se voit pas — écarté :
  échouer aussi sur un mapping partiel (l'expert a le droit de ne pas tout
  remplir), d'où l'avertissement plutôt que l'erreur dans ce cas.

- 0045 — Politique d'erreur API en deux classes : panne PASSAGÈRE (429, 5xx,
  réseau) → abstention tracée dans `notes`, la campagne continue ; panne
  SYSTÉMATIQUE (401, 403, 404, 400) → remonte et arrête tout — répéter une clé
  invalide 200 fois ne produirait que 200 lignes vides en facturant chaque
  échec. La politique vit dans `vision_extract` pour que `run_v0` reste sans
  dépendance au SDK — écarté : tout avaler (aurait masqué le risque 0029).

- 0046 — Journal `.jsonl` écrit au fil de l'eau + `--reprendre` — une campagne de
  200 bouteilles interrompue à la 180e perdait 180 appels API déjà payés ; le
  journal est aussi la trace brute des réponses, indépendante de l'Excel —
  écarté : n'écrire qu'à la fin.

- 0047 — Option de config `abstention_vide` par colonne, activée sur les colonnes
  numériques de l'exemple — « non lisible » dans une colonne de nombres casse le
  tri et le filtre du commissaire-priseur. L'abstention reste visible par le
  surlignage de la ligne et la colonne « À vérifier », donc rien n'est perdu
  (compatible 0002) — écarté : masquer partout, ou n'offrir aucun réglage.
  **À confirmer avec la maison.**

- 0048 — `_entier()` arrondit au lieu de lever (« 75.5 » → 76) — `int("75.5")`
  levait, si bien qu'un modèle ayant LU une contenance décimale s'abstenait
  silencieusement ; le centilitre est l'unité utile, la demi-mesure n'a pas de
  sens ici.

## Backend gratuit

- 0049 — Les consignes d'extraction (system prompt, libellés de rôle des photos,
  instruction finale) vivent dans `src/extract/consignes.py`, partagées par TOUS
  les extracteurs — si deux backends recevaient des prompts différents, leurs
  scores ne seraient plus comparables et la v0 ne mesurerait plus rien. Un test
  vérifie l'identité des consignes entre backends — écarté : dupliquer le prompt
  par fournisseur.

- 0050 — 2e extracteur : Gemini (`--backend gemini`, défaut), palier GRATUIT —
  contrainte budgétaire du projet ; c'est le 2e cas d'usage qui justifiait
  d'emblée le Protocol `Extractor` (0014), et aucun autre module n'a bougé.
  Sortie contrainte par `response_json_schema`, alimenté par le `tool_schema()`
  existant : `schema.py` reste la source unique (0001 respecté, pas d'OCR, pas
  de parsing de texte libre).
  **Deux réserves à porter dans toute lecture d'un score produit par ce
  backend** : (a) le palier gratuit est *Flash uniquement*, donc le chiffre qui
  décidera de la suite du projet doit être rejoué sur un modèle de tête —
  un plancher mesuré avec un petit modèle sous-estime la technologie et
  pourrait faire conclure à tort qu'il faut entraîner un modèle maison ;
  (b) Google peut exploiter les entrées/sorties du palier gratuit, ce qui est à
  trancher avec la maison avant d'y envoyer les photos de ses lots.

- 0051 — Sur Gemini, un 429 est le RÉGIME NOMINAL, pas un incident (~15
  requêtes/minute en gratuit) : appels espacés de 4,5 s et jusqu'à 4 tentatives
  avec attente croissante avant de renoncer — sans cela, la moitié d'une
  campagne serait sortie en abstention et le score aurait été faux. La
  distinction passager/systématique de 0045 est conservée à l'identique.

---

## Questions ouvertes (trancher avec l'expert)

- Fichier Excel réel de la maison pilote (en-têtes exacts, valeurs utilisées)
  → première config.
- Valeurs exactes de l'état de l'étiquette dans la nomenclature de la maison.
- Source de données pour l'estimation future.
- La maison accepte-t-elle que les photos de ses lots transitent par un palier
  gratuit dont le fournisseur peut exploiter les données (0050) ? Si non :
  backend payant, ou modèle local.
