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
