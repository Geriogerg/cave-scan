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

- 0011 — Format de sortie piloté par config YAML par maison (fond/forme séparés) —
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

## Mise en œuvre (squelette v0)

- 0016 — Troisième convention d'abstention : `None` pour les champs numériques
  (`contenance_cl`, `degre`), à côté de `non_lisible` (texte) et
  `non_determinable` (enums) — garder 75 et 13.5 typés en nombres pour qu'Excel
  puisse trier et qu'on puisse calculer dessus ; `est_abstention()` centralise
  les trois conventions en un seul endroit — écarté : mettre « non_lisible »
  partout (aurait transformé toutes les colonnes numériques en texte).

- 0017 — Enum `Couleur` = rouge | blanc | rose | non_determinable — les trois
  couleurs incontestables d'un catalogue ; « effervescent » est un type, pas une
  couleur (un champagne est blanc ou rosé) — écarté : ajouter orange/effervescent
  sans avoir vu de vrai catalogue. **À confirmer avec l'expert** (voir questions
  ouvertes).

- 0018 — Modèle par défaut `claude-opus-5`, surchargeable par `CAVE_SCAN_MODEL` —
  le plancher doit être mesuré avec un modèle générique de haut de gamme, sinon
  on mesure la contrainte de coût, pas la capacité — écarté : figer le modèle.

- 0019 — Thinking adaptatif + `tool_choice` forcé sur l'appel VLM — lire une
  étiquette abîmée et savoir renoncer demande de la réflexion, et c'est
  exactement la compétence mesurée ; thinking désactivé fait écrire au modèle
  ses appels d'outil en texte visible — écarté : thinking désactivé.
  ⚠ **Combinaison non vérifiée contre l'API réelle** (aucune clé dans
  l'environnement de développement) : à valider au premier vrai run.

- 0020 — Pas de `strict: true` sur l'outil ; `from_tool_input()` tolérant à la
  place — le schéma utilise des types nullables (`["integer", "null"]`) dont la
  compatibilité avec le mode strict n'a pas pu être testée, et une réponse de
  travers doit produire une abstention plutôt qu'une exception — écarté :
  strict non testé, à reconsidérer dès qu'une clé permet de le vérifier.

- 0021 — Longueurs différentes entre photos et listing manuel = `ValueError`,
  pas une comparaison tronquée — comparer des bouteilles décalées produit un
  score faux ET crédible, le pire des résultats — écarté : comparer sur le
  minimum des deux longueurs.

- 0022 — Le pliage de comparaison s'arrête à casse + accents + espaces — retirer
  la ponctuation ou le préfixe « Domaine » serait normaliser, or la v0 doit
  laisser ces écarts VISIBLES pour qu'on écrive plus tard les bonnes règles
  (0007, 0008). Conséquence assumée : `13.0` vs `13` sortira en désaccord — c'est
  une information sur les conventions, pas un bug.

- 0023 — `FixtureExtractor` vit dans `src/`, pas dans `tests/` — `run_v0
  --dry-run` est un chemin de production ; le faire dépendre du code de test
  aurait inversé la dépendance — écarté : extracteur factice côté tests.

- 0024 — Champs comparés = 11 (hors `couleur_source`, `champs_a_verifier`,
  `notes`) — ce sont des métadonnées produites par le modèle, l'expert n'en
  produit pas d'équivalent : les comparer n'aurait aucun sens.

- 0025 — Colonne de config à `champ: null` = colonne vide — un seul mécanisme
  générique couvre le lot ET l'estimation, plutôt qu'un cas particulier codé en
  dur pour l'estimation (0005) — écarté : traiter l'estimation à part.

- 0026 — Une colonne de config qui référence un champ inexistant lève une erreur
  au chargement — une faute de frappe doit s'arrêter là, pas livrer une colonne
  silencieusement vide à une maison de vente.

- 0027 — Regroupement des photos : un sous-dossier par bouteille, « contre » dans
  le nom de fichier = contre-étiquette, dossier plat = une image par bouteille —
  convention v0 isolée dans `src/io/photos.py`, **à confirmer avec l'expert** ;
  si la vraie arborescence diffère, un seul fichier change.

- 0028 — Le paquet `src/io` porte le nom d'un module stdlib : ne jamais ajouter
  `src/` au `sys.path` (seulement la racine) — sinon `src/io` masque le module
  `io` de la stdlib et casse openpyxl. Verrouillé par `tests/conftest.py`.

- 0029 — `sys.stdout` forcé en UTF-8 dans `run_v0` — la console Windows est en
  cp1252 et mutilait les accents du rapport, qui est le livrable.

- 0030 — `requirements.txt` recentré sur la v0 (anthropic, openpyxl, pyyaml,
  pytest) — `requests`, `beautifulsoup4` et `rapidfuzz` servaient au scraping et
  au matching LWIN d'un périmètre antérieur, hors v0.

---

## Questions ouvertes (trancher avec l'expert)

- Une ligne par bouteille ou par lot ?
- Format réel du listing manuel (fichier, en-têtes exacts) → verrouille la config
  et load_manual().
- Photos ordonnées comme le listing ? Vues de bouteille entière dispo (format) ?
- L'échelle de couleur (rouge/blanc/rosé) suffit-elle, ou le catalogue distingue
  aussi orange, vin doux, effervescent ? → verrouille l'enum `Couleur` (0017).
- Arborescence réelle des photos : un sous-dossier par bouteille ? → confirme ou
  corrige `src/io/photos.py` (0027).
