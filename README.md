# cave-scan

À partir des photos d'une bouteille (étiquette, contre-étiquette, capsule…), un
modèle vision-langage extrait les champs de catalogage. L'expert relit et
corrige, puis on exporte un Excel au format de la maison de ventes. On peut
aussi comparer ce listing automatique au listing de l'expert, champ par champ :
c'est le **tableau de scores par champ**.

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

Une bouteille = ses photos. Chaque photo posée à la racine du dossier est une
bouteille d'une seule photo ; une bouteille photographiée plusieurs fois
(étiquette, contre-étiquette, capsule…) a son propre sous-dossier, ses photos
dans l'ordre de leur nom. Les photos HEIC d'iPhone sont lues.

```
python run_v0.py --photos data/photos --limite 3            (essai sur 3 bouteilles)
python run_v0.py --photos data/photos --nom "Cave Dupont" --manual listing_expert.xlsx
```

Dans l'ordre, `run_v0.py` :

1. crée l'inventaire : la config de la maison est figée et les photos sont
   copiées dans le stockage de l'outil ;
2. refuse un dossier invalide (photo en double, format non lu, plus de photos
   pour une bouteille que la maison n'en accepte — 4 par défaut) AVANT tout
   appel, puis affiche chaque bouteille avec ses photos ;
3. extrait chaque bouteille — toutes ses photos en un seul appel — en
   enregistrant la réponse du modèle dès son retour ;
4. exporte l'Excel (`out/listing_auto.xlsx` par défaut, ou `--sortie`) : une
   ligne par bouteille, y compris une bouteille en erreur d'analyse (fond rouge
   pâle, « Erreur d'analyse » dans « À vérifier ») ;
5. avec `--manual`, affiche le **score du modèle** face à l'expert ; sans, les
   signaux du modèle.

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
- Valider bouteille par bouteille est facultatif : l'Excel se télécharge sans.
  Une bouteille corrigée après validation repasse à relire. Un inventaire est
  `valide` quand toutes ses bouteilles le sont, validées une par une : il n'y a
  pas de validation en masse. Une bouteille dont les photos sont signalées ne
  peut pas être validée. Une bouteille en erreur d'analyse se valide « en
  saisie manuelle » une fois ses champs obligatoires saisis (domaine,
  appellation, millésime, format).
- `exporter` est refusé tant qu'une bouteille n'est pas encore analysée :
  chaque bouteille doit avoir sa ligne dans l'Excel.
- `stats` donne les tokens consommés par bouteille : c'est la base du coût réel.

## API et extraction en arrière-plan

Deux processus : le serveur API et le worker qui extrait. Pour développer, une
commande lance les deux à la fois.

```
python serveur.py                    (écrans + API sur http://127.0.0.1:8000, local par défaut)
python worker.py                     (Gemini, 4 extractions simultanées)
python dev.py                        (les deux à la fois)
python dev.py --backend factice      (sans réseau ni quota : réponses fausses, pour développer)
```

Si le port 8000 est pris, l'application démarre sur le premier port libre qui
suit et l'annonce. Avec `--port N`, c'est ce port-là ou un message clair : rien
ne démarre.

La documentation interactive est sur http://127.0.0.1:8000/docs. On peut y :
- créer un inventaire en envoyant ses photos (`POST /inventaires`), ou en
  brouillon, bouteille par bouteille ;
- lancer l'extraction, suivre la progression, annuler, relancer les erreurs ;
- lister et consulter les bouteilles, les corriger, les valider une par une ;
- revenir à la valeur du modèle, réanalyser une bouteille, signaler un problème
  de photos, séparer des exemplaires d'état différent, retirer une bouteille
  (et la remettre) ;
- renommer, archiver, mettre à la corbeille (et restaurer), clore et rouvrir un
  inventaire ;
- lire le récapitulatif de la relecture et télécharger l'Excel (refusé, avec la
  raison, tant qu'une bouteille n'a pas sa ligne).

Les actions de l'expert demandent l'en-tête `X-Auteur`. La fiche d'une bouteille
porte une `version` : la renvoyer avec une correction ou une validation fait
refuser (409) l'enregistrement si la bouteille a été modifiée ailleurs entre-temps.
`POST /inventaires/{id}/valider` ne valide aucune bouteille : il constate que
toutes l'ont été.

- **Rien n'est perdu.** Le travail en attente vit dans la base. Si le worker est
  arrêté (Ctrl-C), il termine les extractions commencées. S'il est tué, un
  worker relancé reprend les bouteilles abandonnées au bout de 2 minutes, sans
  jamais extraire deux fois la même.
- **Le débit est réglé pour tous les workers à la fois.** Les appels sont
  espacés (`--espacement`, 4,5 s par défaut pour le palier gratuit Gemini). Sur
  une limite atteinte, tout le monde ralentit au lieu de multiplier les
  tentatives.
- **Le quota gratuit Gemini (20 requêtes par jour) ne suffit pas pour un
  inventaire réel.** Il faut une clé payante (Gemini ou `--backend anthropic`).
- `run_v0.py` et `inventaire.py` continuent de fonctionner, sur les mêmes
  fonctions et la même base.

## Écrans : déposer les photos depuis un téléphone

L'application web (pages dans la même application que l'API) :

```
python dev.py --backend factice                     sur l'ordinateur : http://127.0.0.1:8000/
python dev.py --backend factice --reseau-local      depuis un téléphone sur le même Wi-Fi
```

Avec `--reseau-local`, le démarrage affiche un avertissement et l'adresse à
ouvrir sur le téléphone, par exemple `http://192.168.1.189:8000/`. Sans
connexion (prévue en session 7), **tout appareil du réseau y a accès** : à
utiliser chez vous, jamais sur le réseau d'un client. Windows peut demander
d'autoriser Python dans le pare-feu (« Réseaux privés »).

Le parcours de l'expert :

1. **Nouvel inventaire** : le nom de la vente.
2. **Photographier les bouteilles**, une à une, chacune avec toutes ses photos
   (étiquette, contre-étiquette, capsule, bouteille entière… 4 au plus par
   défaut, réglable dans la configuration).
   - **Appareil photo** : prenez les photos de la bouteille à la suite (le
     compteur les affiche), indiquez la quantité s'il y a plusieurs bouteilles
     identiques, puis « Bouteille suivante ».
   - **Galerie ou ordinateur** : « Bouteille 1 » → ajoutez ses photos ;
     « Ajouter une bouteille » → les siennes, etc.
   - Les photos partent une par une. Une coupure de réseau n'en perd aucune :
     l'envoi reprend tout seul, et une photo déjà reçue n'est pas renvoyée.
   - Un fichier refusé est affiché avec sa raison. Les photos HEIC d'iPhone
     sont acceptées.
   - « Plus tard » : on s'arrête et on reprend quand on veut.
3. **Vérifier et lancer** : chaque bouteille est une carte, ses photos dans
   l'ordre. Une photo d'une autre bouteille ? « Nouvelle bouteille à partir
   d'ici ». Une bouteille coupée en deux ? « Rattacher à la précédente ». Puis
   **Lancer l'analyse** : les photos d'une bouteille lancée ne bougent plus.
4. **Suivi** : la progression se met à jour seule. On peut mettre l'analyse en
   pause et la reprendre, relancer les erreurs, **relire** dès la première
   bouteille analysée (voir ci-dessous), et télécharger l'Excel dès que chaque
   bouteille a sa ligne.
5. **Gérer l'inventaire** (depuis le suivi) : ajouter des bouteilles après le
   lancement, renommer, archiver, mettre à la corbeille (rien n'est effacé, il
   se restaure depuis l'accueil), **clore** quand tout est bon (lecture seule ;
   l'écran dit d'abord ce qui n'a pas été validé), rouvrir si besoin. Chaque
   geste est tracé.

**La réduction des photos avant l'envoi est désactivée par défaut**, tant que
son effet sur la lecture n'est pas mesuré. Avec des crédits API et de **vraies
photos originales du téléphone**, pas passées par WhatsApp (qui les réduit et
efface leur date) :

```
python mesurer_reduction.py --photos dossier_photos_originales --tailles 1600,2000,2500,3000
```

Il fait (1 + nombre de tailles) appels par photo. Notez le tableau et la taille
retenue dans `decisions.md`, puis activez la réduction dans `src/web/pages.py`
(`REDUCTION_PAR_DEFAUT`, `TAILLE_REDUCTION`).

## Écran de relecture (ordinateur, clavier)

Depuis le suivi, « Relire les bouteilles » ouvre la première bouteille non
validée. La relecture peut commencer pendant que l'analyse continue : les
bouteilles pas encore analysées sont sautées et comptées à part.

- **À gauche, les photos** : molette, double-clic ou `Z` pour zoomer (l'original
  pleine résolution se charge dès qu'on zoome), glisser pour se déplacer, `E`
  pour passer à la photo suivante de la bouteille (`Maj` + `E` : précédente),
  « Ouvrir l'original » dans un nouvel onglet. Les photos de la bouteille
  suivante sont préchargées.
- **À droite, les champs**, dans l'ordre de la config de la maison. Chacun dit
  d'où vient sa valeur : lue, déduite, proposée (à vérifier), corrigée ou saisie
  par l'expert. Une valeur non lisible s'affiche « à remplir », jamais comme une
  valeur. Les doutes du modèle sont surlignés. Au survol d'un champ corrigé, la
  lecture du modèle ; « Revenir à la valeur du modèle » la remet.
- **Rien à enregistrer à la main.** Chaque champ est enregistré dès qu'on le
  quitte. L'indicateur en haut dit « Tout est enregistré » ou « Erreur
  d'enregistrement, nouvel essai… » ; on ne passe pas à une autre bouteille tant
  qu'une saisie n'est pas enregistrée. Une saisie refusée est expliquée à côté
  du champ et bloque la validation.
- **Deux onglets sur la même bouteille** : enregistrer par-dessus une
  modification faite ailleurs est d'abord signalé (« Enregistrer quand même »
  ou recharger). L'historique garde toutes les corrections.

| Touche                           | Action                                                   |
|----------------------------------|----------------------------------------------------------|
| `Entrée` (hors champ texte)      | valider et passer à la suivante                          |
| `Ctrl` + `Entrée` (partout)      | valider et passer à la suivante                          |
| `←` `→` ou `J` `K`               | bouteille précédente / suivante                          |
| `Tab`                            | champ suivant (`Maj` + `Tab` : précédent)                |
| `Entrée` dans un champ texte     | enregistrer le champ                                     |
| `Échap`                          | quitter le champ (il est enregistré)                     |
| `Z` / `E`                        | zoom / autre photo                                       |
| `?`                              | aide des raccourcis                                      |

Les raccourcis à une lettre et les flèches ne fonctionnent pas pendant la saisie
dans un champ : `Échap` pour en sortir.

**Les cas particuliers** (« Autres actions », sous les champs) :
- **Réanalyser** : la bouteille repasse par le modèle (le worker doit tourner).
  L'ancienne lecture est gardée ; vos corrections restent prioritaires.
- **Signaler un problème de photos** : une photo ne montre pas cette bouteille.
  Elle ne peut plus être validée tant que le signalement n'est pas levé.
- **Retirer cette bouteille** : photographiée par erreur, pas dans la vente…
  Elle sort de la relecture et de l'Excel ; rien n'est effacé, elle se remet
  depuis le récapitulatif.
- **Séparer** : 5 bonnes et 1 abîmée ? Indiquez d'abord la quantité totale (6),
  puis séparez 1 exemplaire. Une seconde bouteille apparaît juste après, avec
  les mêmes photos et les mêmes valeurs ; ajustez son état et sa description.
  Si les deux restent identiques sur les colonnes de regroupement de la maison,
  l'écran prévient qu'elles seront fusionnées en une ligne à l'export.
- **Bouteille en erreur d'analyse** : la raison est affichée en clair, avec
  « Réanalyser ». On peut aussi saisir ses champs à la main : avec au moins
  domaine, appellation, millésime et format, elle se valide « en saisie
  manuelle ». Dans l'Excel, elle a toujours sa ligne : « Erreur d'analyse »,
  ou « Saisie manuelle » une fois validée.

Le **récapitulatif** (lien en haut, et à la fin) donne ce qui reste à relire,
les bouteilles en erreur ou signalées, et les chiffres : corrections par champ,
temps de relecture par bouteille (compté même sans valider, absences de plus
d'une minute exclues),
bouteilles réanalysées, séparées, signalées. Les mêmes chiffres sont dans
`python inventaire.py stats 1`.

Les corrections faites à l'écran sont signées « Expert », ou du nom indiqué par
`CAVE_SCAN_AUTEUR` dans `.env`, en attendant la connexion.

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
  pour les inventaires suivants : pensez à incrémenter son champ `version` (la
  page « Configuration » le fait pour vous).

## Configuration

Chaque maison de vente a sa propre installation de l'application, avec sa
configuration : les pages ne parlent jamais de « maison ». La configuration est
le fichier de `config/maisons/` (s'il y en a plusieurs, `CAVE_SCAN_MAISON` dans
`.env` désigne le bon).

Depuis l'accueil, **Configuration** : les colonnes de votre Excel. Sans
configuration, « Créer la configuration » part des colonnes de base, sans aucun
fichier : on ajoute ensuite les siennes à la main.
On ajoute, modifie, réordonne ou retire une colonne (nom, type, source, valeurs
et leur description, règle), on voit pour chacune ce qui est envoyé au modèle,
on importe ou exporte le JSON. Chaque enregistrement est vérifié comme un
fichier et devient une nouvelle version ; un inventaire garde la version de sa
création. Colonnes système facultatives : `a_verifier` (doutes du modèle, et
« Erreur d'analyse ») et `relue` (« oui » si l'expert a validé la bouteille).

## Anciennes options

| Avant                   | Maintenant                                                          |
|-------------------------|---------------------------------------------------------------------|
| `--journal FICHIER`     | supprimé : chaque extraction est en base                            |
| `--reprendre`           | `--inventaire ID`                                                   |
| `--auto JOURNAL.jsonl`  | `--inventaire ID` : réexport et score sans rappeler le modèle       |
| `--sans-contre`         | inutile : une photo à la racine = une bouteille ; plusieurs photos = un sous-dossier |

Ces options sont encore acceptées, mais seulement pour afficher leur remplaçante.

## Tests

```
python -m pytest
```

Les tests tournent hors ligne, sur une base temporaire. Aucune clé n'est lue :
aucun test ne peut appeler un vrai modèle.

Les tests de navigation pilotent un vrai Chromium :
- `tests/test_navigateur.py`, au format téléphone, du dépôt des photos à l'Excel ;
- `tests/test_navigateur_relecture.py`, sur un écran d'ordinateur : 10 bouteilles
  relues uniquement au clavier, le temps compté sans validation, deux onglets
  sur la même bouteille, une coupure de réseau, et le passage d'une bouteille à
  la suivante sur 300 bouteilles.

Ils demandent une installation préalable : `python -m playwright install
chromium`. Sans Chromium, ils sont ignorés.

## Organisation du code

| Chemin                         | Rôle                                                                |
|--------------------------------|---------------------------------------------------------------------|
| `run_v0.py`, `inventaire.py`   | lignes de commande : elles appellent les services et affichent      |
| `serveur.py`, `worker.py`, `dev.py` | API JSON (local), worker d'extraction, les deux pour développer |
| `src/api/`                     | API FastAPI : routes fines, format d'erreur unique                  |
| `src/web/`                     | écrans : pages Jinja2 + HTMX (dépôt, suivi, relecture, configuration), scripts d'envoi des photos, de relecture et de configuration, style |
| `mesurer_reduction.py`, `src/mesure/` | mesure de l'effet de la réduction des photos sur l'extraction |
| `src/worker.py`                | boucle du worker : réserver, extraire en parallèle, signes de vie   |
| `src/services/`                | inventaires, cycle de vie, dépôt (brouillons), extraction, file d'attente, pilotage, débit, relecture, cas particuliers, consultation, envoi des photos, configuration, restitution |
| `src/donnees/`                 | modèles SQLAlchemy, ouverture et migration de la base, stockage des photos |
| `src/extract/`                 | contrat `Bouteille`, extracteurs Gemini, Anthropic et fixtures      |
| `src/config/`                  | config par maison, lecture de `.env`                                |
| `src/export/`, `src/compare/`  | Excel au format maison, comparaison au listing de l'expert          |
| `src/io/`, `src/normalize/`    | photos (HEIC compris) et listing manuel, normalisation (identité pour l'instant) |
| `migrations/`                  | migrations Alembic                                                  |
