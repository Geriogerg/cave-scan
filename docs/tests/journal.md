# Journal de la boucle qualité

Tenu par Claude à chaque tour ; lu par le testeur avant de commencer.

- **Corrigé** : à revérifier par le testeur.
- **Écarté** : point volontairement non traité, avec sa raison (contrainte de
  CLAUDE.md, hors champ, ou choix motivé). Le testeur ne le signale pas de
  nouveau, sauf élément nouveau.

| Tour | Id | Gravité | Point | Suite donnée | Commit |
|---|---|---|---|---|---|
| 1 | T1-B1 | bloquant | Quantité tapée sur « Vérifier » perdue au lancement | Corrigé : enregistrée au changement et emportée par « Lancer l'analyse » | lot 1 |
| 1 | T1-B2 | bloquant | Réimporter la version active : erreur 500 | Corrigé : message « Aucun changement » | lot 1 |
| 1 | T1-M1 | majeur | Relecture bloquée après « Revenir » ou saisie identique | Corrigé dans relecture.js (champ retenu par requête ; saisie revenue = inchangée) | lot 1 |
| 1 | T1-M2 | majeur | Excel « À vérifier » : clés internes | Corrigé : noms de colonnes de la maison | lot 2 |
| 1 | T1-M3 | majeur | Configuration : refus hors écran | Corrigé : défilement vers le message, colonne fautive encadrée | lot 2 |
| 1 | T1-M4 | majeur | Configuration : messages techniques ou en anglais | Corrigé : colonnes par leur nom, un seul message pour une colonne sans nom, JSON illisible en français | lot 2 |
| 1 | T1-m1 | mineur | Durée d'analyse qui grandit | Corrigé : figée à la dernière lecture | lot 3 |
| 1 | T1-m2 | mineur | « En pause » après restauration | Corrigé : pas de pause affichée quand tout est analysé | lot 3 |
| 1 | T1-m9 | mineur | Clos : Valider refusé | Corrigé : « Bouteille suivante » à la place | lot 3 |
| 1 | T1-m10 | mineur | Double clic Valider | Corrigé : 2e envoi ignoré, bouton désactivé pendant l'envoi | lot 3 |
| 1 | T1-m11 | mineur | Messages en double ; remise sans message | Corrigé : un seul message (pause, clôture, signalement, réanalyse) ; remise annoncée | lot 3 |
| 1 | T1-m13 | mineur | Renommer vide : contexte perdu | Corrigé : « Revenir à l'inventaire », message à l'impératif | lot 3 |
| 1 | T1-S2 | suggestion | « extraite(s) » | Corrigé : « analysée(s) » dans le suivi | lot 3 |
| 1 | T1-m3 | mineur | Barres d'actions qui débordent au téléphone | Corrigé : deux boutons par rangée | lot 4 |
| 1 | T1-m7 | mineur | Relecture au téléphone chargée | Corrigé : auteur et touches masqués sans clavier, photo moins haute, marque sur une ligne | lot 4 |
| 1 | T1-m8 | mineur | Valider sous le bas de l'écran | Corrigé : zone de validation collée en bas | lot 4 |
| 1 | T1-m14 | mineur | Incohérences visuelles | Corrigé : une couleur de lien, récapitulatif centré, barre alignée sur la colonne, barre de progression | lot 4 |
| 1 | T1-m6 | mineur | Badges d'origine faux | Corrigé : « saisie au dépôt » pour la quantité ; après « Revenir », le badge d'origine revient | lot 5 |
| 1 | T1-m12 | mineur | Noms techniques dans les messages | Corrigé : conflits par nom de colonne ; adresse mal formée ou inconnue = page 404 en français (l'API garde son JSON) | lot 5 |
| 1 | T1-S5 | suggestion | Accueil sans avancement de la relecture | Corrigé : « N validée(s) » ; « Analyse en pause » au lieu d'« annulée » | lot 5 |
| 1 | T1-S8 | suggestion | Clôture sans liste | Corrigé : lien vers le récapitulatif, qui liste les bouteilles non validées | lot 5 |
| 1 | T1-S9 | suggestion | Export d'un inventaire vide | Corrigé : refusé, avec la raison | lot 5 |
| 1 | T1-S7 | suggestion | Confirmation au-delà de 100 exemplaires | Écarté : une caisse ou un lot de cave dépasse parfois 100 ; une confirmation ralentirait l'expert pour un cas rare, la quantité est visible au dépôt, à la vérification et dans l'Excel | — |
| 1 | T1-m4 | mineur | Numérotation galerie / vérification | Corrigé : le dépôt affiche les numéros de « Vérifier » ; la bouteille vide ne compte pas | lot 6 |
| 1 | T1-m5 | mineur | Dépôt : compteur après reprise, miniatures, HEIC | Corrigé : resynchronisation avec le serveur, miniatures des photos reçues, pastille « 📷 HEIC » au lieu d'une image cassée | lot 6 |
| 1 | T1-S1 | suggestion | « Vérifier » au téléphone trop long | Corrigé : trois vignettes par rangée | lot 6 |
| 1 | T1-S3 | suggestion | Configuration trop longue | Corrigé : chaque colonne repliable (ouverte si nouvelle ou refusée) | lot 6 |
| 1 | T1-S3b | suggestion | Aperçu modèle en phrases | Écarté : l'aperçu montre EXACTEMENT ce qui part au modèle (demande de la session 6) ; une paraphrase pourrait s'en écarter | — |
| 1 | T1-S4 | suggestion | Liste des envois qui s'allonge | Corrigé : les envois réussis ne s'affichent plus (ils sont sur les vignettes) | lot 6 |
| 1 | T1-S6 | suggestion | Clé interne visible | Corrigé : identifiant dans un « réglage avancé » pour une nouvelle colonne, caché ensuite | lot 6 |
| 2 | T2-B1 | bloquant | Quantité démesurée : 500 ; « Lancer » muet ; faux « connexion interrompue » | Corrigé : plafond 100 000 partout, refus en clair ; toute réponse 500 se dit en français | lot 7 |
| 2 | T2-B2 / T2-D2 | majeur | Configuration : colonnes qui se replient, colonne déplacée perdue | Corrigé : les colonnes ouvertes le restent, la colonne qui a agi est mise en vue | lot 7 |
| 2 | T2-B3 / T2-D3 | mineur | Aide des photos à trous au téléphone | Corrigé : masquée sans clavier | lot 7 |
| 2 | T2-B4 / T2-D4 | mineur | Durée allongée par une réanalyse | Corrigé : seule la première lecture de chaque bouteille compte | lot 7 |
| 2 | T2-B5 | mineur | Texte sans plafond | Corrigé : 1 000 caractères au plus | lot 7 |
| 2 | T2-B5b | mineur | Estimation « abc » acceptée | Écarté : la colonne est un texte libre dans la config, pour saisir une fourchette (« 800-1000 ») ; la maison peut la passer en « nombre » | — |
| 2 | T2-B6 | mineur | Bouteille vide « Bouteille 1 » en double | Corrigé : la bouteille vide prend le numéro qui suit | lot 7 |
| 2 | T2-B7 | suggestion | Cibles tactiles de 19–21 px | Corrigé : 44 px | lot 7 |
| 2 | T2-B8 | suggestion | Texte cité pris pour un bouton | Corrigé : « le bouton … ci-dessous / en bas de l'écran » | lot 7 |
| 2 | T2-D1 | mineur | Dépôt dans un autre navigateur : numérotation à 1 | Corrigé : les bouteilles en attente du serveur sont listées et numérotées | lot 8 |
| 2 | T2-D5 | mineur | Conflit qui fige un autre champ | Corrigé : après « Enregistrer quand même », les champs bloqués repartent seuls ; message « Pas enregistré : … » | lot 8 |
| 2 | T2-D6 | mineur | « Donner un nom », « entier ≥ 1 attendu », bouteille non citée | Corrigé : « Donnez un nom à la vente », « indiquez un nombre de bouteilles (1 ou plus) », numéro de la bouteille | lot 8 |
| 2 | T2-D7 | mineur | « à saisir » / « — à remplir — » | Corrigé : un mot par état, fond rose réservé à « à remplir » | lot 8 |
| 2 | T2-D8 | mineur | Refus de photo caché sous la barre | Corrigé : affiché dans la carte de la bouteille | lot 8 |
| 2 | T2-D9 | mineur | Incohérences d'écran | Corrigé : nom d'inventaire en lien (dépôt, vérifier), « Quantité » en galerie, barre pleine largeur, boutons du suivi, « sa photo / ses N photos », espaces insécables | lot 8 |
| 2 | T2-D10 | mineur | Archivé invisible | Corrigé : bandeau « Inventaire archivé — Sortir des archives », avancement sur les cartes d'archives, « se met à jour » seulement pendant l'analyse | lot 8 |
| 2 | T2-D11 | mineur | Pas de confirmation après Valider | Corrigé : « Bouteille n°X validée. » sur la suivante. Focus sur un champ : écarté (Entrée dans un champ enregistre le champ au lieu de valider la bouteille : le flux clavier de l'expert serait cassé) | lot 8 |
| 2 | T2-D12 | mineur | Récapitulatif / configuration techniques | Corrigé : un retour au modèle n'est plus compté, plus de nom de fichier, « noyau » expliqué, « Séparer » relibellé, doublon de liste dit simplement | lot 8 |
| 2 | T2-DS1 | suggestion | Dépôt en mode galerie à l'ordinateur | Corrigé (premier passage, selon le pointeur) | lot 8 |
| 2 | T2-DS2 | suggestion | « Vérifier » compact à l'ordinateur | Corrigé : deux cartes par rangée, vignettes plus petites | lot 8 |
| 2 | T2-DS3 | suggestion | Photo visible pendant la saisie au téléphone | Corrigé : photo collée en haut (30 % de l'écran), champs resserrés, Valider ne recouvre plus | lot 8 |
| 2 | T2-DS4 | suggestion | « Vérifier et lancer » trop tôt en avant | Corrigé : bouton principal seulement avec des photos | lot 8 |
| 2 | T2-DS5 | suggestion | Barre de configuration trop haute | Corrigé : une rangée au téléphone, affichée après une modification (toujours là sans JavaScript) | lot 8 |
| 3 | T3-R2 | majeur | Tests encore liés à `config/maisons/` (105 tests, indirectement) | Corrigé : `CAVE_SCAN_CONFIGS`, copie figée par test ; suite verte avec dossier vide et avec colonne renommée | lot 9 |
| 3 | T3-R3 | — | 42 assertions sur de longues phrases | Corrigé : mots-clés ; `test_style_des_tests.py` l'impose ; 3 exceptions (données) justifiées dans ce fichier | lot 9 |
| 3 | T3-R5 | — | Score muet sur des consignes modifiées | Corrigé : avertissement dans le rapport de score et les signaux ; test | lot 9 |
| 3 | T3-R8 / T3-D2 (partie) | majeur | Fausse alerte few-shot sur « observee » | Corrigé : une citation déjà dans le texte d'origine n'est pas signalée ; test. Le jargon du message reste à traiter (T3-D2) | lot 9 |
| 3 | T3-R7 / T3-R10 | — | Documentation fausse (tests.sh, vérificateur) | Corrigé : textes à jour. Le message du commit e464954 reste faux (historique non réécrit) : R2 n'était pas faite à ce moment | lot 9 |
| 3 | T3-R9 | — | `test_arret_brutal…` instable sous forte charge | À surveiller, non affaibli (une occurrence, non reproduite) | — |
| 3 | T3-D1 | bloquant | Quantité remise à 1 en reprenant une bouteille sur un autre appareil | Corrigé : quantité lue sur le serveur, n'est renvoyée que si changée sur cet appareil ; test navigateur à deux appareils | lot 10 |
| 3 | T3-D12 (T2-D1) | mineur | Bouteilles d'un autre appareil invisibles en galerie | Corrigé : toutes les bouteilles photographiées ont leur carte, dans l'ordre | lot 10 |
| 3 | T3-D5 (T2-D8) | majeur | Photo refusée pour le plafond, invisible | Corrigé : refus dans la carte et dans le résumé | lot 10 |
| 3 | T3-D8 | mineur | Quantité démesurée au dépôt : photo refusée | Corrigé : contrôlée à la saisie (message sous le champ) ; la photo n'est plus refusée pour la quantité ; champ de 6 chiffres | lot 10 |
| 3 | T3-D16 | mineur | Refus de photo : nom coupé | Corrigé : nom entier. Le doublon carte / liste reste : la liste du bas est le seul endroit visible pour une bouteille sans carte à l'écran | lot 10 |
| 3 | T3-D19 | mineur | Ordre des bouteilles instable | Corrigé : toujours par numéro | lot 10 |
