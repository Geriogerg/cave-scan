# cave-scan

À partir des photos d'une bouteille (étiquette + contre-étiquette), un modèle
vision-langage extrait les champs de catalogage. On exporte ensuite un Excel au
format de la maison de ventes, puis on compare ce listing automatique au listing
de l'expert, champ par champ. Le livrable est ce **tableau de scores par champ**.

Inventaires, extractions et corrections sont conservés dans une base de données.
Les règles du projet sont dans `CLAUDE.md`, les décisions techniques dans
`decisions.md`, le périmètre de chaque session dans `docs/sessions/`.

## Installation

```
pip install -r requirements.txt
copy .env.example .env        (puis renseigner GEMINI_API_KEY)
```

## Essai hors ligne

```
python run_v0.py --dry-run
```

Le dry-run rejoue des réponses enregistrées sur des photos générées, dans une base
temporaire. Il ne demande ni clé ni réseau, et n'écrit rien dans votre base. Le
rapport doit afficher « Comparaison auto vs manuel — 6 bouteille(s) ».

Pour essayer aussi la relecture sans clé, on garde l'inventaire de démonstration :

```
python run_v0.py --dry-run --base out/demo.db
python inventaire.py bouteilles 1 --base out/demo.db
```

## Un inventaire réel

Les photos sont posées à plat dans un dossier, dans l'ordre de prise de vue :
étiquette, contre-étiquette, bouteille après bouteille.

```
python run_v0.py --photos data/photos --limite 3            (essai sur 3 bouteilles)
python run_v0.py --photos data/photos --nom "Cave Dupont" --manual listing_expert.xlsx
```

Dans l'ordre, `run_v0.py` :

1. crée l'inventaire : la config de la maison est figée et les photos sont
   copiées dans le stockage de l'outil ;
2. refuse un dossier invalide (nombre impair, photo en double, HEIC) AVANT tout
   appel, puis affiche l'appariement ;
3. extrait chaque bouteille, en enregistrant la réponse du modèle dès son retour ;
4. exporte l'Excel (`out/listing_auto.xlsx` par défaut, ou `--sortie`) ;
5. avec `--manual`, affiche le **score du modèle** face à l'expert ; sans, les
   signaux du modèle.

Vous n'avez que des étiquettes, sans contre-étiquette ? Ajoutez `--sans-contre` :
chaque photo devient une bouteille.

```
python run_v0.py --photos data/etiquettes --sans-contre
```

Autres options : `--backend gemini|anthropic`, `--maison config/maisons/x.json`
et `--base`.

## Reprendre, réexporter, rescorer

```
python run_v0.py --inventaire 1 [--manual listing_expert.xlsx]
```

La commande termine l'extraction là où elle s'est arrêtée, sans refaire une
bouteille déjà extraite, et retente celles en erreur. Puis elle réexporte et
rescore. Si tout est déjà extrait, le modèle n'est pas appelé.

| Incident                                              | Ce qui se passe                                                        |
|-------------------------------------------------------|------------------------------------------------------------------------|
| Clé invalide, modèle inconnu, requête refusée         | Enregistré, puis l'inventaire s'arrête et affiche la commande de reprise |
| Limite de débit, délai, serveur surchargé             | Quelques nouvelles tentatives, puis la bouteille passe en erreur ; les autres continuent |
| Réponse inexploitable                                 | Réponse gardée en base, la bouteille seule passe en erreur              |
| Ctrl-C, clé absente, Excel ouvert                     | Rien de perdu : la commande de reprise s'affiche                        |

## Relire et corriger

```
python inventaire.py lister
python inventaire.py bouteilles 1
python inventaire.py fiche 1 3                    (bouteille n°3, ou son identifiant B-…)
python inventaire.py corriger 1 3 millesime 2016 --auteur "Prénom Nom"
python inventaire.py corriger 1 3 quantite 2 --auteur "Prénom Nom"
python inventaire.py corriger 1 3 estimation "800-1000" --auteur "Prénom Nom"
python inventaire.py valider 1 3 --auteur "Prénom Nom"
python inventaire.py stats 1
python inventaire.py exporter 1 --sortie out/cave_dupont.xlsx
```

- **Une correction ne modifie jamais la sortie du modèle.** Elle s'ajoute à
  l'historique, avec le champ, l'ancienne et la nouvelle valeur, l'auteur et la
  date. L'export montre la valeur courante ; `fiche` montre les deux, et
  l'extraction d'origine.
- La saisie est validée selon le type de la colonne : quantité = entier ≥ 1,
  liste = code ou libellé connu, nombre, ou texte libre.
- L'estimation se saisit ici, par l'expert. Le modèle ne la remplit jamais.
- Le score de `run_v0.py --manual` mesure **le modèle seul**, sans les
  corrections. Les corrections se comptent dans `stats`.
- Une bouteille corrigée après validation repasse à relire. Un inventaire est
  `valide` quand toutes ses bouteilles le sont ; une bouteille en erreur ne peut
  pas être validée.
- `stats` donne les tokens consommés par bouteille : c'est la base du coût réel.

## Où sont les données

- **Base** : `data/cave_scan.db` (SQLite). Se change avec `CAVE_SCAN_DB` (chemin,
  ou URL PostgreSQL) ou l'option `--base`.
- **Photos** : `data/stockage/`, nommées par leur empreinte. Se change avec
  `CAVE_SCAN_STOCKAGE`.
- `data/` et `out/` ne sont jamais versionnés.
- Le schéma évolue par migrations Alembic (`migrations/`), appliquées
  automatiquement à l'ouverture de la base.
- **Config d'une maison** : `config/maisons/*.json`. Un inventaire garde la
  config du jour de sa création. Un fichier modifié devient une nouvelle version
  pour les inventaires suivants : pensez à incrémenter son champ `version`.

## Anciennes options

| Avant (session 1)       | Maintenant                                                          |
|-------------------------|---------------------------------------------------------------------|
| `--journal FICHIER`     | supprimé : chaque extraction est en base                            |
| `--reprendre`           | `--inventaire ID`                                                   |
| `--auto JOURNAL.jsonl`  | `--inventaire ID` : réexport et score sans rappeler le modèle       |

Ces options sont encore acceptées, mais seulement pour afficher leur remplaçante.

## Tests

```
python -m pytest
```

Les tests tournent hors ligne, sur une base temporaire. Aucune clé n'est lue :
aucun test ne peut appeler un vrai modèle.

## Organisation du code

| Chemin                         | Rôle                                                                |
|--------------------------------|---------------------------------------------------------------------|
| `run_v0.py`, `inventaire.py`   | lignes de commande : elles appellent les services et affichent      |
| `src/services/`                | inventaires, extraction, relecture, restitution (export, stats, score) |
| `src/donnees/`                 | modèles SQLAlchemy, ouverture et migration de la base, stockage des photos |
| `src/extract/`                 | contrat `Bouteille`, extracteurs Gemini, Anthropic et fixtures      |
| `src/config/`                  | config par maison, lecture de `.env`                                |
| `src/export/`, `src/compare/`  | Excel au format maison, comparaison au listing de l'expert          |
| `src/io/`, `src/normalize/`    | photos et listing manuel, normalisation (identité pour l'instant)   |
| `migrations/`                  | migrations Alembic                                                  |
