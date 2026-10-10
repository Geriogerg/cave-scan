# CLAUDE.md

> Règles permanentes, lues à chaque session. En cas de doute métier, ce fichier
> tranche ; s'il est muet, demande. Les règles détaillées par domaine sont dans
> `.claude/rules/` et se chargent quand tu travailles sur les fichiers concernés.
> Le périmètre de la session en cours est dans `docs/sessions/`. Ne lis pas
> `ROADMAP.md` ni les guides des sessions passées.

## Le produit

Assistant de catalogage de vins pour maisons de vente. L'expert dépose les photos
(étiquette + contre-étiquette), un modèle vision-langage extrait les champs,
l'expert relit et corrige, l'outil exporte un Excel au format de la maison.
On ne remplace pas l'expert : on lui retire la saisie.

Pipeline : photos → extraction (sortie contrainte) → normalisation (identité pour
l'instant) → base de données (extraction + corrections) → relecture → export.
La ligne de commande et `--dry-run` (hors ligne, sans clé API) restent
fonctionnels à chaque session.

## Contraintes dures (ne jamais violer)

1. **Ne jamais deviner.** `non_lisible` / `non_determinable` sont des réponses
   correctes. Millésime et format ne sont jamais devinés.
2. **Le modèle ne produit jamais de prix.** L'estimation est saisie par l'expert.
3. **Les colonnes de source `expert` ou `systeme` ne sont jamais envoyées au
   modèle.**
4. **La sortie brute du modèle est immuable.** Une correction est un
   enregistrement séparé, jamais un écrasement.
5. **Aucune donnée perdue en silence** : photo refusée, envoi interrompu, erreur
   d'extraction, correction non enregistrée sont toujours signalés.
6. **Format de chaque maison piloté par sa config JSON** (`config/maisons/`),
   jamais par du code propre à une maison.
7. **Pas de few-shot ni de règles de normalisation** tant qu'une session ne le
   demande pas.

## Architecture (règles générales)

- Logique métier dans des **fonctions de service** sans état caché. Ligne de
  commande, API, worker et pages ne font que les appeler.
- Une interface (`typing.Protocol`) seulement où la variation est certaine
  (l'extracteur) ; code plat ailleurs, pas d'abstraction spéculative.
- Type hints partout ; I/O et appels au modèle isolés dans leurs modules.
- Pas d'infrastructure lourde pour le pilote (ni Redis, ni Celery, ni framework
  JavaScript).

## Règles de session

- Ne construis que le périmètre du guide de session en cours.
- Une étape, un commit, avec diff et sortie des tests. Rien ne passe si un test
  échoue ou si un score de non-régression baisse.
- Ne modifie jamais un test pour le faire passer sans accord ; n'affaiblis jamais
  un test qui vérifie une contrainte dure.
- Changement du contrat de `Bouteille` ou du schéma de base : arrête-toi et
  demande. Le schéma évolue uniquement par migrations.
- `decisions.md` : consulte la section concernée avant de trancher un choix lié ;
  ne le relis pas en entier. Ajoute une ligne pour chaque choix tranché.
- Interface et messages en français ; jamais de message technique brut montré à
  l'expert.
