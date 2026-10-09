# Session 3 — Tâches de fond + API

Objectif : que l'extraction d'un inventaire de 300 bouteilles tourne **en
arrière-plan, en parallèle, sans rien perdre**, et que tout ce dont les futurs
écrans auront besoin soit accessible par une **API JSON**. Aucun écran dans
cette session : on pose la mécanique que les sessions 4 et 5 viendront habiller.

Prérequis : session 2 terminée (fonctions de service, base, migrations, tests
verts).

---

## 1. Ce que cette session apporte

- Un **processus worker** qui traite les bouteilles à extraire, plusieurs à la
  fois, et qui survit aux redémarrages.
- Une **API JSON** (FastAPI) qui expose les fonctions de service : créer un
  inventaire avec ses photos, lancer et suivre l'extraction, consulter et
  corriger les bouteilles, valider, exporter.
- La **mesure réelle** du temps et du coût d'un inventaire de taille pilote.

La ligne de commande continue de fonctionner et passe par les mêmes fonctions.

---

## 2. Tâches de fond

### File d'attente en base

Pas de Redis ni de Celery. Le statut des bouteilles (déjà en base depuis la
session 2) sert de file d'attente :

- lancer l'extraction d'un inventaire = marquer ses bouteilles « à extraire » ;
- le worker **réserve** une bouteille de façon atomique (une seule réservation
  possible), la passe « en cours », l'extrait, enregistre le résultat ;
- une bouteille réservée porte un **horodatage de vie** mis à jour pendant le
  traitement ; si le worker s'arrête brutalement, une bouteille « en cours »
  dont l'horodatage est trop ancien est remise « à extraire ».

Note SQLite : activer le mode WAL et garder des transactions courtes. Au passage
à PostgreSQL (session 7), la réservation s'appuiera sur le verrouillage de ligne
prévu pour ce cas (`SKIP LOCKED`). La logique doit être isolée dans une fonction
pour que ce changement ne touche qu'elle.

### Parallélisme

- Nombre d'extractions simultanées configurable (défaut prudent : 4).
- Respect des limites de débit de l'API du modèle : en cas de limite atteinte,
  ralentir, pas multiplier les tentatives.
- Classification des erreurs inchangée (décidée en session 2) : systématique →
  arrêt de l'inventaire ; passagère → nouvelles tentatives avec délai croissant,
  puis erreur sur la bouteille ; réponse inexploitable → erreur sur la bouteille.

### Contrôle d'un inventaire

- **Lancer** : idempotent, relancer ne crée pas de doublon.
- **Annuler** : les bouteilles pas encore commencées repassent « à extraire »
  sans être traitées ; celles en cours terminent proprement.
- **Relancer les erreurs** : remet les bouteilles en erreur « à extraire ».
- **Progression** : nombre de bouteilles par statut, coût cumulé, temps écoulé
  et estimation du temps restant.

### Lancement

Deux processus : le serveur API et le worker, lançables chacun par une commande
simple. Pour le développement, une commande unique peut démarrer les deux.

---

## 3. API JSON

Couche fine : valider l'entrée, appeler la fonction de service, mettre en forme
la réponse. Pas de logique métier dans les routes.

### Ressources attendues

**Maisons et configs**
- lister les maisons et leur version de config active.

**Inventaires**
- créer un inventaire : nom, maison, envoi des photos (plusieurs fichiers) ;
  l'appariement et les garde-fous de la session 1 s'appliquent (nombre impair
  refusé avec un message clair, doublons détectés) ;
- lister les inventaires ;
- consulter un inventaire : statut, progression, statistiques ;
- lancer, annuler, relancer les erreurs ;
- valider l'inventaire ;
- télécharger l'export Excel.

**Bouteilles**
- lister les bouteilles d'un inventaire, paginées, filtrables par statut et par
  « à vérifier » ;
- consulter une bouteille : valeurs courantes, valeurs du modèle, champs à
  vérifier, historique des corrections, liens vers ses deux photos, position
  dans l'inventaire (précédente / suivante, pour la future relecture) ;
- corriger un champ ;
- modifier la quantité ;
- valider la bouteille.

**Photos**
- servir une photo par son identifiant, après vérification qu'elle appartient
  bien à l'inventaire demandé ; une version réduite pour l'affichage, et
  l'originale à la demande ;
- jamais de liste de dossier, jamais de métadonnées EXIF dans les réponses.

### Envoi des photos

- formats acceptés : JPEG, PNG, HEIC (si la lecture HEIC est en place) ;
- chaque fichier est réellement ouvert pour vérifier que c'est une image ;
- limites de taille par fichier et de nombre par inventaire (au moins 600 photos,
  soit 300 bouteilles) ;
- rotation EXIF appliquée pour l'affichage, l'original conservé tel quel.

### Erreurs

Format de réponse d'erreur unique et lisible (code, message en français, détail
éventuel), réutilisable tel quel par les futurs écrans. Les messages des
garde-fous (nombre impair de photos, valeur hors liste, inventaire contenant une
bouteille en erreur…) doivent être compréhensibles par l'expert, pas seulement
par un développeur.

### Sécurité pour cette session

Pas encore de connexion (session 7) : le serveur n'écoute qu'en local. Les routes
sont tout de même organisées pour qu'ajouter l'authentification ne demande pas de
les réécrire.

---

## 4. Critères d'acceptation

Tests hors ligne, avec un extracteur factice (latence et erreurs simulables) :

**Worker**
- 300 bouteilles factices traitées avec 4 extractions simultanées : toutes
  extraites, aucune en double.
- Arrêt brutal du worker en cours de traitement, puis redémarrage : les
  bouteilles interrompues sont reprises, aucune perdue, aucune en double.
- Erreur systématique simulée : l'inventaire s'arrête, les bouteilles non
  traitées restent « à extraire ».
- Erreur passagère simulée : nouvelles tentatives, puis succès ou erreur sur la
  bouteille seule.
- Annulation : les bouteilles non commencées ne sont pas traitées.
- Relancer un inventaire déjà lancé ne crée aucun doublon.

**API**
- Parcours complet : créer un inventaire avec photos → lancer → attendre la fin
  → lister → corriger → valider → exporter. L'Excel obtenu est identique à celui
  produit par la ligne de commande sur les mêmes données.
- Nombre impair de photos, fichier non image, valeur hors liste : refusés avec un
  message d'erreur clair.
- Une photo demandée via un autre inventaire que le sien est refusée.
- Aucune réponse ne contient de métadonnées EXIF.
- La documentation interactive de l'API est générée et à jour.

**Non-régression**
- Tous les tests des sessions précédentes restent verts ; `--dry-run` fonctionne.

---

## 5. Ce qu'il faut surveiller

- **Logique métier dans les routes** : une route qui fait plus que valider,
  appeler un service et répondre est à refuser.
- **État en mémoire** : une file d'attente, un compteur ou un cache en mémoire
  dans le serveur ou le worker est à refuser ; tout passe par la base.
- **Infrastructure ajoutée sans besoin** (Redis, Celery, conteneurs) : hors
  périmètre pour le pilote.
- **Photos exposées comme un dossier statique** : à refuser.
- **Tests du worker qui « attendent » avec des pauses fixes** : ils deviennent
  instables ; ils doivent attendre une condition (toutes les bouteilles
  extraites) avec une limite de temps.

---

## 6. Validation finale (toi)

1. Tests verts, `--dry-run` OK.
2. Démarrer le serveur et le worker, ouvrir la documentation interactive de
   l'API dans le navigateur.
3. Créer un inventaire de 20 à 30 vraies photos depuis la documentation, lancer,
   suivre la progression jusqu'à la fin.
4. Pendant l'extraction, arrêter le worker, le relancer : vérifier que tout
   reprend sans doublon.
5. Corriger deux champs, valider, télécharger l'Excel.
6. Noter dans `decisions.md` : temps total, coût total, temps et coût par
   bouteille, et l'extrapolation pour 300 bouteilles. C'est la base du prix.
7. Commit final.

Prochaine session : premier écran web, le dépôt des photos depuis un téléphone.
