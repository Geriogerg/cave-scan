# Session 4 — Application web : dépôt des photos

Objectif : l'expert crée un inventaire, envoie ses photos depuis son téléphone,
vérifie l'ordre des paires, lance l'extraction et suit sa progression. C'est le
premier écran que l'expert verra : il doit être simple, robuste sur un réseau
instable, et ne jamais perdre une photo en silence.

Prérequis : session 3 terminée (worker, API JSON, tests verts).

Hors périmètre : l'écran de relecture (session 5), la connexion (session 7).

---

## 1. Le parcours de l'expert

1. **Accueil** : liste des inventaires (nom, maison, date, statut, progression)
   et un bouton « Nouvel inventaire ».
2. **Nouvel inventaire** : nom de la vente, choix de la maison. Crée un
   inventaire en **brouillon**.
3. **Dépôt des photos** : ajout des photos, envoi une par une avec progression,
   possibilité d'en ajouter en plusieurs fois.
4. **Vérification de l'ordre** : aperçu des paires (étiquette | contre-étiquette)
   en miniatures numérotées ; l'expert peut supprimer une photo, inverser les
   deux photos d'une paire, déplacer une photo. Les anomalies sont signalées
   (nombre impair, doublon, photo illisible).
5. **Lancement** : « Lancer l'analyse », possible uniquement si le nombre de
   photos est pair et qu'aucune n'est en cours d'envoi. L'inventaire quitte le
   brouillon, les paires deviennent des bouteilles, l'extraction démarre.
6. **Suivi** : progression mise à jour automatiquement (bouteilles extraites,
   en erreur, temps restant estimé), bouton pour relancer les erreurs, et
   téléchargement de l'Excel une fois terminé. Le lien vers la relecture est
   présent mais indique « bientôt disponible ».

---

## 2. Les points techniques qui font la différence

### Ajouter des photos depuis un téléphone

Un simple champ de sélection de fichiers suffit : sur iPhone et Android, il
propose la galerie et l'appareil photo, sans application à installer. Deux
boutons :

- **« Choisir dans la galerie »** : sélection multiple, le cas normal (photos
  prises en cave, envoyées au bureau) ;
- **« Prendre une photo »** : ouvre directement l'appareil, une photo à la fois,
  ajoutée à la suite. Utile pour reprendre une photo ratée.

L'accès direct à la caméra en continu (flux vidéo dans la page) n'est pas
nécessaire et exige une connexion sécurisée : hors périmètre.

### Le volume

300 bouteilles = 600 photos, de 3 à 5 Mo chacune sur un téléphone récent, soit
2 à 3 Go. C'est trop lourd à envoyer d'un bloc, surtout en 4G. Deux mécanismes :

- **Envoi fichier par fichier** : chaque photo est une requête séparée. Si le
  réseau coupe, les photos déjà envoyées sont acquises, et l'envoi reprend là
  où il s'est arrêté. Une photo déjà reçue (même empreinte) n'est pas renvoyée
  deux fois. Envois limités à 2 ou 3 simultanés.
- **Réduction avant envoi**, dans le navigateur : la photo est redimensionnée
  (côté long autour de 2 500 pixels, JPEG de bonne qualité) avant d'être
  envoyée, ce qui divise le poids par 4 à 6.

**La réduction doit être mesurée, pas supposée.** Un millésime en petits
caractères peut devenir illisible. Avant de l'activer par défaut, on compare sur
un échantillon de vraies photos les résultats d'extraction sur les originaux et
sur les versions réduites. Si le score baisse, on augmente la taille cible. Une
option permet d'envoyer les originaux.

### Le piège de l'ordre

L'appariement repose sur l'ordre des photos (prise de vue). Deux risques :

- la **réduction dans le navigateur efface les métadonnées EXIF**, dont la date
  de prise de vue. Il faut lire cette date **avant** de réduire la photo, et
  l'envoyer à côté du fichier ;
- l'**ordre de sélection dans la galerie** n'est pas toujours l'ordre de prise de
  vue, et diffère selon le téléphone.

Règle : le serveur trie par date de prise de vue (lue avant réduction), puis par
nom de fichier, puis par ordre d'arrivée. Et l'écran de vérification de l'ordre
est **obligatoire** avant le lancement : l'expert voit les paires, et corrige.

### Photos iPhone (HEIC)

Lors d'un envoi depuis un navigateur, l'iPhone convertit généralement ses photos
en JPEG, mais pas dans tous les cas. Un fichier HEIC reçu doit être soit lu (si
la lecture HEIC est en place côté serveur), soit refusé avec un message clair
indiquant comment régler l'iPhone. Jamais ignoré en silence.

### Le navigateur mobile en arrière-plan

Un navigateur mobile suspend une page passée en arrière-plan ou dont l'écran
s'éteint : l'envoi s'arrête. L'écran doit :

- demander à garder l'écran allumé pendant l'envoi quand le navigateur le
  permet ;
- afficher clairement « Gardez cette page ouverte pendant l'envoi » ;
- reprendre automatiquement l'envoi au retour sur la page.

### Tester depuis un vrai téléphone

Le serveur n'écoute qu'en local par défaut. Pour tester depuis ton téléphone, une
option de développement explicite permet l'écoute sur ton réseau Wi-Fi, avec un
avertissement au démarrage. Sans connexion (session 7), toute personne sur ce
réseau peut accéder à l'application : à utiliser chez toi, jamais sur le réseau
d'un client.

---

## 3. Changements côté serveur

L'API de la session 3 crée un inventaire avec toutes ses photos d'un coup. Le
dépôt en plusieurs fois demande :

- un statut **brouillon** pour l'inventaire (migration de base) ;
- ajouter une photo à un brouillon (avec sa date de prise de vue fournie à
  part) ; idempotent par empreinte ;
- supprimer une photo d'un brouillon, réordonner, inverser une paire ;
- obtenir l'aperçu des paires et les anomalies ;
- **finaliser** : vérifier les garde-fous, créer les bouteilles, lancer
  l'extraction. Plus aucune modification de photos ensuite.

Ces opérations sont des fonctions de service, utilisées à la fois par les pages
et par l'API JSON.

Miniatures : générées côté serveur à la réception, servies par la route
sécurisée existante.

---

## 4. Apparence

- Sobre et lisible : fond clair, texte foncé, une seule couleur d'accent.
- Pensé pour une main sur téléphone : boutons larges (au moins 44 pixels de
  haut), actions principales en bas de l'écran, pas de petites icônes seules.
- Textes en français, courts, orientés action (« Ajouter des photos »,
  « Vérifier l'ordre », « Lancer l'analyse »).
- Chaque état est visible : en cours d'envoi, envoyée, refusée (avec la raison),
  doublon.
- Fonctionne sur Safari iPhone et Chrome Android récents, et sur ordinateur.

---

## 5. Critères d'acceptation

**Tests automatisés (hors ligne)**
- Chaque page s'affiche sans erreur ; le parcours complet brouillon → dépôt →
  vérification → lancement → suivi → export fonctionne avec l'extracteur factice.
- Une photo renvoyée deux fois n'est enregistrée qu'une fois.
- Le tri utilise la date de prise de vue fournie, puis le nom, puis l'ordre
  d'arrivée.
- Supprimer, déplacer, inverser une paire modifie bien l'appariement.
- Lancement refusé si le nombre de photos est impair, avec le message prévu.
- Après finalisation, plus aucune modification de photos n'est possible.
- Un fichier non image ou HEIC illisible est refusé avec une raison claire.
- Les règles de sécurité de la session 3 tiennent toujours (photo d'un autre
  inventaire refusée, pas d'EXIF renvoyé).
- Tous les tests précédents restent verts ; `--dry-run` fonctionne.

**Test de navigation (recommandé)**
- Un test de bout en bout dans un navigateur automatisé, avec un écran au format
  téléphone : créer un inventaire, envoyer 6 photos, inverser une paire, lancer,
  attendre la fin, télécharger l'Excel.

**Mesure**
- Comparaison de l'extraction sur originaux et versions réduites, sur un
  échantillon de vraies photos ; taille de réduction retenue notée dans
  `decisions.md`.

---

## 6. Ce qu'il faut surveiller

- **Un framework JavaScript qui s'installe** (React, Vue, outils de build) : à
  refuser.
- **Des garde-fous seulement côté navigateur** : le serveur doit toujours
  vérifier.
- **La date de prise de vue perdue** à la réduction : c'est le bug le plus
  probable de la session, et il est silencieux.
- **Un envoi en un seul bloc** de toutes les photos : à refuser.
- **Une réduction activée sans mesure** de son effet sur l'extraction.

---

## 7. Validation finale (toi)

1. Tests verts.
2. Démarrer en mode réseau local, ouvrir l'application sur ton téléphone.
3. Créer un inventaire, envoyer une vingtaine de vraies photos depuis la
   galerie ; couper le Wi-Fi au milieu, le rétablir : l'envoi reprend.
4. Vérifier l'ordre des paires, en inverser une, lancer, suivre jusqu'à la fin,
   télécharger l'Excel.
5. Recommencer avec un iPhone si tu en as un sous la main (HEIC, Safari).
6. Faire faire le parcours à ton frère **sans lui expliquer** : noter où il
   hésite. C'est le meilleur test d'ergonomie disponible.
7. Commit final.

Prochaine session : l'écran de relecture.
