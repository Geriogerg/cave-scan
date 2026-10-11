# Archive des décisions

Décisions remplacées ou devenues sans objet, retirées de `decisions.md`
(session 5). Le numéro reste réservé ; `decisions.md` garde une ligne de renvoi
à sa place. Texte d'origine, inchangé.

---

- 0005 — Colonne estimation présente mais VIDE, jamais remplie par le modèle — un
  VLM sort un prix inventé, ce qui grille la crédibilité — l'estimation viendra
  d'une couche données plus tard.

- 0011 — [format précisé par 0020 : JSON] Format de sortie piloté par config YAML par maison (fond/forme séparés) —
  changer de maison = changer de config, pas de code — écarté : une sous-classe
  formatter par maison.

- 0035 — [remplacée par 0020] Colonne de config à `champ: null` = colonne vide — un seul mécanisme
  générique couvre le lot ET l'estimation, plutôt qu'un cas particulier codé en
  dur pour l'estimation (0005) — écarté : traiter l'estimation à part.

- 0036 — [remplacée par 0052] Une colonne de config qui référence un champ inexistant lève une erreur
  au chargement — une faute de frappe doit s'arrêter là, pas livrer une colonne
  silencieusement vide à une maison de vente.

- 0037 — [remplacée par 0023] Regroupement des photos : un sous-dossier par bouteille, « contre » dans
  le nom de fichier = contre-étiquette, dossier plat = une image par bouteille —
  convention v0 isolée dans `src/io/photos.py`, **à confirmer avec l'expert** ;
  si la vraie arborescence diffère, un seul fichier change.

- 0040 — [remplacée par 0060] `requirements.txt` recentré sur la v0 (anthropic, openpyxl, pyyaml,
  pytest) — `requests`, `beautifulsoup4` et `rapidfuzz` servaient au scraping et
  au matching LWIN d'un périmètre antérieur, hors v0.

- 0045 — [remplacée par 0079] Politique d'erreur API en deux classes : panne PASSAGÈRE (429, 5xx,
  réseau) → abstention tracée dans `notes`, la campagne continue ; panne
  SYSTÉMATIQUE (401, 403, 404, 400) → remonte et arrête tout — répéter une clé
  invalide 200 fois ne produirait que 200 lignes vides en facturant chaque
  échec. La politique vit dans `vision_extract` pour que `run_v0` reste sans
  dépendance au SDK — écarté : tout avaler (aurait masqué le risque 0029).

- 0046 — [remplacée par 0079] Journal `.jsonl` écrit au fil de l'eau + `--reprendre` — une campagne de
  200 bouteilles interrompue à la 180e perdait 180 appels API déjà payés ; le
  journal est aussi la trace brute des réponses, indépendante de l'Excel —
  écarté : n'écrire qu'à la fin.

- 0047 — [remplacée par 0055] Option de config `abstention_vide` par colonne, activée sur les colonnes
  numériques de l'exemple — « non lisible » dans une colonne de nombres casse le
  tri et le filtre du commissaire-priseur. L'abstention reste visible par le
  surlignage de la ligne et la colonne « À vérifier », donc rien n'est perdu
  (compatible 0002) — écarté : masquer partout, ou n'offrir aucun réglage.
  **À confirmer avec la maison.**

- 0051 — Sur Gemini, un 429 est le RÉGIME NOMINAL, pas un incident (~15
  requêtes/minute en gratuit) : appels espacés de 4,5 s et jusqu'à 4 tentatives
  avec attente croissante avant de renoncer — sans cela, la moitié d'une
  campagne serait sortie en abstention et le score aurait été faux. La
  distinction passager/systématique de 0045 est conservée à l'identique.

- 0060 — [remplacée par 0070] Dépendances : pyyaml retiré avec l'ancienne config YAML. Restent
  google-genai, anthropic, openpyxl, python-dotenv, pytest.

- 0067 — [remplacée par 0082] Quantité « modifiable par l'expert » : stockée par bouteille (jamais
  recalculée), 1 par défaut. En attendant une interface, elle se modifie dans le
  journal puis `--auto` refait l'export ; le regroupement additionne.

- 0093 — [remplacée par 0110] À la relance, une bouteille restée `en_cours` est une extraction
  interrompue (coupure, arrêt brutal) : elle est refaite. Une relance forcée sur
  une bouteille validée la remet à relire, et c'est tracé dans l'historique
  (auteur « relance forcée (modèle) »).

- 0107 — Tests du journal adaptés (liste approuvée), chacun gardant son exigence,
  vérifiée en base : écrit au fil de l'eau -> chaque extraction en base dès son
  retour ; interruption -> aucun appel payé perdu (Ctrl-C et panne
  systématique) ; reprise du journal -> `--inventaire ID` ; journal réinitialisé
  -> nouvel inventaire, l'ancien intact ; dry-run journalisé -> dry-run hors de
  la base de l'utilisateur ; identifiant au journal -> identifiant en base et à
  l'export ; doublons -> refusés par `creer_inventaire` avant tout client ;
  dossier modifié refusé -> la reprise ne relit jamais le dossier d'origine ;
  quantité au journal -> `inventaire.py corriger`. `bouteille_depuis_dict`
  disparaît ; son test devient « un code de la maison n'est jamais perdu à la
  relecture depuis la base ».

- 0120 — Valider un inventaire = valider d'un coup toutes ses bouteilles
  extraites ; refusé, avec un message pour l'expert, s'il reste une bouteille en
  erreur ou non extraite.

- 0070 — [remplacée par 0158] Dépendances : Pillow ajouté (dates EXIF). pillow-heif NON ajouté —
  Pillow seul ne lit pas le HEIC, qui est refusé avec un message clair et la
  marche à suivre ; pillow-heif s'installe sans difficulté ici (vérifié, non
  installé) mais il faudrait en plus convertir en JPEG avant l'envoi (Anthropic
  n'accepte pas le HEIC) : à décider selon le téléphone de l'expert. Restent :
  google-genai, anthropic, openpyxl, pillow, python-dotenv, pytest.

- 0019 — [remplacée par 0162] Champs du pilote : identifiant, domaine, appellation, cuvée,
  millésime, couleur, format, quantité, état de l'étiquette, description
  générale de l'état. Niveau, capsule, bouchon : hors pilote.

- 0023 — [remplacée par 0166] Pas de réseau en cave : photos prises au téléphone dans l'ordre
  (étiquette, contre-étiquette, bouteille suivante), puis dépôt au bureau ;
  appariement par ordre, paires affichées côte à côte en relecture, paires
  incohérentes signalées. Mode hors ligne dans l'application : plus tard.

- 0068 — [remplacée par 0166] Appariement des photos par ordre (0023), sans jamais deviner : tri
  par date de prise de vue EXIF si TOUTES les photos en ont une, sinon toutes
  par nom de fichier en tri naturel (« photo 2 » avant « photo 10 ») — jamais
  de tri mixte, qui intercalerait les photos au hasard ; paires consécutives
  étiquette / contre-étiquette. ARRÊT avec message explicite sur : nombre
  impair, photo dans un format non lu (HEIC d'iPhone, TIFF, RAW…, avec le
  réglage iPhone à changer), photos rangées dans un sous-dossier (ancienne
  convention, elles ne seraient jamais lues). Fichiers non-photo ignorés.
  L'appariement est affiché AVANT l'extraction, et vérifié avant même de créer
  le client du modèle : un dossier invalide se signale sans clé ni coût —
  écarté : écarter la photo orpheline et continuer (décalage silencieux).

- 0108 — [remplacée par 0166] Contre-étiquette facultative : `run_v0.py --photos DOSSIER --sans-contre`
  traite un dossier d'étiquettes seules, une photo par bouteille (nombre impair
  accepté). C'est l'utilisateur qui le déclare, par dossier : l'outil ne devine
  jamais si une photo est une étiquette ou une contre-étiquette, et sans
  l'option l'appariement par paires reste exigé. Schéma : `photo_contre_id`
  devient facultatif (migration 0002, accord donné le 2026-10-09 ; les données
  existantes sont conservées) ; le contrat `Bouteille` ne change pas. Le modèle
  reçoit alors la seule étiquette — les extracteurs le géraient déjà.

- 0128 — [remplacée par 0166] Ordre d'un brouillon : tri automatique par date de prise de vue, puis
  nom (ordre naturel), puis ordre d'arrivée ; si une photo n'a pas de date,
  toutes sont triées par nom (0068). Dès que l'expert corrige l'ordre à la main,
  les photos ajoutées ensuite vont à la fin (et c'est signalé) ; « Retrier
  automatiquement » revient au tri.

- 0129 — [remplacée par 0166] Date de prise de vue : lue par le navigateur dans l'EXIF de l'ORIGINAL,
  avant toute réduction, et envoyée à côté du fichier ; à défaut, le serveur la
  lit dans le fichier reçu.
