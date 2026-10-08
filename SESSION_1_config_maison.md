# Session 1 — Config par maison

Objectif : rendre tout le pipeline piloté par un fichier de configuration par
maison (`config/maisons/maison_test.json`). Changer de maison ou de nomenclature
= modifier un JSON, jamais le code.

---

## Étape 0 — Préparer le repo (5 min, à faire toi-même)

1. Sauvegarder la v0 dans git (si ce n'est pas déjà fait) :
   ```bash
   git init            # seulement si le repo n'existe pas encore
   git add -A
   git commit -m "v0 fonctionnelle"
   ```
2. Vérifier que `.gitignore` exclut au minimum :
   ```
   .env
   data/
   *.jpg
   *.jpeg
   *.png
   __pycache__/
   .venv/
   ```
3. Poser les fichiers à la racine du repo :
   - `CLAUDE.md` (remplace l'ancien)
   - `decisions.md` (remplace l'ancien)
   - `ROADMAP.md`
   - `config/maisons/maison_test.json`
4. Dans VS Code, vérifier en bas à droite que l'encodage des `.md` est **UTF-8**.
5. Commit : `git commit -am "contexte + config de test"`.

---

## Étape 1 — Ouvrir Claude Code

Ouvrir le dossier du repo dans VS Code, puis Claude Code (panneau de l'extension,
ou `claude` dans le terminal intégré, à la racine du repo).

---

## Étape 2 — Message de contrôle (à coller en premier)

```
Lis CLAUDE.md et decisions.md en entier (pas ROADMAP.md). Puis explore le code
existant sans rien modifier, et réponds-moi avec :
1. l'architecture actuelle du repo (modules, rôle de chacun, point d'entrée) ;
2. les contraintes dures que tu dois respecter ;
3. ce qui, dans le code actuel, est encore piloté par l'ancienne config YAML
   ou codé en dur et devra passer par la config JSON.
Ne modifie aucun fichier.
```

**Ce que tu dois retrouver dans sa réponse** : pas de devinette (non lisible /
non déterminable), estimation jamais remplie par le modèle, pas de few-shot,
normalisation = identité, extraction par VLM. S'il manque un de ces points,
redis-lui de relire `decisions.md` avant de continuer.

---

## Étape 3 — Demander un plan (sans coder)

```
Avant de coder, propose-moi un plan pour la session décrite ci-dessous :
fichiers créés ou modifiés, changements éventuels du contrat de Bouteille,
ordre des commits. Attends ma validation.
```

Puis colle le prompt de l'étape 4 juste en dessous, dans le même message.

---

## Étape 4 — Le prompt de la session

```
OBJECTIF — rendre le pipeline entièrement piloté par la config de maison
config/maisons/maison_test.json, qui remplace l'ancienne config YAML.

1. Chargement et validation de la config (src/config/) :
   - charger le JSON et le valider strictement au démarrage (clés uniques,
     types connus : texte | liste | nombre, sources connues : modele |
     modele_best_effort | expert | systeme) ; message d'erreur clair sinon ;
   - ajouter automatiquement « Non déterminable » à chaque colonne de type
     liste, sans qu'il soit écrit dans le fichier ;
   - conserver le numéro de version de la config dans chaque export.

2. Schéma d'extraction dynamique (src/extract/) :
   - générer le schéma tool-use à partir des colonnes dont la source est
     modele ou modele_best_effort ; les colonnes de type liste deviennent des
     enums, et les descriptions de valeurs (et la "regle" éventuelle) sont
     injectées dans le schéma ;
   - le noyau canonique (domaine, appellation, millésime, format) reste
     toujours extrait, même si une config ne l'affiche pas (decisions 0021) ;
   - les colonnes expert et systeme ne sont JAMAIS envoyées au modèle ;
   - toute valeur issue d'une colonne modele_best_effort est ajoutée à
     a_verifier.

3. Une ligne = une bouteille (decisions 0016-0017) :
   - chaque bouteille reçoit un identifiant stable ;
   - quantité = 1 par défaut, modifiable par l'expert ;
   - à l'export, regrouper les bouteilles dont les champs listés dans
     regroupement_export sont identiques, en additionnant les quantités.
     Deux bouteilles d'état différent restent sur deux lignes.

4. Appariement des photos par ordre (decisions 0023) :
   - photos triées par date de prise de vue (EXIF), sinon par nom de fichier ;
     paires étiquette / contre-étiquette dans l'ordre ;
   - si le nombre de photos est impair, s'arrêter avec un message explicite
     (aucun appariement silencieux) ;
   - signaler dans a_verifier toute paire où le modèle indique que les deux
     photos ne semblent pas être la même bouteille.

5. Export Excel : colonnes, en-têtes et ordre exactement selon la config ;
   les valeurs « Non déterminable » sont affichées vides et la ligne est
   surlignée.

CRITÈRES D'ACCEPTATION :
- --dry-run fonctionne avec maison_test.json, sans clé API.
- Tests hors ligne : config invalide rejetée ; « Non déterminable » ajouté ;
  colonnes expert et systeme absentes du schéma envoyé au modèle ;
  regroupement 5 + 1 correct ; nombre de photos impair refusé.
- Changer un libellé ou une valeur dans le JSON change l'export sans toucher
  au code.
- Le test de comparaison existant reste vert.

À NE PAS FAIRE : pas d'interface, pas de normalisation, pas d'estimation,
pas de few-shot. Si le contrat de Bouteille doit changer, montre-moi le
changement proposé avant de l'appliquer.

Un commit par étape, avec diff et sortie des tests. Ajoute dans decisions.md
une ligne pour chaque choix technique tranché.
```

---

## Étape 5 — Pendant la session : ce qu'il faut surveiller

- **Colonnes expert envoyées au modèle** (estimation, quantité) : c'est l'erreur
  la plus probable. Si le modèle les reçoit, il essaiera de les remplir.
  Vérifie le test correspondant.
- **Normalisation glissée en douce** (retirer « Domaine », etc.) : refuser, ce
  sera la session suivante.
- **Appariement silencieux** : avec un nombre impair de photos, l'outil doit
  s'arrêter, pas deviner.
- **Un commit par étape** : si une étape part de travers, `git reset` sur le
  commit précédent plutôt que de corriger par-dessus.

---

## Étape 6 — Validation finale (à faire toi-même)

1. `python run_v0.py --dry-run` → l'Excel sort avec les colonnes de
   `maison_test.json`, dans l'ordre.
2. Modifier un libellé dans le JSON (ex. « Rouge » → « Vin rouge »), relancer :
   l'export change, aucun code touché.
3. Lancer sur une dizaine de **vraies** photos avec la clé API : vérifier qu'aucune
   estimation n'est remplie et que les champs best effort sont dans « À vérifier ».
4. Tests verts.
5. Commit final : `git commit -am "session 1 : config par maison"`.

Session terminée quand ces 5 points sont OK. Prochaine session : base de données
et réorganisation en bibliothèque, puis application web.
