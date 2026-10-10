---
paths:
  - "src/donnees/**"
  - "src/services/**"
  - "migrations/**"
  - "alembic.ini"
  - "inventaire.py"
  - "run_v0.py"
---

# Règles : base de données et services

- Valeur affichée = sortie du modèle, remplacée par la dernière correction.
  Corrections conservées en historique (champ, ancienne, nouvelle, auteur, date).
- Chaque extraction trace modèle, version du prompt, tokens, durée, erreur. La
  réponse brute est enregistrée avant d'être interprétée.
- Images sur disque, nommées par leur hash ; la base ne stocke que chemins et
  empreintes. Une photo identique n'est enregistrée qu'une fois.
- Migrations versionnées uniquement ; jamais de suppression-recréation.
- Une correction sur une bouteille validée la remet à relire ; un inventaire avec
  une bouteille en erreur ne peut pas être validé.
- Saisies de l'expert validées selon le type : quantité entier ≥ 1, liste = code
  connu, texte libre.
- Un inventaire reste lié à la version de config avec laquelle il a été créé
  (config figée à la création, jamais relue depuis `config/maisons/`).
