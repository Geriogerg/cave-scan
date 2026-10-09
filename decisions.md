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

- 0036 — [remplacée par 0052] Une colonne de config qui référence un champ inexistant lève une erreur
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

- 0040 — [remplacée par 0060] `requirements.txt` recentré sur la v0 (anthropic, openpyxl, pyyaml,
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

- 0045 — [remplacée par 0079] Politique d'erreur API en deux classes : panne PASSAGÈRE (429, 5xx,
  réseau) → abstention tracée dans `notes`, la campagne continue ; panne
  SYSTÉMATIQUE (401, 403, 404, 400) → remonte et arrête tout — répéter une clé
  invalide 200 fois ne produirait que 200 lignes vides en facturant chaque
  échec. La politique vit dans `vision_extract` pour que `run_v0` reste sans
  dépendance au SDK — écarté : tout avaler (aurait masqué le risque 0029).

- 0046 — [remplacée par 0079] Journal `.jsonl` écrit au fil de l'eau + `--reprendre` — une campagne de
  200 bouteilles interrompue à la 180e perdait 180 appels API déjà payés ; le
  journal est aussi la trace brute des réponses, indépendante de l'Excel —
  écarté : n'écrire qu'à la fin.

- 0047 — [remplacée par 0055] Option de config `abstention_vide` par colonne, activée sur les colonnes
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

- 0060 — [remplacée par 0070] Dépendances : pyyaml retiré avec l'ancienne config YAML. Restent
  google-genai, anthropic, openpyxl, python-dotenv, pytest.

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

- 0067 — [remplacée par 0082] Quantité « modifiable par l'expert » : stockée par bouteille (jamais
  recalculée), 1 par défaut. En attendant une interface, elle se modifie dans le
  journal puis `--auto` refait l'export ; le regroupement additionne.

- 0068 — Appariement des photos par ordre (0023), sans jamais deviner : tri
  par date de prise de vue EXIF si TOUTES les photos en ont une, sinon toutes
  par nom de fichier en tri naturel (« photo 2 » avant « photo 10 ») — jamais
  de tri mixte, qui intercalerait les photos au hasard ; paires consécutives
  étiquette / contre-étiquette. ARRÊT avec message explicite sur : nombre
  impair, photo dans un format non lu (HEIC d'iPhone, TIFF, RAW…, avec le
  réglage iPhone à changer), photos rangées dans un sous-dossier (ancienne
  convention, elles ne seraient jamais lues). Fichiers non-photo ignorés.
  L'appariement est affiché AVANT l'extraction, et vérifié avant même de créer
  le client du modèle : un dossier invalide se signale sans clé ni coût —
  écarté : écarter la photo orpheline et continuer (décalage silencieux).

- 0069 — Paire incohérente : question technique `photos_meme_bouteille`
  (oui | non | non_determinable) posée au modèle — pas un champ de `Bouteille`.
  « non » -> `paire_photos` dans `champs_a_verifier` (doute précis : la ligne
  est surlignée) et une note. La consigne finale ne présuppose plus que les
  photos montrent la même bouteille : l'affirmer aurait dissuadé le modèle de
  signaler une erreur d'appariement.

- 0070 — Dépendances : Pillow ajouté (dates EXIF). pillow-heif NON ajouté —
  Pillow seul ne lit pas le HEIC, qui est refusé avec un message clair et la
  marche à suivre ; pillow-heif s'installe sans difficulté ici (vérifié, non
  installé) mais il faudrait en plus convertir en JPEG avant l'envoi (Anthropic
  n'accepte pas le HEIC) : à décider selon le téléphone de l'expert. Restent :
  google-genai, anthropic, openpyxl, pillow, python-dotenv, pytest.

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

- 0083 — Statut d'inventaire : `ouvert` | `valide` ; il passe à `valide` quand
  toutes ses bouteilles le sont. Seule une bouteille extraite peut être
  validée : une bouteille en erreur ne le peut pas, donc un inventaire qui en
  contient une ne peut pas passer à `valide`. Une correction (ou une relance
  forcée) sur une bouteille validée la remet à relire (statut `extraite`) et
  l'inventaire repasse à `ouvert`. La validation et la remise à relire sont
  tracées dans l'historique des corrections (champ « statut », auteur, date),
  sans colonne supplémentaire au schéma validé.

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

---

## Questions ouvertes (trancher avec l'expert)

- Fichier Excel réel de la maison pilote (en-têtes exacts, valeurs utilisées)
  → première config.
- Valeurs exactes de l'état de l'étiquette dans la nomenclature de la maison.
- Source de données pour l'estimation future.
- La maison accepte-t-elle que les photos de ses lots transitent par un palier
  gratuit dont le fournisseur peut exploiter les données (0050) ? Si non :
  backend payant, ou modèle local.
- Le téléphone de l'expert est-il un iPhone réglé en HEIC ? Si oui : réglage
  « Le plus compatible », ou ajout de pillow-heif + conversion JPEG (0070).
