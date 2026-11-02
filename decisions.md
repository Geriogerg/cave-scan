# Journal de décisions — v0

Décisions techniques qui cadrent la v0. Une ligne chacune :
`NNNN — décision — raison — alternative écartée`. Les décisions stratégiques
(marché, suite) sont dans ROADMAP.md, pas ici. Seules les décisions EN VIGUEUR
sont ici ; les décisions remplacées sont dans `docs/decisions-archive.md`, avec
un renvoi d'une ligne à leur place.

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

- 0005 — archivée (règle devenue la contrainte dure n° 2 de CLAUDE.md ; colonne vide via 0020) → docs/decisions-archive.md

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

- 0011 — archivée (précisée par 0020 : config JSON) → docs/decisions-archive.md

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

- 0019 — archivée (remplacée par 0162) → docs/decisions-archive.md

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

- 0023 — archivée (remplacée par 0166) → docs/decisions-archive.md

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

- 0035 — archivée (remplacée par 0020) → docs/decisions-archive.md

- 0036 — archivée (remplacée par 0052) → docs/decisions-archive.md

- 0037 — archivée (remplacée par 0023) → docs/decisions-archive.md

- 0038 — Le paquet `src/io` porte le nom d'un module stdlib : ne jamais ajouter
  `src/` au `sys.path` (seulement la racine) — sinon `src/io` masque le module
  `io` de la stdlib et casse openpyxl. Verrouillé par `tests/conftest.py`.

- 0039 — `sys.stdout` forcé en UTF-8 dans `run_v0` — la console Windows est en
  cp1252 et mutilait les accents du rapport, qui est le livrable.

- 0040 — archivée (remplacée par 0060, puis 0070) → docs/decisions-archive.md

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

- 0045 — archivée (remplacée par 0079) → docs/decisions-archive.md

- 0046 — archivée (remplacée par 0079) → docs/decisions-archive.md

- 0047 — archivée (remplacée par 0055) → docs/decisions-archive.md

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

- 0051 — archivée (rythme et tentatives repris par 0079 et 0114) → docs/decisions-archive.md

## Session 1 — config par maison

- 0052 — Config JSON validée STRICTEMENT au chargement, toutes les erreurs
  rassemblées dans un seul message : clés JSON en double détectées (le module
  `json` garde silencieusement la dernière, d'où un `object_pairs_hook`),
  clés inconnues refusées (préfixe « _ » = commentaire), types et sources
  connus, `cle` et en-têtes uniques (à la casse près), codes et libellés
  uniques, `non_determinable` réservé et ajouté d'office à chaque liste,
  `canonique` ⇔ noyau 0021, colonnes système limitées à ce que l'outil sait
  calculer (`id`, `a_verifier`), quantité forcément expert, aucune colonne
  modèle sur un champ du pipeline, nature d'un champ v0 (texte | liste |
  nombre) non modifiable, regroupement limité aux colonnes lues par le modèle
  — une config mal écrite ne doit jamais produire un export plausible et faux
  — écarté : valider au fil de l'usage (l'erreur surgirait en plein export).

- 0053 — Un texte envoyé au modèle qui contient un exemple de réponse (citation
  entre guillemets, « par exemple », « ex. ») est SIGNALÉ au chargement, pas
  refusé — c'est du few-shot (CLAUDE.md), mais la config appartient à la
  maison : on rend le conflit visible plutôt que de le trancher à sa place.
  maison_test.json en contient un (description de `description_etat`) —
  écarté : bloquer (empêcherait la maison d'écrire ses consignes), ou ignorer.

- 0054 — Contrat `Bouteille` étendu : `id` (système), `quantite` (expert, 1
  par défaut), `valeurs_maison` (colonnes propres à la maison, par clé) ; et
  `couleur`, `effervescence`, `format` typés `str` — ils portent un CODE, celui
  de l'enum v0 ou celui du vocabulaire de la maison quand sa config redéfinit
  le champ (maison_test.json a des couleurs et des formats absents des enums
  v0). Les enums restent le vocabulaire par défaut ; leurs membres étant des
  `str`, le code existant et le test de comparaison sont inchangés — écarté :
  ranger les listes de maison à part (le même champ aurait eu deux valeurs).

- 0055 — Export : une abstention (`non_lisible`, `non_determinable`) s'affiche
  en case VIDE et la ligne est surlignée (CLAUDE.md). Une ligne est surlignée
  si une case lue par le modèle est vide pour abstention, si un code sort du
  vocabulaire de la maison (affiché tel quel, jamais masqué), ou si le modèle
  signale un doute PRÉCIS. Les champs best effort, toujours dans « À
  vérifier », ne surlignent pas à eux seuls — sinon toutes les lignes le
  seraient et le surlignage ne dirait plus rien — écarté : surligner dès que
  « À vérifier » n'est pas vide (règle v0).

- 0056 — Version de la config copiée dans les propriétés du classeur (titre
  « maison — config vN », champ version, nom du fichier de config) — lisible
  dans Fichier > Propriétés sans ajouter de feuille ni de ligne qui casserait
  l'import du fichier chez la maison — écarté : une feuille « Infos ».

- 0057 — `load_manual(chemin, config)` lit le fichier de l'expert dans la
  langue de la maison : en-têtes reconnus par le `nom` des colonnes de la
  config, libellés de liste ramenés à leur code (on compare des codes). Une
  valeur ni libellé ni code reste telle quelle et ressort en désaccord. La
  table d'en-têtes codée en dur (issue d'exemple.yaml) disparaît : la config
  la remplace — écarté : garder une table d'alias dans le code.

- 0058 — Un texte qui commence par « = » est écrit comme TEXTE dans l'Excel —
  un texte lu sur une étiquette ne doit jamais devenir une formule exécutée à
  l'ouverture du fichier par la maison.

- 0059 — `id`, `quantite` et `valeurs_maison` ne sont jamais demandés au
  modèle, et ignorés s'il les renvoie (`from_tool_input` = source non fiable).
  Le journal d'extraction se relit par `bouteille_depuis_dict` (source de
  confiance) : identifiant, quantité et codes de maison y sont conservés au
  lieu d'être rabattus sur l'enum v0 — écarté : une seule fonction de lecture
  (le modèle aurait pu fixer une quantité).

- 0060 — archivée (remplacée par 0070) → docs/decisions-archive.md

- 0061 — Schéma envoyé au modèle = champs v0 de CLAUDE.md (« Champs à
  extraire ») + colonnes `modele` / `modele_best_effort` de la config. Une
  colonne de config qui porte le nom d'un champ v0 en redéfinit la description
  et le vocabulaire (ses codes deviennent l'enum). Le noyau canonique étant
  parmi les champs v0, il est toujours extrait même si la config ne l'affiche
  pas (0021) ; les champs v0 non affichés restent extraits pour la comparaison
  et le journal — la config décide de l'affichage, pas de la mesure. Colonnes
  expert et système : jamais ajoutées (vérifié sur la requête envoyée, pour les
  deux backends). La consigne d'abstention est ajoutée PAR LE CODE à chaque
  colonne : « ne jamais deviner » ne dépend pas de la rédaction de la maison —
  écarté : un schéma fait des seules colonnes de la config (on aurait perdu
  les champs mesurés par la v0).

- 0062 — Lecture avec la config : chaque colonne best effort est ajoutée à
  `champs_a_verifier` par le code, toujours et une seule fois (CLAUDE.md), sans
  dépendre du modèle ; les colonnes propres à la maison vont dans
  `valeurs_maison` ; un code hors vocabulaire devient `non_determinable`.

- 0063 — Signaux du rapport : les champs best effort sont exclus des « doutes »
  et affichés à part (« toujours à vérifier ») — sinon le taux de relecture
  vaudrait 100 % quelle que soit la qualité de lecture, et ne mesurerait plus
  rien. `compare_listings` reçoit leurs noms, pas la config : il reste du code
  plat.

- 0064 — Prompt : le paragraphe EFFERVESCENCE précise que la couleur suit le
  vocabulaire propre à son champ, même s'il mêle couleur et type de vin (la
  config de test classe « champagne » parmi les couleurs). Changement minimal,
  commun aux deux backends, toujours sans exemple.

- 0065 — Identifiant stable = empreinte SHA-256 du CONTENU des photos de la
  bouteille (« B- » + 10 caractères), posé par le pipeline : identique d'un run
  à l'autre et insensible au renommage des fichiers (photos absentes du disque,
  au dry-run : empreinte du chemin). Deux bouteilles au même identifiant (photo
  copiée deux fois) arrêtent le run AVANT tout appel au modèle ; `--reprendre`
  refuse un journal qui ne correspond plus aux photos (sinon décalage silencieux
  de toutes les lignes reprises) — écarté : un numéro d'ordre (change dès qu'on
  insère une photo), un UUID (change à chaque run).

- 0066 — Regroupement à l'EXPORT seulement : en interne une ligne reste une
  bouteille (comparaison et journal ne voient jamais de regroupement).
  Égalité STRICTE sur les clés de `regroupement_export` (pas de pliage, ce
  serait normaliser). Une bouteille À RELIRE n'est jamais fusionnée : elle
  garde sa ligne pour que ses cases vides restent visibles — donc une
  abstention sur une clé n'est jamais une égalité (on fusionnerait un magnum et
  une bouteille au format illisible). Quantités additionnées, identifiants tous
  listés, doutes réunis ; une colonne hors clé qui diffère garde toutes ses
  valeurs, jointes par « / ». Conséquence assumée : sur des gros plans, le
  format est non déterminable, donc rien ne se regroupe tant qu'il n'est pas
  renseigné. Découvert en cours de route : la première version (fusion dès que
  les clés sont égales) masquait l'abstention d'une bouteille derrière la
  valeur de l'autre — un test l'a révélé — écarté : fusionner sur les seules
  clés.

- 0067 — archivée (remplacée par 0082) → docs/decisions-archive.md

- 0068 — archivée (remplacée par 0166) → docs/decisions-archive.md

- 0069 — Paire incohérente : question technique `photos_meme_bouteille`
  (oui | non | non_determinable) posée au modèle — pas un champ de `Bouteille`.
  « non » -> `paire_photos` dans `champs_a_verifier` (doute précis : la ligne
  est surlignée) et une note. La consigne finale ne présuppose plus que les
  photos montrent la même bouteille : l'affirmer aurait dissuadé le modèle de
  signaler une erreur d'appariement.

- 0070 — archivée (remplacée par 0158) → docs/decisions-archive.md

- 0071 — Sortie d'erreur aussi en UTF-8 (étend 0039) : les refus de config et
  de photos s'affichaient avec des accents mutilés, au moment précis où il faut
  les lire. Clé Gemini absente -> message clair renvoyant à `.env`, plus de
  trace Python brute. Appel de fonction automatique du SDK Gemini coupé
  explicitement (aucun appel de fonction ici ; il était actif par défaut et
  l'annonçait par un avertissement à chaque run).

## Session 2 — bibliothèque + base de données

- 0072 — La sortie brute du modèle est IMMUABLE : stockée telle que reçue, jamais
  réécrite ni supprimée (garde posée sur le modèle de données lui-même, pas
  seulement une convention). Une correction de l'expert est un enregistrement
  séparé (champ, ancienne valeur, nouvelle valeur, auteur, date). La valeur
  affichée = sortie du modèle relue avec la config de l'inventaire, remplacée
  par la dernière correction de chaque champ ; elle est RECALCULÉE à chaque
  lecture, jamais stockée — il n'existe donc jamais deux vérités — écarté :
  écrire la valeur corrigée par-dessus l'extraction.

- 0073 — Config figée par inventaire : `config_version` garde le texte complet
  du JSON et une empreinte SHA-256 de sa forme canonique (clés triées, sans
  espaces — une simple remise en forme ne crée pas de version). Nouvelle
  version dès que l'empreinte change, numérotée par un compteur propre à
  chaque maison ; le numéro déclaré dans le JSON est conservé à côté, et un
  AVERTISSEMENT s'affiche si le contenu a changé sans que ce numéro ait été
  incrémenté. L'export d'un inventaire relit SA version, jamais le fichier —
  écarté : relire le JSON à chaque export (l'export d'un inventaire changerait
  après coup).

- 0074 — Photos copiées dans un stockage géré par l'outil, nommées par leur
  SHA-256 complet ; la base ne garde que le chemin RELATIF au stockage et
  l'empreinte (le stockage peut être déplacé). Une même photo déposée deux fois
  dans un inventaire est refusée à la création ; présente dans deux
  inventaires, elle n'est stockée qu'une fois. Jamais d'image dans la base —
  écarté : pointer vers le dossier d'origine (que l'utilisateur peut déplacer).

- 0075 — SQLite en local via SQLAlchemy 2 (ORM déclaratif), pour passer à
  PostgreSQL sans réécrire ; schéma créé et modifié UNIQUEMENT par migrations
  Alembic (mode « batch », nécessaire pour modifier une table sous SQLite),
  jamais par `create_all` ; un test vérifie que les migrations correspondent
  exactement aux modèles. Base et stockage configurables par variables
  d'environnement (`CAVE_SCAN_DB`, `CAVE_SCAN_STOCKAGE`), par défaut sous
  `data/`, jamais versionné.

- 0076 — Chaque extraction trace : modèle, version du prompt, tokens d'entrée
  et de sortie, durée, date, erreur. Version du prompt = empreinte de TOUT ce
  qui part au modèle (consignes + schéma de la maison) : deux runs de même
  version ont reçu exactement la même demande. Tokens de sortie Gemini =
  réponse + réflexion (les deux sont facturés). Durée mesurée par le service
  autour de l'appel : pauses de quota et nouvelles tentatives comprises, c'est
  le temps réel par bouteille.

- 0077 — Protocol `Extractor` : `extraire_brut() -> SortieModele` (réponse brute,
  modèle, version du prompt, tokens, erreur), et `extract() -> Bouteille`
  CONSTRUIT à partir d'`extraire_brut()` — une seule implémentation par
  fournisseur. `extraire_brut()` ne lève que pour une panne systématique ;
  tout autre résultat revient comme une donnée — écarté : faire mémoriser à
  l'extracteur ses derniers tokens (état caché).

- 0078 — La réponse brute est ENREGISTRÉE AVANT d'être interprétée : si
  l'interprétation échoue (JSON illisible, réponse vide, bogue), ce que le
  modèle a répondu reste en base, l'erreur est notée sur l'extraction et la
  bouteille passe en erreur — un appel payé n'est jamais perdu.

- 0079 — Trois classes d'erreurs à l'extraction : SYSTÉMATIQUES (clé invalide,
  modèle inconnu, requête mal formée) -> enregistrées, puis l'inventaire
  s'arrête ; PASSAGÈRES (limite de débit, délai dépassé, serveur surchargé ou
  en erreur) -> quelques nouvelles tentatives à délai croissant, puis erreur
  sur la bouteille, sans bloquer les autres ; RÉPONSE INEXPLOITABLE -> erreur
  sur la bouteille seule. Une erreur imprévue est traitée comme systématique
  (mieux vaut s'arrêter que répéter un bogue sur 300 bouteilles). Après un
  arrêt, `--inventaire ID` reprend là où on s'est arrêté : les bouteilles
  extraites ne sont jamais refaites, celles en erreur sont retentées.

- 0080 — Logique métier dans des fonctions de service à session de base et
  stockage EXPLICITES (pas d'état global, pas de couche « repository », pas de
  bus d'événements). `run_v0.py` et `inventaire.py` n'appellent que ces
  fonctions et ne font qu'afficher.

- 0081 — La comparaison au listing de l'expert mesure la SORTIE DU MODÈLE seule,
  sans les corrections, et le rapport le dit ; sinon chaque correction de
  l'expert gonflerait le score du modèle. Les corrections sont mesurées à part
  par `stats_inventaire` (champs les plus corrigés).

- 0082 — `corriger` accepte les colonnes lues par le modèle ET les colonnes de
  source expert (estimation comprise) ; il refuse un champ inconnu et les
  colonnes système. Saisie validée selon le type : quantité = entier ≥ 1,
  liste = code connu (un libellé de la maison est ramené à son code), nombre =
  nombre, texte = libre. L'export affiche la saisie de l'expert ; le modèle ne
  peut toujours rien écrire dans une colonne expert (CLAUDE.md). La quantité
  courante est portée par la bouteille, son historique par les corrections.

- 0083 — archivée (remplacée par 0169) → docs/decisions-archive.md

- 0084 — Ligne de commande : `--journal`, `--reprendre` et `--auto` sont
  remplacés par `--inventaire ID` (reprendre, réexporter, rescorer depuis la
  base) et `--base` ; les utiliser affiche l'option qui les remplace, pas une
  erreur générique. `--limite N` s'applique à la création de l'inventaire.
  Nouvelle commande `inventaire.py` : lister, bouteilles, stats, corriger,
  valider, exporter.

- 0085 — `--dry-run` travaille sur une base et un stockage TEMPORAIRES, avec des
  photos générées : le vrai chemin de création (appariement, empreintes,
  stockage) est exercé hors ligne, et la base de l'utilisateur n'est jamais
  touchée. Les tests isolent de même base et stockage.

- 0086 — Dates en base : UTC, sans fuseau — SQLite ne stocke pas de fuseau ; une
  seule convention évite de mélanger heure locale et UTC selon le poste.

- 0087 — Contraintes NOMMÉES par convention (Alembic ne sait modifier sous SQLite
  que des contraintes nommées, sinon la première évolution du schéma bloque).
  Clés étrangères VÉRIFIÉES à chaque connexion SQLite (désactivées par défaut :
  une bouteille orpheline passait), mais PAS pendant les migrations (le mode
  batch recopie les tables, ce qu'elles feraient échouer). Les tests tournent
  sur une base modèle construite UNE fois par les vraies migrations puis copiée
  — jamais `create_all`, qui testerait un autre schéma.

- 0088 — L'immuabilité est posée sur le modèle de données lui-même (événements
  SQLAlchemy) : modifier la sortie brute, le modèle, la version du prompt ou les
  tokens d'une extraction, ou la supprimer, lève une erreur ; seule `erreur`
  peut être complétée après coup (0078). Une correction n'est jamais modifiée
  ni supprimée. Limite connue : du SQL écrit à la main contournerait ces gardes
  — tout le code passe par l'ORM.

- 0089 — Dépendances : SQLAlchemy et Alembic ajoutés. Restent : google-genai,
  anthropic, openpyxl, pillow, python-dotenv, pytest.

- 0090 — `creer_inventaire` vérifie TOUT avant d'écrire quoi que ce soit : config
  valide, maison demandée = maison décrite par la config, appariement (impair,
  format illisible, sous-dossier), puis photos en double par empreinte. Les
  doublons sont cherchés APRÈS l'appariement : un nombre impair reste signalé
  comme tel, c'est le défaut le plus courant. Le dossier d'origine n'est gardé
  que pour mémoire ; les bouteilles pointent vers les copies du stockage.

- 0091 — Stockage : le nom garde l'extension en minuscules (elle donne le type
  d'image envoyé au modèle), et la copie passe par un fichier temporaire
  renommé à la fin — une coupure en pleine copie ne laisse jamais une photo
  tronquée sous un nom valide.

- 0092 — Gemini : délai dépassé, connexion coupée (erreurs réseau que le SDK
  n'enveloppe PAS dans ses erreurs d'API) et code 408 sont des pannes
  PASSAGÈRES, réessayées à délai croissant — sans ce classement, un simple
  délai dépassé aurait arrêté tout l'inventaire comme une clé invalide.
  Anthropic : le SDK réessaie lui-même ; le nombre de tentatives (3) est fixé
  explicitement plutôt que laissé au défaut.

- 0093 — archivée (remplacée par 0110) → docs/decisions-archive.md

- 0094 — L'extracteur de fixtures se déclare comme modèle « fixtures », avec des
  tokens NON MESURÉS (vides) — jamais un faux coût qui fausserait le coût par
  bouteille ; sa version de prompt est celle qu'aurait reçue un vrai modèle
  pour la même maison.

- 0095 — Dans les services, l'historique d'une bouteille (extractions,
  corrections) est LU par une requête explicite, jamais par une liste chargée
  plus tôt dans la session ; il est ÉCRIT en rattachant l'enregistrement à la
  bouteille. Découvert par les tests : une liste chargée une fois (pour
  calculer l'« ancienne valeur ») restait figée, et une correction ajoutée
  ensuite n'apparaissait pas dans les valeurs courantes.

- 0096 — Saisie de l'expert : une quantité accepte « 3 » comme 3 mais refuse 0,
  2,5, « cinq » ; un nombre accepte la virgule française (« 13,5 ») ;
  `non_determinable` est une saisie valide pour une liste (« je ne peux pas
  trancher » est une réponse) ; un texte est libre. Une correction est
  possible quel que soit le statut — l'expert peut renseigner une bouteille
  en erreur —, mais ne la rend pas validable pour autant. Les corrections
  survivent à une relance forcée : elles s'appliquent à la nouvelle
  extraction.

- 0097 — Non-régression vérifiée sur PIÈCES : mêmes photos, mêmes fixtures, on
  produit l'export par le chemin de la session 1 et depuis la base, et on
  compare valeurs, types de cellule, surlignage, polices, largeurs, gel des
  en-têtes et propriétés du fichier — identiques. L'export depuis la base
  réutilise `ecrire_excel` sans le modifier : seule la source des valeurs
  change.

- 0098 — Coût par bouteille = tokens de TOUTES ses extractions (relances et
  réponses inexploitables comprises : elles sont facturées), rapportés aux
  bouteilles qui ont consommé des tokens mesurés. Une extraction sans mesure
  (fixtures, panne survenue avant toute réponse) ne pèse pas et est comptée à
  part : jamais un faux zéro qui ferait baisser la moyenne.

- 0099 — Le rapport de comparaison porte, sous son titre, la mention « SCORE DU
  MODÈLE : sa sortie brute, sans les corrections de l'expert » (0081) — ajoutée
  sans modifier les lignes existantes. Export, statistiques et comparaison
  vivent dans `src/services/restitution.py` : ils lisent à la fois les
  inventaires et la relecture, les ranger dans l'un des deux aurait créé une
  dépendance circulaire.

- 0100 — `inventaire.py` a aussi une commande `fiche ID BOUTEILLE` : valeur lue
  par le modèle, valeur courante, historique des corrections, extractions (et
  celle qui fait foi). C'est elle qui permet de constater qu'une correction n'a
  pas touché l'extraction d'origine (validation finale du guide, point 3). Une
  bouteille se désigne par sa position ou son identifiant B-… ; `--base`
  s'accepte avant comme après la commande ; `--auteur` est obligatoire.

- 0101 — Garde-fou des tests : une fixture automatique retire les clés d'API de
  l'environnement et neutralise la lecture de `.env` — aucun test ne peut
  appeler un vrai modèle, même par accident (le `.env` contient une vraie clé ;
  un appel réel accidentel a eu lieu en session 1). Les tests de la ligne de
  commande branchent leurs extracteurs à la place de `run_v0._extracteur`.

- 0102 — `.env` est lu par les DEUX lignes de commande, via
  `src/config/environnement.py` : il porte aussi la base et le stockage, et un
  `.env` lu par un seul script ferait travailler `run_v0.py` et `inventaire.py`
  sur deux bases différentes sans le dire. Une variable déjà définie dans
  l'environnement l'emporte.

- 0103 — La normalisation (identité, 0007) s'applique à la LECTURE des valeurs
  du modèle (`valeurs_modele`), jamais à la réponse brute stockée : ses règles
  futures vaudront aussi pour les inventaires déjà extraits, et la comparaison
  mesure, comme en session 1, la sortie normalisée. Sans ce branchement, la
  suppression de `run_v0.extraire` l'aurait déconnectée du pipeline.

- 0104 — `--dry-run --base FICHIER` garde l'inventaire de démonstration dans
  cette base, pour essayer `inventaire.py` sans clé ; ses photos vont alors dans
  le stockage configuré, pour que la base ne pointe jamais vers des fichiers
  effacés. Sans `--base`, tout reste temporaire (0085).

- 0105 — Ligne de commande : `--photos`, `--inventaire ID` et `--dry-run` sont
  exclusifs ; sur une reprise, `--maison`, `--limite` et `--nom` sont ignorés
  avec un avertissement (config figée, 0073). Tout arrêt survenu après la
  création de l'inventaire — panne systématique, Ctrl-C, clé absente, Excel
  ouvert — affiche la commande de reprise `--inventaire ID`, code de sortie 2 ;
  le listing manuel est vérifié AVANT tout appel au modèle.

- 0106 — `session_de_base()` : la ligne de commande ouvre la base par un
  gestionnaire de contexte qui migre, puis ferme le moteur en sortant (sous
  Windows, un fichier SQLite encore ouvert ne peut être ni déplacé ni supprimé —
  le dossier temporaire du dry-run).

- 0107 — archivée (liste d'adaptation de tests de la session 2, appliquée) → docs/decisions-archive.md

- 0108 — archivée (remplacée par 0166) → docs/decisions-archive.md

---

## Session 3 — tâches de fond + API

- 0109 — File d'attente EN BASE (pas de Redis ni de Celery) : le statut des
  bouteilles est la file. Une bouteille est réservée de façon ATOMIQUE par une
  seule fonction, `reserver_bouteille()` — sous SQLite un `UPDATE … WHERE
  statut = 'a_extraire' … RETURNING` ; au passage à PostgreSQL, `FOR UPDATE SKIP
  LOCKED` ne changera qu'elle. Deux workers ne peuvent jamais réserver la même
  bouteille.

- 0110 — [remplace 0093] « en_cours » = réservation VIVANTE : la bouteille porte
  qui l'a réservée, quand, et un horodatage de vie mis à jour pendant le
  traitement. Une bouteille en cours dont l'horodatage dépasse le délai
  d'abandon (configurable) est remise à extraire ; si sa réponse était déjà en
  base (arrêt entre l'enregistrement de la réponse et le statut), elle est
  terminée SANS nouvel appel — jamais un appel payé deux fois.

- 0111 — Chaque inventaire a un état d'extraction (non_lancee, lancee, annulee,
  arretee) : le worker ne réserve que dans les inventaires lancés. Lancer,
  annuler et relancer les erreurs sont des actions explicites et idempotentes ;
  annuler laisse les bouteilles non commencées « à extraire », celles en cours
  terminent. Une panne systématique passe l'inventaire à « arretee » avec son
  motif : aucun worker ne continue.

- 0112 — Les bouteilles en erreur ne sont plus retentées automatiquement : c'est
  l'action « relancer les erreurs ». La ligne de commande `--inventaire ID`
  garde son comportement (relancer les erreurs, lancer, extraire au premier
  plan) ; un Ctrl-C y libère proprement la réservation.

- 0113 — SQLite en mode WAL avec `busy_timeout` ; transactions courtes, une
  session par tâche, aucune transaction ouverte pendant l'appel au modèle (les
  chemins des photos sont lus avant).

- 0114 — Limite de débit PARTAGÉE en base (table `limite_debit`) : espacement
  minimal entre deux appels à un modèle, et pause commune après une limite de
  débit atteinte — on ralentit tous les workers au lieu de multiplier les
  tentatives. Rien en mémoire : un redémarrage la respecte.

- 0115 — Parallélisme : un processus worker, un pool de threads borné (4 par
  défaut, configurable). Les appels au modèle attendent le réseau : des threads
  suffisent, sans multiprocessing.

- 0116 — Envoi des photos par l'API : chaque fichier est réellement ouvert
  (Pillow), limites de taille par fichier et de nombre par inventaire (au moins
  600), noms nettoyés ; puis `creer_inventaire` est réutilisé tel quel, avec
  tous ses garde-fous (impair, doublons). HEIC refusé avec un message clair tant
  que pillow-heif n'est pas installé (0070).

- 0117 — Photos servies uniquement par une route qui vérifie qu'elles
  appartiennent à l'inventaire demandé. Version réduite (rotation EXIF
  appliquée) et version pleine taille, toutes deux RÉENCODÉES sans aucune
  métadonnée (qualité 95) : l'« original » brut porterait l'EXIF, dont la
  position GPS de la cave. Le fichier stocké reste intact.

- 0118 — API FastAPI, couche fine : format d'erreur unique `{code, message,
  detail}` en français, chaque exception de service traduite en un seul endroit ;
  aucune logique dans les routes. L'auteur d'une correction est fourni dans la
  requête via une dépendance, et toutes les routes passent par une dépendance
  d'accès vide aujourd'hui : la connexion (session 7) les remplacera sans
  réécrire les routes. Écoute sur 127.0.0.1 uniquement.

- 0119 — Lancement : `python serveur.py` (API), `python worker.py` (worker),
  `python dev.py` (les deux, pour le développement).

- 0120 — archivée (remplacée par 0138 : pas de validation en masse) → docs/decisions-archive.md

- 0121 — Migration 0003 (accord donné le 2026-10-09) : état d'extraction de
  l'inventaire, réservation et horodatage de vie des bouteilles, table
  `limite_debit`. Le contrat `Bouteille` ne change pas.

- 0122 — Backend `factice` (`worker.py --backend factice --latence N`) : sans
  réseau ni clé, une latence réglable et une réponse plausible mais fausse —
  pour développer et tester le worker sans quota. Il journalise chaque appel
  (début, fin, processus) : c'est ce journal qui prouve, même entre processus et
  après un arrêt brutal, qu'aucune photo n'est appelée deux fois en même temps.

- 0123 — Worker : l'extracteur est créé PAR BOUTEILLE avec la config figée de son
  inventaire (pas de cache en mémoire) ; la clé est vérifiée au démarrage. Une
  erreur imprévue (base, disque) rend la bouteille à la file au lieu de la
  bloquer « en cours ». `--jusqu-a-vide` s'arrête quand plus rien n'est à
  extraire dans un inventaire lancé NI en cours nulle part — il attend donc la
  reprise des bouteilles abandonnées avant de conclure.

- 0124 — `dev.py` fait tourner le worker dans un thread de son propre processus
  (et non dans un sous-processus) : l'arrêter, même brutalement, arrête les
  deux — jamais de worker orphelin sous Windows. En production, `serveur.py` et
  `worker.py` restent deux processus. `serveur.py` n'a aucune option d'hôte :
  127.0.0.1 en dur jusqu'à la connexion (session 7).

- 0125 — Validation réelle de la session 3 (2026-10-10, 12 étiquettes, Gemini
  palier gratuit) : serveur, documentation, création par l'API, worker tué en
  pleine extraction puis relancé — reprise sans doublon (exactement une
  extraction par bouteille). Mais 10 bouteilles sur 12 en erreur 429 : le quota
  gratuit (20 requêtes/jour) n'était pas renouvelé. Temps et coût réels par
  bouteille NON mesurés : reportés au premier essai avec des crédits.

---

## Session 4 — dépôt des photos (écrans web)

- 0126 — Inventaire en BROUILLON (migration 0004, accord donné le 2026-10-10) :
  créé avec son nom et sa maison (config figée dès ce moment), il reçoit ses
  photos une par une, en plusieurs fois. « Finaliser » vérifie les garde-fous,
  forme les bouteilles et lance l'extraction ; ensuite, plus aucune modification
  de photos. Le chemin « tout d'un coup » (ligne de commande, POST /inventaires)
  est conservé.

- 0127 — Envoi idempotent : par empreinte du CONTENU reçu (unique en base) ; et,
  pour ne pas RENVOYER une photo déjà reçue après une coupure, par une signature
  du fichier d'origine (nom, taille, date de modification) que le navigateur
  demande au serveur avant d'envoyer. Pas d'empreinte SHA-256 dans le navigateur :
  elle n'y est disponible qu'en HTTPS, pas sur le réseau local en HTTP.

- 0128 — archivée (remplacée par 0166) → docs/decisions-archive.md

- 0129 — archivée (remplacée par 0166) → docs/decisions-archive.md

- 0130 — Réduction avant envoi (navigateur, côté long 2 500 px, JPEG qualité
  0,9) : implémentée mais DÉSACTIVÉE par défaut tant que son effet sur
  l'extraction n'est pas mesuré (`mesurer_reduction.py`, à lancer avec des
  crédits). L'option « envoyer les originaux » reste disponible.

- 0131 — Écrans : pages générées côté serveur (Jinja2) + HTMX (fichier local, ni
  CDN ni outil de build) + un seul fichier de JavaScript simple pour l'envoi. Les
  pages vivent sous /app (« / » y mène), dans la même application que l'API, et
  appellent les mêmes fonctions de service ; tout garde-fou est vérifié côté
  serveur.

- 0132 — [remplace en partie 0124] Écoute sur le réseau local seulement avec
  l'option explicite `--reseau-local` (serveur.py, dev.py) : avertissement au
  démarrage et adresse à ouvrir sur le téléphone. Sans elle : 127.0.0.1.

- 0133 — Miniatures générées à la réception (stockage/miniatures/, rotation
  appliquée, sans métadonnées) et servies par la route sécurisée des photos.
  Supprimer une photo d'un brouillon ne supprime pas son fichier : le stockage
  est adressé par contenu et peut être partagé.

- 0134 — Envois simultanés : chaque modification d'un brouillon commence par
  prendre le verrou d'écriture (sur la ligne de l'inventaire), pour que deux
  photos arrivant en même temps reçoivent des positions distinctes.

- 0135 — Test de navigation de bout en bout avec Playwright (Chromium, écran
  au format téléphone), dépendance de test seulement : c'est le seul moyen de
  tester le JavaScript d'envoi (date lue avant réduction, reprise).

- 0136 — Mesure de la réduction : `mesurer_reduction.py` extrait chaque photo en
  original puis réduite (côté long N, JPEG 0,9, comme le navigateur) et compte,
  champ par champ, les lectures PERDUES par rapport à l'original (référence :
  la lecture de l'original, faute de listing de l'expert). Constat du
  2026-10-10 : les 12 photos d'essai sont passées par WhatsApp (≤ 2048 px,
  157 Ko en moyenne, AUCUNE date EXIF) — inutilisables pour cette mesure ; il
  faut des originaux du téléphone. Taille retenue : à noter ici après la mesure.

## Session 5 — écran de relecture

- 0137 — Contexte réorganisé : `CLAUDE.md` court (toujours chargé), règles par
  domaine dans `.claude/rules/` avec des `paths` vérifiés sur les vrais fichiers
  du repo (sinon la règle ne se charge jamais), guides passés dans
  `docs/sessions/archive/`, décisions remplacées dans
  `docs/decisions-archive.md` avec un renvoi d'une ligne — écarté : un seul
  gros fichier relu à chaque session.

- 0138 — [remplace 0120] Pas de validation en masse : « valider l'inventaire »
  ne valide plus aucune bouteille, il CONSTATE que toutes ont été validées une
  par une (sinon refus, avec le nombre restant) et passe l'inventaire à
  « relu » — chaque bouteille doit avoir été vue par l'expert (règle web) —
  écarté : supprimer l'action (on perd « reste-t-il du travail ? »), ou la
  garder dans l'API seule (contradiction maintenue).

- 0139 — Migration 0005 (accord donné le 2026-10-10) : table
  `evenement_bouteille` (bouteille, type, auteur, date, détail) pour tracer
  réanalyse, inversion, signalement et séparation ; colonnes de bouteille
  `paire_signalee`, `separee_de_id`, `temps_relecture_ms`. Le contrat
  `Bouteille` ne change pas — écarté : tout mettre dans les corrections (ce ne
  sont pas des valeurs de champ).

- 0140 — Bouteille séparée : le regroupement de l'export reste celui de la
  config de la maison ; si les deux fiches sont identiques sur les clés de
  regroupement, l'écran AVERTIT l'expert qu'elles seront fusionnées à l'export
  (accord du 2026-10-10) — écarté : ne jamais fusionner une bouteille séparée
  (du code qui passe outre la config, contrainte 6).

- 0141 — Services de l'écran de relecture : `cas_particuliers` (réanalyser,
  inverser les photos, signaler une paire, séparer — chaque action tracée dans
  `evenement_bouteille`), la lecture de l'écran dans `consultation` (fiche,
  navigation, compteurs, récapitulatif), et `valeurs_courantes_de_l_inventaire`
  qui calcule les 300 bouteilles en 3 requêtes, avec le même calcul que
  `valeurs_courantes` (testé). Une bouteille en erreur montre une raison EN
  CLAIR par catégorie (panne passagère, réponse illisible, refus, panne
  systématique), jamais le message technique — écarté : une requête par
  bouteille à chaque page (trop lent sur 300).

- 0142 — Modification concurrente : la page porte la VERSION de la bouteille
  affichée (dernière correction, dernière extraction, dernier événement).
  Enregistrer sur une version périmée lève `ModificationConcurrente` (409), qui
  dit ce qui a changé et par qui ; rien n'est écrit sans « enregistrer quand
  même ». Une saisie identique à la valeur courante n'ajoute rien à
  l'historique — écarté : un verrou sur la bouteille (un onglet oublié
  bloquerait l'expert).

- 0143 — Valider depuis l'écran renvoie TOUT le formulaire : le serveur
  enregistre d'abord ce qui diffère de l'affichage (règles de `corriger`), garde
  les saisies valides et refuse la validation si une saisie est invalide, avec
  la raison par champ. Le garde-fou est côté serveur, pas seulement dans le
  navigateur. Une abstention s'affiche VIDE (« à remplir ») et un champ resté
  vide signifie « inchangé » : renvoyer un formulaire intact n'écrit rien —
  écarté : n'envoyer que les champs modifiés (le navigateur seul déciderait).

- 0144 — Séparer : nouvelle bouteille aux MÊMES photos, placée juste après sa
  source (les suivantes reculent), identifiant « B-…-2 », « -3 »… ; elle lit
  l'extraction de sa source tant qu'elle n'a pas la sienne (aucun nouvel appel)
  et reprend ses corrections, pour partir des mêmes valeurs. Les quantités sont
  réparties par des corrections, la somme est conservée ; seule une bouteille
  analysée, de quantité ≥ 2, se sépare. Les corrections écrites par la
  séparation sont listées dans son événement et exclues des statistiques de
  corrections (sinon double compte) — écarté : une bouteille vierge (l'expert
  devrait refaire ses corrections, et l'export divergerait).

- 0145 — Paire signalée : colonne `paire_signalee` ; la bouteille ne peut plus
  être validée, par aucune voie (écran, API, ligne de commande), et une
  bouteille validée qu'on signale redevient à relire. Le signalement se lève
  (erreur de l'expert), tracé. Elle n'est pas proposée par « suivante à
  relire » : elle attend au récapitulatif.

- 0146 — archivée (remplacée par 0169) → docs/decisions-archive.md

- 0147 — Réanalyser remet UNE bouteille « à extraire » : le worker l'extrait
  (aucun appel au modèle depuis l'écran). Seulement si l'analyse de
  l'inventaire est lancée (annulée ou arrêtée : la relancer depuis le suivi,
  sinon toutes les bouteilles non commencées repartiraient). Validée, elle
  redevient à relire, tracé ; l'ancienne extraction reste, les corrections
  restent prioritaires.

- 0148 — Version réduite des photos (affichage) préparée une fois sur disque
  (`stockage/reduites`), comme les miniatures : passer d'une bouteille à la
  suivante ne réencode rien. Écriture atomique dans un fichier partiel propre à
  chaque demande — préchargement et affichage peuvent la demander en même temps.

- 0149 — Tests adaptés (liste annoncée avec le plan de session 5, approuvée le
  2026-10-10), chacun gardant son exigence : `test_valider_l_inventaire_…` →
  refus tant qu'une bouteille n'est pas validée une par une, puis constat ;
  parcours de l'API → validation bouteille par bouteille, puis constat ; Excel
  toujours identique à la ligne de commande.

- 0150 — Auteur des corrections faites depuis les écrans : `CAVE_SCAN_AUTEUR`
  (défaut « Expert »), affiché en tête de la relecture, en attendant la
  connexion (session 7). L'API garde l'en-tête `X-Auteur` — écarté : demander
  un nom à chaque ouverture (sans connexion, rien ne le vérifierait).

- 0151 — Écran de relecture : une PAGE par bouteille (adresse propre, retour
  arrière du navigateur), champs dans l'ordre de la config. Chaque champ est
  enregistré à sa sortie par HTMX, en file d'attente sur le formulaire
  (`hx-sync … queue all` : la requête suivante part avec la version renvoyée
  par la précédente) ; la réponse ne remplace JAMAIS la saisie, seulement
  l'en-tête (origine) et le pied (état) du champ — une frappe en cours n'est
  jamais écrasée. Valider soumet tout le formulaire (fonctionne aussi sans
  JavaScript), puis la bouteille suivante à relire s'ouvre, ou le
  récapitulatif. Un refus (422) ou une modification faite ailleurs (409) est
  une réponse à afficher, pas une panne.

- 0152 — `relecture.js`, seulement ce que le navigateur impose : raccourcis
  (J = précédente, K = suivante, dans l'ordre du guide ; aucun raccourci à une
  lettre ni flèche dans un champ, Échap pour en sortir) ; zoom à la molette, au
  double-clic ou Z, déplacement au glisser, l'original pleine résolution
  chargé dès qu'on zoome ; E pour l'autre photo ; état de l'enregistrement,
  nouvel essai après une coupure (1 s, 2 s, 4 s… 30 s), changement de bouteille
  bloqué tant qu'une saisie n'est pas enregistrée ; temps actif. Tab depuis la
  page va au premier champ, contenu sélectionné.

- 0153 — Préchargement : `<link rel="prefetch">` des photos réduites de la
  bouteille suivante (servies avec un cache navigateur d'une heure) — écarté :
  précharger la page HTML suivante (elle change à chaque validation).

- 0154 — API de la relecture : les mêmes services que l'écran. `version`
  FACULTATIVE sur une correction, un retour à la valeur du modèle, une
  validation : périmée, 409 `modification_concurrente` avec les changements en
  `detail` ; absente, aucune vérification (les clients de la session 3 restent
  valides). Nouvelles routes : revenir, reanalyser, inverser-photos,
  signalement (POST / DELETE), separer (201, la nouvelle bouteille),
  recapitulatif. Les chiffres de relecture sont dans les statistiques de
  `GET /inventaires/{id}` et de `inventaire.py stats`.

- 0155 — Formulaire de relecture en `novalidate` : le navigateur ne bloque
  rien en silence (un `min="1"` HTML empêchait l'envoi d'une quantité 0 sans
  aucun message) ; le serveur juge chaque saisie et dit pourquoi il la refuse.

- 0156 — Tests navigateur de la relecture (Playwright, Chromium 1440×900, vrai
  `dev.py`, extracteur factice, aucune pause fixe) : 10 bouteilles uniquement
  au clavier (liste, texte, quantité, refus, raccourcis tapés dans un champ,
  navigation, export, auteur, temps) ; deux onglets (avertissement,
  « enregistrer quand même », historique) ; une coupure de réseau (« erreur,
  nouvel essai », changement de bouteille bloqué, rien de perdu) ; 300
  bouteilles — passage à la
  suivante mesuré à 170 ms en médiane (seuil du test : 500 ms), photos de la
  suivante préchargées pendant la relecture de la courante.

---

## Session 6 — configuration, groupes de photos, cycle de vie de l'inventaire

- 0157 — Port au démarrage (serveur.py, dev.py) : sans `--port`, 8000, sinon
  le premier port libre jusqu'à 8019, ANNONCÉ en français ; un `--port` imposé
  et occupé n'est jamais remplacé en silence : arrêt (code 2) avec un message
  en français. Vérifié AVANT tout démarrage : dev.py ne crée le worker qu'une
  fois le port obtenu (le 2026-10-10, uvicorn échouait en anglais pendant que
  le worker, déjà lancé, appelait Gemini). Vérification par une tentative
  d'écoute aussitôt libérée ; un port réservé par Windows (« accès refusé »)
  compte comme occupé — écarté : laisser uvicorn échouer ; ouvrir la socket
  nous-mêmes et la passer à uvicorn (lancement testé à réécrire pour une
  fenêtre de concurrence négligeable).

- 0158 — [remplace 0070 ; en partie 0068 et 0116 pour le HEIC] Photos HEIC
  d'iPhone LUES : `pillow-heif` ajouté (inscrit auprès de Pillow par
  `src/io/heic.py`, importé par tout module qui ouvre une photo). Au dépôt, le
  contenu décide (un HEIC nommé .jpg est reconnu), le fichier est stocké TEL
  QUEL ; miniature, version réduite et original servis en JPEG sans
  métadonnées, comme les autres. Pour le modèle, conversion en JPEG
  (qualité 95, orientée, SANS métadonnées) au moment de l'appel, dans
  `lire_photo` : les deux fournisseurs reçoivent la même image et l'un
  n'accepte pas le HEIC. En ligne de commande, un HEIC illisible arrête le run
  AVANT tout appel — écarté : convertir à la réception (le fichier reçu ne
  serait plus celui de l'expert) ; envoyer le HEIC tel quel à Gemini (les deux
  backends ne liraient plus la même image).

- 0159 — Plafond de photos par bouteille : clé racine
  `photos_max_par_bouteille` de la config de la maison (1 à 10, 4 par défaut :
  étiquette, contre-étiquette, capsule, bouteille entière), modifiable dans la
  page Configuration et figée avec l'inventaire. Chaque photo envoyée au modèle
  se paie (choix du 2026-10-11) — écarté : un réglage global dans `.env` (une
  maison ne pourrait pas l'ajuster).

- 0160 — [remplace en partie 0066] Regroupement de l'export : colonnes lues par
  le modèle OU saisies par l'expert ; seules les colonnes calculées par l'outil
  (id, à vérifier) sont refusées. Deux lots ou deux caisses différents ne
  fusionnent jamais ; deux bouteilles sans lot saisi restent fusionnables.
  Une abstention sur une clé LUE empêche toujours la fusion (0066) — écarté :
  regrouper sur les seules colonnes lues (deux bouteilles identiques de lots
  différents deviendraient une ligne « 12 / 13 »).

- 0161 — [remplace en partie 0020 : l'éditeur dans l'interface existe]
  Configuration d'une maison par la page « Configuration » ou par import d'un
  JSON (`src/services/configuration.py`). Le fichier de `config/maisons/` reste
  LA config active (la ligne de commande le lit, contrainte 6) : chaque
  enregistrement est validé exactement comme un fichier, rien n'est écrit tant
  qu'il reste une erreur (chaque erreur listée à part), le numéro de version
  est fixé par l'outil (le précédent + 1, signalé si le fichier importé en
  disait un autre), le fichier est remplacé d'un coup, puis la version est
  enregistrée en base (exportable, et un inventaire garde celle de sa
  création). Refusés : un contenu identique à la version active, une page
  ouverte sur une version périmée (rien n'est écrasé), un changement de nom de
  maison (ce serait une autre maison : on l'importe). Une maison nouvelle
  importée reçoit un fichier nommé d'après elle. L'aperçu de chaque colonne
  montre le morceau de schéma EXACT envoyé au modèle (`propriete_modele`), ou
  « jamais envoyée » — écarté : configs en base seulement (la ligne de
  commande et le README reposent sur le fichier) ; un brouillon de config en
  base (état caché entre deux pages).

- 0162 — [remplace 0019] Champs du pilote dans la config de test (version 2) :
  ceux de 0019, plus `niveau` et `etat_capsule` (best effort, avec la règle
  « seulement si une photo montre le col… sinon non déterminable »), `caisse`
  (CBO, carton, sans) et `numero_lot` (texte), saisis par l'expert : une photo
  de bouteille ne montre pas la caisse. L'exemple de réponse de
  `description_etat` est retiré (few-shot, contrainte 7). Le regroupement
  porte aussi sur niveau, capsule, caisse et lot. Conséquence assumée : tant
  que niveau et capsule restent « non déterminables » (gros plans
  d'étiquette), la ligne est à vérifier et ne fusionne pas, comme pour le
  format (0066). Bouchon : hors pilote.

- 0163 — Page « Configuration » (/app/configuration, lien depuis l'accueil) :
  liste des maisons (un fichier invalide est montré avec ses erreurs), import
  d'un JSON, édition d'une maison. Chaque action (ajouter, monter, descendre,
  retirer une colonne ; ajouter, retirer une valeur ; changer type ou source ;
  vérifier) renvoie TOUTE la config, que le serveur réaffiche : aucun état
  gardé entre deux demandes, rien d'écrit avant « Enregistrer la version N ».
  Une clé ou un code déjà enregistrés ne se modifient pas (champs cachés : les
  inventaires s'y réfèrent) ; ceux d'une nouveauté sont créés à partir du nom
  ou du libellé s'ils sont laissés vides. `canonique` est posé par l'outil.
  Sous chaque colonne, « Ce que reçoit le modèle » ; les consignes générales
  sont consultables. Historique des versions, chacune téléchargeable. Quitter
  avec des modifications non enregistrées est signalé par le navigateur. Sans
  JavaScript, tout fonctionne en simples envois de formulaire — écarté : un
  éditeur JSON brut (illisible pour une maison) ; un éditeur en JavaScript
  (la logique et les garde-fous resteraient côté serveur de toute façon).

- 0164 — [remplace en partie 0049 (libellés de rôle) et 0069 (wording)]
  Toutes les photos d'UNE bouteille partent dans le MÊME appel, dans l'ordre de
  l'expert, chacune précédée de « Photo n sur N : », SANS rôle imposé
  (étiquette, contre-étiquette) : l'expert photographie librement et le modèle
  n'utilise que ce qu'il voit. La consigne finale dit que les photos ont été
  regroupées par l'expert et que le modèle doit le vérifier
  (`photos_meme_bouteille`, 0069). Le Protocol devient
  `extraire_brut(photos)` / `extract(photos)` : une photo seule ou la liste des
  photos d'une bouteille (jamais vide). Les libellés restent partagés par les
  deux backends (testé) ; la version du prompt change avec eux — écarté :
  garder des rôles (il faudrait les deviner, ou les faire saisir pour chaque
  photo).

- 0165 — Garde-fou de taille d'un appel : au-delà de la limite du fournisseur
  (Gemini : 20 Mo par requête ; Anthropic : 5 Mo par image, 32 Mo par requête ;
  base64 compris), l'appel serait refusé (400), refus classé « panne
  systématique » qui arrêterait TOUT l'inventaire. Seules les photos les plus
  lourdes sont alors réduites (côté long 3 000 px, puis 2 500, 2 000…, JPEG
  qualité 90, sans métadonnées, toujours depuis l'original), pour cet appel
  seulement ; le fichier stocké ne change jamais, une bouteille sous la limite
  part telle quelle (0130, réduction à l'envoi désactivée, reste vraie), et
  la réduction est notée dans le journal du worker — écarté : refuser la
  bouteille (l'expert ne saurait que faire) ; passer par l'API de fichiers de
  Gemini (un appel réseau de plus par photo, rien pour Anthropic).

- 0166 — [remplace 0023, 0068, 0108, 0128, 0129 ; en partie 0116, 0126, 0141,
  0145] Une bouteille = un GROUPE de photos (1 à N, plafond de la maison,
  0159), tel que l'expert l'a constitué : plus d'appariement étiquette /
  contre-étiquette par ordre, plus de tri par date de prise de vue (gardée
  pour information), plus d'option « étiquettes seules ». Schéma (migration
  0006, accord du 2026-10-11) : table `groupe_photos` (inventaire, numéro
  d'ordre de prise de vue, clé donnée par l'appareil, quantité saisie à la
  capture) ; `photo.groupe_id` + `rang` ; `bouteille.groupe_id` ;
  `photo_etiquette_id`, `photo_contre_id`, `inventaire.sans_contre`,
  `ordre_manuel` supprimées. Reprise : chaque paire devient un groupe
  (étiquette = photo 1, contre = photo 2), une bouteille séparée partage le
  groupe de sa source, un brouillon est découpé comme l'aurait fait l'ancien
  lancement ; tout est vérifié AVANT d'écrire ; extractions, corrections,
  événements, identifiants intouchés (vérifié sur une copie de la base réelle :
  7 inventaires, 32 bouteilles, aller et retour sans perte). Retour arrière
  possible tant qu'aucun groupe n'a plus de deux photos. Ligne de commande :
  une photo à la racine du dossier = une bouteille, un sous-dossier = une
  bouteille et toutes ses photos (ordre naturel des noms) ; `--sans-contre`
  devient une option remplacée. API « tout d'un coup » : photos dans l'ordre
  d'envoi, `photos_par_bouteille` (« 2,2,1 ») ou une par bouteille ; un total
  qui ne correspond pas est refusé (on ne devine jamais). Identifiant :
  empreinte des photos dans leur ordre — inchangé pour une ancienne paire. En
  relecture : toutes les photos, numérotées, `E` / `Maj+E` ; « Inverser les
  photos » disparaît avec les rôles (le type d'événement reste pour
  l'historique) ; « problème de paire » devient « problème de photos » pour
  l'expert, noms internes inchangés (l'historique les porte) — écarté :
  garder des rôles (étiquette, contre, capsule…) à saisir pour chaque photo
  (un geste de plus par photo, et le modèle n'en a pas besoin).

- 0167 — Dépôt bouteille par bouteille (`services/depot.py`, `depot.js`) :
  chaque photo part avec la CLÉ de sa bouteille (donnée par l'appareil) et son
  numéro d'ordre de prise de vue ; le serveur crée le groupe à la première
  photo, range les bouteilles par numéro (une photo peut arriver avant celle
  d'une bouteille précédente sur un réseau qui coupe) et les photos d'une
  bouteille dans leur ordre d'arrivée — le navigateur envoie donc les photos
  d'UNE bouteille une à la fois, plusieurs bouteilles en parallèle. Mode
  appareil photo : la bouteille en cours, compteur « n / plafond », « × N »,
  « Bouteille suivante », « Reprendre » une bouteille précédente. Mode galerie
  ou ordinateur : une carte par bouteille, « Ajouter ses photos ». Une photo
  prise depuis la page n'existe nulle part ailleurs : gardée dans le
  navigateur (IndexedDB) jusqu'à ce que le serveur l'ait reçue, la bouteille en
  cours survit à un rechargement (testé dans un vrai navigateur) ; si le
  navigateur ne peut pas la garder, un message le dit. Limite connue : si le
  téléphone ferme le navigateur pendant que l'appareil photo est ouvert, la
  photo qui venait d'être prise ne revient pas — le compteur le montre.
  « Vérifier et lancer » : retirer une photo, « Nouvelle bouteille à partir
  d'ici » (couper), « Rattacher à la précédente » (plafond tenu), supprimer une
  bouteille, quantité. Lancer forme une bouteille par groupe en attente, à la
  fin de l'inventaire ; on peut AJOUTER des bouteilles après le lancement par
  les mêmes écrans (l'analyse repart, le temps restant estimé repart de ce
  lancement) ; les photos d'une bouteille formée ne bougent plus. Le suivi
  signale les bouteilles ajoutées pas encore lancées — écarté : un viseur
  dans la page (exige HTTPS) ; garder toutes les photos de la galerie dans le
  navigateur (elles restent dans la galerie, et le stockage du navigateur est
  limité).

- 0168 — Cycle de vie de l'inventaire (migration 0007, accord du 2026-10-11) :
  on le commence, l'arrête, le reprend, le modifie, et on le CLÔT quand on est
  sûr. Rien ne se supprime : « supprimer » = corbeille (`supprime_le`) — plus
  aucun écran ni aucune route ne l'ouvre, son analyse s'arrête, il se restaure
  (choix 1 du 2026-10-10 : un effacement réel violerait la contrainte 4) ;
  « archiver » range hors de la liste sans rien fermer ; « clore »
  (`clos_le`) met en LECTURE SEULE (corrections, validations, cas
  particuliers, dépôt, relance, renommage refusés côté serveur ; l'export
  reste possible), permis sans tout avoir validé (avertissement, et ce qui ne
  l'est pas est noté dans la trace), refusé tant qu'une bouteille n'a pas sa
  ligne (pas encore analysée, ou ajoutée et pas lancée) ; « rouvrir » est
  permis, confirmé et tracé (choix 7 et 8). Retirer une bouteille (`retiree`)
  : hors relecture, export, comptes et file d'attente, elle garde sa place
  (positions) et ses données, se remet depuis le récapitulatif. Chaque geste
  est tracé avec son auteur : table `evenement_inventaire` (renommage,
  archivage, désarchivage, suppression, restauration, clôture, réouverture),
  types « retrait » / « remise » pour `evenement_bouteille` ; historiques
  immuables. L'analyse se met en pause et reprend depuis le suivi (l'ancien
  « annuler »). Corbeille, clôture et réouverture passent par une page de
  confirmation qui dit ce qui va se passer — écarté : effacer pour de bon
  (extractions immuables, 0072) ; clore seulement quand tout est validé
  (valider reste facultatif, choix du 2026-10-11).

- 0169 — Statut d'inventaire : `ouvert` | `valide` ; il passe à `valide` quand
  toutes ses bouteilles le sont (valider reste facultatif, 0168). Une bouteille
  EXTRAITE se valide ; une bouteille dont l'analyse a ÉCHOUÉ aussi, en « saisie
  manuelle », une fois ses champs obligatoires saisis — les colonnes du noyau
  canonique (domaine, appellation, millésime, format) présentes dans la config
  de la maison (choix 2 du 2026-10-10) ; sinon le refus dit ce qui manque. Une
  correction (ou une relance forcée) sur une bouteille validée la remet à
  relire : `extraite`, ou `erreur` si aucune analyse n'a réussi ; l'inventaire
  repasse à `ouvert`. Validation et remise à relire sont tracées dans
  l'historique des corrections (champ « statut », auteur, date ; « erreur » ->
  « validée » = saisie manuelle), sans colonne supplémentaire. Temps de
  relecture : mesuré par l'écran (temps actif, onglet visible, pause au-delà de
  60 s sans clavier ni souris), CUMULÉ par bouteille, borné à 1 h par envoi ;
  envoyé avec la validation, et SANS validation en quittant la bouteille (et
  chaque minute, par `sendBeacon` vers `.../temps`) : une bouteille ouverte et
  non validée compte aussi ; une validation refusée garde son temps pour
  l'envoi suivant. Une mesure, pas une modification : comptée même sur un
  inventaire clos — remplace 0083 et 0146 — écarté : une bouteille en erreur
  jamais validable (un modèle qui échoue toujours sur une photo bloquait
  l'inventaire) ; ne compter que le temps des bouteilles validées.

- 0170 — Excel : une ligne par bouteille, toujours (choix du 2026-10-11).
  `exporter` est REFUSÉ (`ExportRefuse`, 409 `export_refuse` ; bouton
  remplacé par ce qui manque dans le suivi et le récapitulatif) tant qu'une
  bouteille n'est pas encore analysée ou qu'une bouteille ajoutée n'est pas
  lancée — la règle de la clôture (0168). Valider n'est pas requis. Une
  bouteille en erreur a sa ligne : fond rouge pâle (`F4CCCC`, distinct du jaune
  « à relire »), « Erreur d'analyse » dans « À vérifier » ; validée en saisie
  manuelle, « Saisie manuelle » (fond normal). Ces lignes ne sont JAMAIS
  fusionnées par le regroupement (leurs valeurs vides ou saisies se
  ressembleraient). Colonne système facultative `relue` : « oui » si l'expert
  a validé la bouteille. Une config sans colonne `a_verifier` reste valide,
  avec un avertissement (une erreur ne s'y verrait qu'à la couleur). Les
  bouteilles retirées n'ont pas de ligne. La comparaison au listing et les
  signaux du modèle ne comptent pas les bouteilles nées d'une séparation : une
  bouteille = un groupe de photos lu une fois ; insérée après sa source, elle
  décalait l'alignement ligne à ligne (0010) — écarté : exporter en laissant
  tomber les bouteilles pas encore analysées (perte silencieuse) ; exporter
  sans les erreurs.

- 0171 — Une instance de l'application = une maison (demande de l'utilisateur,
  2026-10-13) : chaque maison a sa propre installation, avec SA configuration,
  qu'elle modifie à sa guise. Aucune page ne nomme ni ne fait choisir la
  maison : « Nouvel inventaire » demande seulement le nom de la vente ;
  « Configuration » ouvre directement la configuration ; un fichier importé
  devient sa nouvelle version, quel que soit le nom de maison qu'il porte. La
  configuration de l'instance est le fichier de `config/maisons/` (s'il y en a
  plusieurs : `CAVE_SCAN_MAISON`, à défaut le premier par nom). Les données
  (table des maisons, versions figées par inventaire), l'API et la ligne de
  commande (`--maison`) gardent la notion de maison : le format reste piloté
  par sa config JSON (contrainte 6) — écarté : supprimer la notion de maison des
  données (migration sans bénéfice, et les inventaires passés y sont liés).

  (Le choix « à défaut, la première par nom de fichier » est remplacé par
  0182 : sans désignation, aucune.)

- 0172 — La configuration se crée à la main, sans JSON (demande de
  l'utilisateur, 2026-10-13) : sans configuration, la page propose « Créer la
  configuration », qui part des colonnes de base (N°, quantité, domaine,
  appellation, millésime, format, à vérifier — le noyau canonique est toujours
  lu) ; l'expert ajoute ensuite ses colonnes une à une dans l'éditeur (nom,
  type, source, description, règle, valeurs d'une liste) et enregistre. Le
  résultat est un fichier JSON comme un autre (contrainte 6), validé de la même
  façon. L'import d'un JSON reste possible — écarté : un assistant pas à pas
  (l'éditeur fait déjà tout, sur la même page).

- 0173 — Consignes générales modifiables par la maison, avec garde-fous
  (demande de l'utilisateur, 2026-10-13). Le texte envoyé au modèle a trois
  parties : deux FIXES, qui portent les contraintes dures de CLAUDE.md (ne
  jamais deviner, valeurs d'abstention, millésime et format jamais devinés ;
  aucun prix), toujours envoyées, jamais modifiables ; et une partie du milieu
  (couleur, effervescence, champs à vérifier…), que la maison réécrit sur la
  page Configuration. Elle vit dans la config (clé facultative `consignes`,
  versionnée et figée par inventaire comme le reste) ; absente, c'est le texte
  d'origine, envoyé au caractère près. Double confirmation : « Modifier les
  consignes » demande « êtes-vous sûr ? » avant de déverrouiller, puis
  l'enregistrement exige la case « Je confirme modifier les consignes »,
  vérifiée par le serveur. La version du prompt suit le texte réellement
  envoyé ; un exemple de réponse dans les consignes déclenche l'avertissement
  few-shot — écarté : tout le texte modifiable (les contraintes dures
  pourraient être retirées) ; consignes figées dans le code (demande de
  l'utilisateur).

- 0174 — Dossier de configuration réglable, tests isolés, score signalé
  (recommandations R2 et R5, boucle qualité, tour 3). `CAVE_SCAN_CONFIGS`
  désigne le dossier de la configuration de l'application (défaut
  `config/maisons/`), comme `CAVE_SCAN_DB` et `CAVE_SCAN_STOCKAGE` ;
  l'application, `run_v0.py` (configuration par défaut = celle de
  l'application), `mesurer_reduction.py` et `dev.py` le lisent. Les tests y
  mettent leur copie figée (`tests/fixtures/maison_test.json`) : la suite passe
  avec `config/maisons/` vide comme avec une colonne renommée. Le rapport de
  score (et les signaux sans listing) avertit quand l'inventaire a été lu avec
  des consignes modifiées : ce score ne se compare pas aux autres. Les tests
  ne comparent plus de phrase de plus de 40 caractères (R3), vérifié par
  `tests/test_style_des_tests.py` — écarté : vérifier l'isolement par un simple
  grep (aveugle aux lectures indirectes, T3-R2).

- 0175 — Corbeille et analyse (boucle qualité, tour 4, lot 15). Mettre une
  bouteille à la corbeille ne met l'analyse en pause que s'il reste des
  bouteilles à analyser ; une analyse finie le reste. La restauration remet
  « lancée » une analyse qu'une corbeille avait arrêtée sans rien laisser à
  lire. En pause sans rien à analyser, « Réanalyser » relance seul ; en pause
  AVEC des bouteilles à analyser, le refus de 0147 tient, et son message dit
  « Reprendre l'analyse » — écarté : autoriser la réanalyse pendant une pause
  (deux lectures concurrentes).

- 0176 — Relecture protégée des doubles appuis et des pages périmées (tour 4,
  lot 16). Une validation acceptée ferme la page aux suivantes ; un appui AU
  BOUTON dans les 500 ms qui suivent l'affichage d'une bouteille est ignoré,
  le clavier non (l'expert enchaîne Entrée) ; une touche Entrée maintenue
  (répétition) est ignorée. Les écrans sont servis en `Cache-Control:
  no-store`, et une page restituée par le retour arrière du navigateur se
  recharge : jamais de valeur périmée prise pour la bonne. Un formulaire
  classique ne part qu'une fois — écarté : un délai pour toute validation
  (ralentit l'expert au clavier) ; des en-têtes de revalidation (le retour
  arrière les ignore).

- 0177 — Photo indécodable refusée à la réception (tour 4, lot 16). La photo
  est décodée à son arrivée : tronquée, « abîmée » ; au-delà de la limite de
  pixels de Pillow, « trop de pixels » ; refus en clair, dans sa carte
  (contrainte 5). Côté écran, une erreur serveur qui n'est pas un passage
  (502, 503, 504) n'est réessayée que deux fois : au troisième échec, la photo
  est dite refusée et n'est plus renvoyée — écarté : réessayer sans fin
  (dépôt bloqué en « Coupure »).

- 0178 — Limites de saisie et d'adresse (tour 4, lots 16 à 20). Quantité au
  plus 100 000, texte au plus 1 000 caractères (compteur au-delà de 900,
  collage coupé annoncé). Un numéro de plus de 18 chiffres dans une adresse
  donne « page introuvable » (404), pas une erreur serveur. Une erreur 404
  pendant la relecture dit « n'est plus disponible : rechargez la page » et la
  saisie n'est pas comptée comme enregistrée (contrainte 5).

- 0179 — Configuration : versions et colonnes (tour 4, lots 19 et 21).
  « Revenir à cette version » enregistre l'ancienne version comme une NOUVELLE
  version (l'historique ne se réécrit jamais ; les inventaires passés gardent
  la leur) ; la version active est marquée. Une colonne ajoutée s'insère avant
  les colonnes calculées de fin (« À vérifier »…). L'identifiant d'une valeur
  tiré de son libellé suit le libellé tant que l'expert ne l'a pas écrit —
  écarté : restaurer en réécrivant le fichier sans nouvelle version (perte de
  trace).

- 0180 — Millésime inhabituel signalé, jamais refusé (tour 4, lot 21). Une
  saisie qui n'est ni 4 chiffres (1600–2099) ni « NM » est enregistrée telle
  que tapée, avec « Inhabituel : 4 chiffres (ex. 2015) ou NM attendus. » sous
  le champ — écarté : la refuser ou la corriger (l'expert peut avoir raison,
  et l'outil ne devine jamais à sa place).

- 0181 — Choix de la boucle qualité confirmés par l'utilisateur (2026-10-14,
  docs/tests/choix_a_trancher.md n° 1 à 6) : quantité plafonnée à 100 000 ;
  texte libre à 1 000 caractères ; photo collée en haut pendant la saisie au
  téléphone ; colonnes de la configuration repliées ; barre « Annuler /
  Vérifier / Enregistrer » masquée tant que rien n'est modifié ; dépôt ouvert
  en mode galerie à l'ordinateur.

- 0182 — Plusieurs configurations dans le dossier, aucune désignée : l'outil
  ne choisit plus (décision de l'utilisateur, 2026-10-14, choix n° 7). Sans
  `CAVE_SCAN_MAISON`, un dossier qui contient plusieurs configurations valides
  n'en donne aucune : un bandeau rouge « Plusieurs configurations trouvées »
  le dit sur Configuration et Nouvel inventaire (aucune création possible),
  et la ligne de commande s'arrête avec la même raison. Remplace « la
  première par nom de fichier » (0171, 0174) — écarté : la première par ordre
  alphabétique (un ancien fichier déposé à côté changeait la configuration en
  silence : 9 colonnes devenaient 16).

- 0183 — Bouteille validée : jamais surlignée dans l'Excel (décision de
  l'utilisateur, 2026-10-14, choix n° 8). « Validée » veut dire relue par
  l'expert : sa ligne n'est plus surlignée et sa colonne « À vérifier » est
  vide, même si une case est restée vide pour abstention (la case reste VIDE :
  jamais devinée, contrainte 1). En échange, valider une bouteille dont le
  format ou le millésime est vide le dit aussitôt, sur la bouteille suivante
  (« Bouteille n°X validée — Format vide : il restera vide dans l'Excel »),
  sans bloquer. Modifie 0055 pour les bouteilles validées ; inchangé pour les
  autres — écarté : garder le jaune après validation (l'expert ne pouvait pas
  dire « rien à lire ici ») ; exiger une seconde validation (un format
  illisible est normal sur un gros plan d'étiquette : presque chaque
  validation serait doublée).

- 0184 — Fusion de la branche de la boucle qualité autorisée (décision de
  l'utilisateur, 2026-10-14, R6) : `boucle-qualite` avance `main` en avance
  rapide (jamais de fusion avec conflit, jamais de push) : maintenant pour
  tout ce qui est fait, puis à la fin de chaque tour corrigé et à l'arrêt de
  la boucle, toujours avec la suite complète verte.

- 0185 — Saisies démesurées et noms de vente (boucle qualité, tour 5, lot 22).
  Une quantité n'est convertie qu'à 6 chiffres ASCII au plus (`quantite_valide`,
  partagée par Vérifier, le lancement, la relecture et Séparer) : au-delà, ou
  « ² », un refus en clair, jamais une erreur serveur ; la saisie citée est
  coupée à 20 caractères. Le nom d'une vente est borné à 200 caractères côté
  serveur aussi, les caractères de contrôle remplacés par une espace
  (`nom_de_vente`). Des consignes égales au texte d'origine (au blanc près)
  sont les consignes d'origine — écarté : refuser les caractères de contrôle
  (un collage depuis un tableur en contient).

- 0186 — Relecture pendant une analyse (tour 5, lot 23). Tant que le modèle n'a
  pas lu une bouteille, « Valider » est grisé avec sa raison (Ctrl+Entrée la
  dit) ; le bandeau dit « en pause » ou « pas encore lancée » quand rien ne
  bougera seul ; aucune « Note du modèle » n'est fabriquée. La fin de la
  lecture recharge la page avec « Le modèle a lu la bouteille ». Le bouton
  Valider est atténué pendant son délai de garde de 500 ms (0176). Vérifier
  sans rien en attente renvoie au suivi, avec la raison.

- 0187 — Configuration en clair (tour 5, lot 24). Les refus emploient les mots
  de la page (types, sources, « Photos au plus par bouteille ») ; un
  identifiant déjà pris est la seule cause dite pour sa colonne ; un fichier
  sans colonne : un seul refus. Avertissements (sans bloquer) pour une
  configuration sans « À vérifier », sans quantité, sans « N° » ou sans une
  colonne du noyau. L'identifiant d'une nouvelle colonne suit son nom jusqu'à
  l'enregistrement. Libellés des types et sources : une seule source
  (`maison.py`).

- 0188 — Dépôt (tour 5, lots 25 et 26). « Ajouter une bouteille » montre la
  carte vide existante au lieu d'en créer une seconde ; une photo déjà choisie
  le dit dans sa carte ; la barre de progression disparaît une fois tout
  envoyé ; deux onglets sur le même dépôt se signalent (BroadcastChannel) ;
  les bouteilles faites en galerie se voient en mode appareil photo ; une photo
  lâchée hors d'une carte est refusée en clair. Accords singulier / pluriel au
  lieu de « (s) » (filtre `accord`) — écarté : une clé de bouteille par onglet
  (une photo gardée pour la reprise ne retrouverait plus sa bouteille).

- 0189 — Relecture au téléphone et récapitulatif (tour 5, lot 27). Au
  téléphone : navigation sur une ligne (mots courts), photo à 26 % de
  l'écran, vignettes sur une rangée, pour lire le premier champ sans
  défiler. Inventaire clos : « Télécharger l'Excel » est l'action principale.

- 0189 bis — Configuration : refus menant à leur colonne (tour 5, lot 28).
  Chaque refus qui cite une colonne est un lien vers elle ; la colonne ajoutée
  est mise en vue, son nom prêt à taper (cherchée après le « settle »
  d'HTMX, qui garde un instant les attributs de l'ancien élément de même id) ;
  les aperçus ouverts le restent après « Vérifier » ; l'alerte d'exemple de
  réponse se répète sous les consignes ; une version reprise d'une autre le
  dit (« reprise de la version N », par comparaison des contenus au numéro de
  version près).

- 0190 — L'avis de validation va avec sa bouteille (tour 6, lot 31). Vers la
  bouteille suivante : en-tête lu par la page, rangé avec le numéro de
  l'inventaire, jamais affiché dans un autre. Vers le récapitulatif (dernière
  bouteille) : `?validee=<id>`, le récapitulatif le dit. Au téléphone, un
  libellé de bouton long passe à la ligne plutôt que d'être coupé ; le refus
  d'une quantité s'affiche sous l'en-tête de sa carte, qui ne bouge pas ; le
  récapitulatif prend la colonne des autres écrans — écarté : un libellé sur
  une seule ligne à tout prix (coupé au téléphone, T6-D1).

- 0191 — Valider d'un seul appui au téléphone (tour 6, lot 32). Au toucher,
  « Valider » part au relâchement du doigt (même délai de garde que le clic,
  0176 ; le clic qui suivrait est ignoré) : un champ qui perd le focus déplace
  la mise en page entre l'appui et le relâchement, et le navigateur n'envoyait
  alors aucun clic (T6-B1). Pendant la saisie, les vignettes sont effacées
  mais gardent leur place — écarté : les retirer de la mise en page (la
  validation restait perdue). Une bouteille que le modèle n'a pas lue
  n'affiche aucun « doute du modèle ». Au dépôt, une quantité refusée reste
  dans son champ, comme sur Vérifier.

- 0192 — Accords et guillemets (tour 6, lot 33). Un seul accord, `src/textes.py`
  (`accord`), pour les écrans (filtre) et les messages des services qui
  atteignent l'expert ; la ligne de commande garde ses « (s) » (outil de
  développeur). Les guillemets « » qui se séparaient de leur mot en fin de
  ligne prennent des espaces insécables. La clôture n'affiche plus un message
  en double : le bandeau « Inventaire clos le … » suffit.

- 0193 — Finitions d'écrans (tour 6, lot 34). Une photo déjà reçue, rechoisie
  après un rechargement, est dite dans sa carte, sans vignette ; la page
  Configuration a le même fil d'Ariane et le même sous-titre dans tous ses
  états ; le motif d'un signalement ou d'un retrait se saisit avant son bouton ;
  « Exemplaires à séparer » au lieu de « ex. » ; au téléphone, le récapitulatif
  met chaque libellé au-dessus de sa valeur.

- 0194 — Clôture et valeurs de liste (tour 6, lot 35). La confirmation de
  clôture nomme les bouteilles non validées (12 au plus, puis « et N autres ») ;
  « Ajouter une valeur » met le curseur dans la nouvelle ligne.

- 0195 — Relecture (tour 7, lot 36). La confirmation « Bouteille n°X validée »
  est rangée avec son inventaire, comme l'avis (0190) : jamais affichée dans
  une autre vente. Une validation partie emporte les champs : aucun envoi de
  champ ne la suit (plus de 409 inutile). La barre de « Valider » est une bande
  pleine : aucun champ dessous. Inventaire clos : le récapitulatif dit
  « consulter les bouteilles ».

- 0196 — Dépôt et Vérifier (tour 7, lot 37). Au dépôt, « − champ + » restent
  ensemble sous leur libellé ; « Bouteille suivante » dit sa raison sous le
  bouton quand il est grisé, et ne passe pas tant qu'une quantité est
  refusée. Sur Vérifier, une coupure pendant l'envoi d'une quantité se dit
  dans sa carte seulement, et un bandeau de coupure disparaît dès qu'une
  réponse arrive. Au toucher, le ✕ fait 40 px. Une quantité effacée : « Quantité
  vide ».

- 0197 — Finitions (tour 7, lot 38). Les messages écrits par les scripts
  mettent des espaces insécables dans « » (une seule fonction par script) ;
  la barre « Annuler / Vérifier / Enregistrer » est fixe en bas, comme sur
  les autres écrans ; Séparer une bouteille unique dit « rien à séparer ».
  Écarté : T7-S2 (curseur sur « Ajouter ses photos » de la nouvelle carte : le
  choix de fichier est un champ masqué derrière son libellé, déjà mis en vue).

- 0198 — Barres fixes et champs (tour 8, lot 39). Une barre fixe en bas
  (« Valider », configuration) ne cache jamais le champ actif : marge de
  défilement sur la saisie elle-même, et la barre de configuration fait
  remonter le champ tapé quand elle apparaît. Le ▶ des volets au toucher ne
  met plus de puces sur les liens. Les h2 restent sous le h1. L'avertissement
  « dépôt ouvert dans un autre onglet » disparaît quand l'autre onglet se
  ferme. Un renommage refusé garde le volet « Gérer l'inventaire » ouvert.

- 0199 — Messages et configuration (tour 8, lot 40). Un nom trop long renvoie
  au suivi avec la raison ; une bouteille introuvable est dite avec le nom de
  la vente ; le dépôt ou Vérifier d'un inventaire clos renvoie au suivi sans
  second message (le bandeau « clos » suffit) ; l'avertissement de clôture est
  encadré. Écarté : T8-S2 (donner seul la source « Lue par le modèle » à une
  colonne nommée comme un champ toujours lu) — l'outil changerait en silence une
  source que l'expert a choisie ; le refus dit déjà quoi choisir (0187).

- 0200 — Confirmations et compteurs (tour 9, lot 41). La clôture dit les
  bouteilles non validées une seule fois, dans un encadré hors de la liste,
  avec leurs numéros ; un conflit à la validation met sa phrase d'abord et ses
  boutons dessous ; les compteurs disent « en cours d'analyse » ; un champ mis
  en vue ne passe jamais sous une barre fixe (marge de défilement générale).

---

## Questions ouvertes (trancher avec l'expert)

- Fichier Excel réel de la maison pilote (en-têtes exacts, valeurs utilisées)
  → première config.
- Valeurs exactes de l'état de l'étiquette dans la nomenclature de la maison.
- Source de données pour l'estimation future.
- La maison accepte-t-elle que les photos de ses lots transitent par un palier
  gratuit dont le fournisseur peut exploiter les données (0050) ? Si non :
  backend payant, ou modèle local.
- (Tranchée le 2026-10-11 : une bouteille en erreur saisie à la main se valide
  en « saisie manuelle », 0169.)
