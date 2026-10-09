# Session 2 — Bibliothèque + base de données

Objectif : transformer le pipeline en bibliothèque qui **conserve son travail**.
Aujourd'hui, un lancement produit un Excel puis tout disparaît. Après cette
session, chaque inventaire, bouteille, extraction et correction est stocké, et
l'export se fait depuis la base. C'est le socle de l'application web : les
sessions suivantes (tâches de fond, écrans) ne feront qu'appeler ces fonctions.

**Pas d'interface web dans cette session.** La ligne de commande reste le seul
point d'entrée, et elle doit continuer à marcher.

---

## Avant de commencer (toi)

1. Session 1 terminée : tests verts, `--dry-run` OK, commit fait.
2. `git commit` de sauvegarde si des fichiers traînent.
3. Poser ce fichier dans `docs/sessions/SESSION_2_donnees.md`.

---

## Le principe à ne jamais casser

**On ne perd jamais la sortie du modèle.** La valeur extraite est stockée telle
quelle et n'est jamais modifiée. Une correction de l'expert est un enregistrement
à part (champ, ancienne valeur, nouvelle valeur, auteur, date). La valeur
affichée = valeur du modèle, remplacée par la dernière correction s'il y en a une.

Pourquoi : pendant le pilote, c'est ce qui permet de mesurer la qualité réelle
(quels champs l'expert corrige, combien de fois). C'est aussi la donnée qui
améliorera l'outil plus tard.

---

## Modèle de données attendu

- **Maison** : nom.
- **ConfigVersion** : maison, numéro de version, contenu JSON complet (copie),
  empreinte (hash). Un inventaire est lié à UNE version : modifier le fichier
  JSON plus tard ne change pas l'export d'un inventaire déjà créé.
- **Inventaire** : maison, config_version, nom, date de création, statut.
- **Photo** : inventaire, chemin du fichier sur disque, empreinte (hash), date
  de prise de vue, ordre. Les images restent sur disque, pas dans la base.
- **Bouteille** : identifiant stable, inventaire, photo étiquette, photo
  contre-étiquette, position dans l'inventaire, quantité, statut
  (a_extraire | en_cours | extraite | erreur | validee).
- **Extraction** : bouteille, sortie brute du modèle (JSON, immuable), modèle
  utilisé, version du prompt, tokens entrée/sortie, durée, date, erreur
  éventuelle. Une bouteille peut avoir plusieurs extractions (relance) ; la
  dernière réussie fait foi.
- **Correction** : bouteille, champ, ancienne valeur, nouvelle valeur, auteur,
  date.

---

## Fonctions de service attendues (la future API)

Fonctions simples, sans état caché, testables sans réseau :

- `creer_inventaire(maison, config_path, dossier_photos, nom)` : enregistre la
  config (nouvelle version si le contenu a changé), les photos, l'appariement
  en bouteilles. Mêmes garde-fous qu'en session 1 (nombre impair → refus).
- `extraire_bouteille(bouteille_id, extractor)` : idempotente. Relancée sur une
  bouteille déjà extraite, elle ne crée pas de doublon sauf si on force une
  relance. Une erreur API est enregistrée sur l'extraction et met la bouteille
  en statut erreur, sans bloquer les autres.
- `extraire_inventaire(inventaire_id, extractor)` : enchaîne les bouteilles à
  extraire (séquentiel dans cette session ; le parallèle viendra avec les
  tâches de fond).
- `corriger(bouteille_id, champ, nouvelle_valeur, auteur)` : refuse un champ
  inconnu ou une valeur hors liste pour une colonne de type liste.
- `valider(bouteille_id, auteur)`.
- `valeurs_courantes(bouteille_id)` : modèle + corrections.
- `exporter(inventaire_id, chemin)` : Excel depuis la base, avec la
  config_version de l'inventaire, regroupement et surlignage comme en session 1.
- `stats_inventaire(inventaire_id)` : nombre de bouteilles par statut, coût
  total en tokens, champs les plus corrigés.

---

## Choix techniques

- **SQLite** pour le local, via **SQLAlchemy**, de façon à passer à PostgreSQL
  au déploiement sans réécrire le code.
- **Migrations versionnées** (Alembic) dès maintenant : le schéma évoluera
  pendant le pilote, et on ne veut jamais perdre les données d'un inventaire.
- Chemin de la base et dossier de stockage des photos configurables par
  variable d'environnement.
- Photos copiées dans un dossier de stockage géré par l'outil (nommées par leur
  hash), pour que la base ne pointe jamais vers un fichier que l'utilisateur
  aurait déplacé.

---

## Message de contrôle (à coller en premier)

```
Lis CLAUDE.md, decisions.md et docs/sessions/SESSION_2_donnees.md en entier
(pas ROADMAP.md). Puis audite le code sans rien modifier et réponds-moi avec :
1. l'état après la session 1 : modules, point d'entrée, tests, et si tout est
   vert ;
2. ce qui, dans le code actuel, garde de l'état en mémoire ou écrit des
   fichiers, et devra passer par la base ;
3. ton plan pour cette session : nouveaux modules, modifications de modules
   existants, changements éventuels du contrat de Bouteille (justifiés),
   dépendances ajoutées, ordre des commits ;
4. les tests existants qui devront être adaptés, avec la raison pour chacun ;
5. les décisions que tu vas ajouter à decisions.md pour cette session, à la
   suite de la numérotation existante : sortie du modèle immuable et
   corrections séparées ; config figée par inventaire ; photos sur disque
   nommées par hash ; SQLite + SQLAlchemy + migrations Alembic ; traçage
   modèle / prompt / tokens / durée par extraction. Mets aussi à jour la
   section « Questions ouvertes » si une question est tranchée.
Puis ARRÊTE-TOI et attends ma validation.
```

---

## Prompt d'exécution (après validation du plan)

```
Plan validé, tu peux exécuter la session 2 décrite dans
docs/sessions/SESSION_2_donnees.md.

RÈGLES :
- On fait évoluer le code existant, on ne le réécrit pas. La ligne de commande
  actuelle (--dry-run compris) doit continuer de fonctionner ; elle passe
  désormais par les fonctions de service.
- La sortie brute du modèle est immuable. Une correction est toujours un
  enregistrement séparé, jamais un écrasement.
- Les colonnes de source expert et systeme ne sont toujours jamais envoyées au
  modèle. Pas d'estimation, pas de normalisation, pas de few-shot, pas
  d'interface web.
- Un commit par étape, avec diff et sortie des tests.
- Si un test existant casse, arrête-toi et explique avant de le modifier. Ne
  jamais affaiblir un test qui vérifie une contrainte dure.

CRITÈRES D'ACCEPTATION (tests hors ligne, base SQLite temporaire) :
- Non-régression : sur les fixtures, l'Excel exporté depuis la base est
  identique en contenu à celui de la session 1.
- Une correction ne modifie jamais l'extraction ; valeurs_courantes renvoie la
  dernière correction ; l'historique garde toutes les corrections.
- corriger refuse un champ inconnu et une valeur hors liste.
- extraire_bouteille relancée ne crée pas de doublon ; une erreur d'extraction
  met la bouteille en erreur sans bloquer les autres.
- Modifier le JSON de config après création d'un inventaire ne change pas
  l'export de cet inventaire ; un nouvel inventaire utilise une nouvelle
  version.
- La même photo déposée deux fois est détectée (hash).
- stats_inventaire renvoie des chiffres cohérents sur les fixtures.
- La migration initiale crée la base de zéro.

À LA FIN :
- Montre la sortie des tests et de --dry-run.
- Ajoute dans decisions.md une ligne par choix technique tranché.
- Donne-moi les vérifications à faire de mon côté.
```

---

## Ce qu'il faut surveiller

- **Écrasement de l'extraction** par une correction : l'erreur la plus grave de
  cette session. Le test dédié doit exister et passer.
- **Sur-architecture** : pas de couche « repository » abstraite, pas d'event
  bus. Des fonctions de service qui utilisent une session de base, c'est assez.
- **Images stockées dans la base** : refuser, elles restent sur disque.
- **Ligne de commande cassée** : `--dry-run` doit marcher à la fin.

---

## Validation finale (toi)

1. Tests verts, `--dry-run` OK.
2. Créer un inventaire avec une dizaine de vraies photos, lancer l'extraction
   avec la clé API, exporter.
3. Corriger deux champs en ligne de commande (ou via un petit script), réexporter :
   les corrections apparaissent, et l'extraction d'origine est toujours en base.
4. Regarder `stats_inventaire` : coût en tokens de tes 10 bouteilles. C'est ton
   premier chiffre de coût réel par bouteille.
5. Commit final : `git commit -am "session 2 : bibliothèque + base de données"`.

Prochaine session : tâches de fond (extraction en parallèle, reprise après
erreur) et API, pour préparer les écrans.