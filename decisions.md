# Journal de décisions — v0

D�cisions techniques qui cadrent la v0. Une ligne chacune :
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

---

## Questions ouvertes (trancher avec l'expert)

- Une ligne par bouteille ou par lot ?
- Format réel du listing manuel (fichier, en-têtes exacts) → verrouille la config
  et load_manual().
- Photos ordonnées comme le listing ? Vues de bouteille entière dispo (format) ?
