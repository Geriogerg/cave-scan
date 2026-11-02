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
| 3 | T3-D2 | majeur | Alerte few-shot en jargon, clé de colonne | Corrigé : « contient un exemple de réponse : le modèle risque de le recopier », colonne par son nom (la fausse alerte : lot 9) | lot 11 |
| 3 | T3-D6 | mineur | Case « Je confirme » toujours visible | Corrigé : `[hidden]` l'emporte partout ; test navigateur | lot 11 |
| 3 | T3-D7 | mineur | Refus des consignes loin de la case | Corrigé : message à côté de la case, case encadrée, mise en vue | lot 11 |
| 3 | T3-D9 | mineur | Erreur d'import : on quitte l'éditeur | Corrigé : on reste sur la configuration, le refus en haut | lot 11 |
| 3 | T3-D10 | mineur | Sans configuration : « importez-la » | Corrigé : bouton « Créer la configuration », création d'inventaire désactivée ; page vide sans titre redondant ni bouton qui ramène sur place | lot 11 |
| 3 | T3-D11 | mineur | Pas de retour aux inventaires depuis la configuration | Corrigé : « Inventaires › Configuration » dans l'en-tête (la barre du bas reste un choix à trancher, n°5) | lot 11 |
| 3 | T3-D3 | majeur | Texte trop long : clé interne ; pas de limite à la saisie | Corrigé : chaque refus nomme la colonne de l'écran (texte, liste, nombre) ; `maxlength` 1000 | lot 12 |
| 3 | T3-D4 | majeur | Excel refusé : téléchargement annulé en silence, JSON brut | Corrigé : route d'écran `/app/…/excel` ; refusé, retour au suivi avec la raison ; test | lot 12 |
| 3 | T3-D13 | mineur | Téléphone : « Valider » sur la photo | Corrigé : la photo collée passe au-dessus | lot 12 |
| 3 | T3-D14 (T2-D12) | mineur | Récapitulatif : deux comptages ; aide de « Séparer » périmée | Corrigé : une seule règle (champ lu qui diffère du modèle, ou champ de l'expert saisi) ; aide sans quantité | lot 12 |
| 3 | T3-D15 | mineur | Archiver : message en double | Corrigé : le bandeau seul | lot 12 |
| 3 | T3-D17 | mineur | Textes | Corrigé : « Action impossible » ; « vente » partout ; un seul deux-points ; guillemets insécables ; « Les valider n'est pas obligatoire » | lot 12 |
| 3 | T3-D18 | mineur | Dépôt à l'ordinateur : vocabulaire de téléphone | Corrigé : « Ajouter les photos » en galerie, « Retirer cette bouteille » (lot 10), option « 4G » masquée à la souris | lot 13 |
| 3 | T3-D20 | mineur | Cibles tactiles < 40 px | Corrigé : 44 px au toucher (navigation, Original, Autres actions, Historique, ↑/↓), cases de 28 px | lot 13 |
| 3 | T3-D21 | mineur | « Vérifier » à l'ordinateur : barre non alignée, 8 boutons | Corrigé : barre alignée sur les cartes ; « ✂ Couper » et « ✕ », noms complets en infobulle et pour les lecteurs d'écran | lot 13 |
| 3 | T3-D22 | mineur | Durée : seul le dernier lancement | Corrigé : « (dernier lancement : X) » | lot 13 |
| 3 | T3-D23 | mineur | Double clic « Lancer » : deux confirmations | Corrigé : un clic par seconde, bouton désactivé pendant l'envoi | lot 13 |
| 3 | T3-D24 | mineur | Configuration peu explicite | Corrigé : « Les colonnes de votre Excel, dans l'ordre » ; « toujours lue » au lieu de « noyau » ; « Identifiant » discret ; pas de description « pour le modèle » sur une liste de l'expert ; « Non déterminable est toujours proposé » | lot 13 |
| 3 | T3-DS1 | suggestion | Suivi titré « Analyse des photos » | Corrigé : titré du nom de la vente ; « Inventaires » dans l'en-tête | lot 14 |
| 3 | T3-DS2 | suggestion | Excel « inventaire_5.xlsx » ; position absente | Corrigé : « Vente — date.xlsx » (en-tête RFC 6266). Position dans l'Excel : écartée — les colonnes viennent de la configuration (contrainte 6) ; la maison peut y ajouter ce dont elle a besoin | lot 14 |
| 3 | T3-DS3 | suggestion | Bouteille signalée : Valider actif puis refusé | Corrigé : bouton désactivé avec la raison | lot 14 |
| 3 | T3-DS4 | suggestion | En-tête de colonne inerte | Corrigé : cliquable ; « Tout ouvrir / Tout fermer » | lot 14 |
| 3 | T3-DS5 | suggestion | Consignes : mots attendus par l'outil | Corrigé : une ligne sous le texte | lot 14 |
| 3 | T3-DS6 | suggestion | Fin de relecture : clore caché | Corrigé : « Clore l'inventaire » au récapitulatif | lot 14 |
| 3 | T3-DS7 | suggestion | Dépôt : ligne d'enchaînement ; « identiques » | « bouteilles identiques » corrigé. Ligne d'enchaînement écartée : l'utilisateur a demandé moins de texte (35c9ae0) | lot 14 |
| 3 | T3-DS8 | suggestion | Brouillons sans compte ; nom en double | Compte corrigé. Nom en double écarté : deux ventes peuvent porter le même nom, la date les distingue | lot 14 |
| 4 | T4-D1 | majeur | Après corbeille puis restauration, « Réanalyser » dans une impasse | Corrigé : une analyse finie n'est plus mise en pause par la corbeille ; la restauration la remet ; en pause sans rien à analyser, « Réanalyser » relance seul. En pause AVEC des bouteilles à analyser : toujours refusé (0147), message « Reprendre l'analyse » | lot 15 |
| 4 | T3-D5 / T4-B6 | majeur | Galerie : refus de photo absent de la carte | Corrigé (liste insérée dans la carte avant d'y chercher sa place) ; test navigateur | lot 15 |
| 4 | T4-D2 | mineur (régression) | « Raccourcis » réapparu au téléphone ; « ☐Seulement » | Corrigé | lot 15 |
| 4 | T4-D6 | mineur | Excel refusé affiché en vert | Corrigé : en jaune | lot 15 |
| 4 | T4-D11 | mineur | « Séparer » retire la validation sans le dire | Corrigé : « la bouteille d'origine est à revalider » | lot 15 |
| 4 | T3-D2 / T4-B11 | mineur | « (few-shot) » ; alerte sur toute citation des consignes | Corrigé : plus de jargon ; dans les consignes, seule une annonce d'exemple ou « réponds … « » » alerte ; test | lot 15 |
| 4 | T4-B1 | bloquant | Photo tronquée ou de plus de 179 Mpx : 500, boucle « Coupure », dépôt bloqué | Corrigé : refus en clair (« abîmée », « trop de pixels »), décodage vérifié à la réception ; côté écran, une erreur serveur qui n'est pas un passage (502–504) devient un refus au 3e essai, la photo n'est plus renvoyée ; test | lot 16 |
| 4 | T4-B2 | majeur | Double appui sur Valider : bouteille suivante validée sans être vue | Corrigé : une validation acceptée ferme la page aux suivantes ; un appui au bouton dans les 500 ms d'un affichage est ignoré (le clavier de l'expert, non) ; Entrée maintenue ignorée ; test navigateur | lot 16 |
| 4 | T4-B3 / T4-D12 | majeur | Retour arrière : page périmée, faux conflit | Corrigé : `Cache-Control: no-store` sur les écrans, rechargement si la page vient du cache ; test | lot 16 |
| 4 | T4-B4 | majeur | 404 affiché « Tout est enregistré » | Corrigé : « n'est plus disponible : rechargez la page », champ refusé, validation dite non faite | lot 16 |
| 4 | T4-B5 | majeur | Coupure réseau muette sur Vérifier et la configuration | Corrigé : « Connexion interrompue : l'action n'a pas été faite » | lot 16 |
| 4 | T4-B7 | mineur | Double appui : deux inventaires, faux « Action impossible » | Corrigé : un formulaire classique ne part qu'une fois ; test navigateur | lot 16 |
| 4 | T4-D5 | mineur | Vérifier : refus de quantité loin du champ | Corrigé : sous le champ, dans la carte ; test | lot 17 |
| 4 | T4-D10 | mineur | Vérifier : ✕ décalé | Corrigé : ✕ dans le coin de la photo, « ✂ Couper » aligné dessous | lot 17 |
| 4 | T4-B16 | mineur | Dernière photo retirée : bouteille supprimée sans prévenir | Corrigé : la confirmation le dit | lot 17 |
| 4 | T4-D14 (partie) | mineur | Vérifier vide dit trois fois la même chose ; dépôt vide « 0 photo(s) » ; « photo(s) » | Corrigé : un seul message ; « Aucune photo reçue pour l'instant » ; accord singulier / pluriel | lot 17 |
| 4 | T4-D8 | mineur | Galerie : ordre des photos faux | Corrigé : photos déjà reçues d'abord | lot 17 |
| 4 | T4-D9 / T4-B15 | mineur | Dépôt : gestes sans retour | Corrigé : pas de « Retirer » sur l'unique carte vide ; quantité 0 / abc refusée sous le champ ; photo choisie deux fois : « déjà dans la bouteille N » | lot 17 |
| 4 | T4-B8 | mineur | « 3 / 6 … 7 / 6 » après un retrait | Corrigé : place parmi les bouteilles présentes ; test | lot 18 |
| 4 | T4-B9 | mineur | Remise à relire : bouton « Déjà validée » | Corrigé : le bouton redevient « Valider » ; test | lot 18 |
| 4 | T4-D13 / T4-B23 | mineur | Collage coupé à 1 000 en silence | Corrigé : compteur au-delà de 900, collage coupé annoncé | lot 18 |
| 4 | T4-D3 | mineur | Téléphone, clavier : champ sous la photo | Corrigé : marge de défilement, vignettes masquées pendant la saisie | lot 18 |
| 4 | T4-D4 / T4-B24 | mineur | Téléphone : aucun champ au premier écran ; confirmation cachée | Corrigé : en-tête de relecture resserré (compteurs détaillés au récapitulatif) ; « Bouteille n°X validée » aussi dans l'indicateur du haut | lot 18 |
| 4 | T4-B17 | mineur | Durée allongée par la réanalyse d'une bouteille séparée | Corrigé : seules les bouteilles lues au lancement comptent | lot 18 |
| 4 | T4-B10 | mineur | Valeur en double : identifiant auto figé ; « code » | Corrigé : l'identifiant tiré du libellé suit le libellé ; « identifiant … en double : changez le libellé ou l'identifiant, ou retirez la ligne » ; test | lot 19 |
| 4 | T4-B12 | mineur | « Vérifier » décoche « Je confirme » | Corrigé ; test | lot 19 |
| 4 | T4-D7 | mineur | Aperçu périmé ; barre après erreur d'import | Corrigé : l'aperçu dit qu'il date tant qu'on n'a pas vérifié ; barre seulement s'il y a une modification refusée | lot 19 |
| 4 | T4-B22 / T4-DS5 (1re partie) | suggestion | Nouvelle colonne après « À vérifier » | Corrigé : insérée avant les colonnes calculées de fin ; test | lot 19 |
| 4 | T4-B25 | suggestion | « Importer » loin du choix du fichier | Corrigé : juste à côté. « Choose File » : texte du navigateur, en français dans un navigateur français | lot 19 |
| 4 | T4-D14 (import) | mineur | Nom de fichier répété ; deux deux-points | Corrigé | lot 19 |
| 4 | T4-B13 | mineur | Mot long : page élargie | Corrigé : coupé (titres, cartes, en-tête, messages, historique, tableaux) | lot 20 |
| 4 | T4-B14 | mineur | Numéro démesuré dans l'adresse : 500 | Corrigé : 404 en français ; test | lot 20 |
| 4 | T4-D16 / T4-B19 | mineur | Cibles de 22–25 px (en-tête, liens) ; bouton « − » | Corrigé : 44 px au toucher | lot 20 |
| 4 | T4-D15 | mineur | Mise en page : récapitulatif sans barre ; « Inventaires » deux fois ; clos : « Relire » | Corrigé : barre du bas au récapitulatif ; « Inventaires » dans l'en-tête seul ; « Consulter les bouteilles » si clos | lot 20 |
| 4 | T4-B20 | suggestion | Refus servis sur l'adresse du POST | Corrigé pour le renommage (retour au suivi, message) ; « Séparer » et l'import gardent leur page de refus (leurs messages dépendent de la saisie) | lot 20 |
| 4 | T4-D14 (signalements) | mineur | « Signalées : 1 » après levée | Corrigé : « Photos signalées : 1 (signalements levés compris) » | lot 20 |
| 4 | T4-B21 | suggestion | Une ligne d'aide sur « Vérifier » | Écarté : l'utilisateur a demandé de retirer ces lignes (0b54815) | — |
| 4 | T4-B18 | mineur | Excel : bouteille validée encore jaune / « À vérifier » | À trancher par l'utilisateur (choix n°8 de choix_a_trancher.md) : touche la règle d'export 0055 | — |
| 4 | T4-DS1 | suggestion | Glisser-déposer au bureau | Corrigé : photos glissées sur une carte de la galerie | lot 21 |
| 4 | T4-DS2 | suggestion | Focus sur « Nom de la vente » | Corrigé | lot 21 |
| 4 | T4-DS3 | suggestion | Bouteilles / exemplaires | Corrigé : au suivi et dans la confirmation du lancement ; test | lot 21 |
| 4 | T4-DS4 | suggestion | Millésime inhabituel | Corrigé : accepté, signalé « Inhabituel : 4 chiffres ou NM » ; test | lot 21 |
| 4 | T4-DS5 (2e partie) | suggestion | Version active, revenir à une version | Corrigé : « active » marquée ; « revenir à cette version » (nouvelle version, confirmée) ; test | lot 21 |
| 4 | T4-DS6 | suggestion | Relecture à l'ordinateur : vignettes coupées | Corrigé : photo moins haute | lot 21 |
| 4 | T4-B19 (ligne d'envoi) | mineur | Nom coupé sur la ligne de reprise | Corrigé | lot 21 |
| 5 | T5-R5 | réserve | Consignes recopiées à l'identique dites « modifiées » | Corrigé : identiques au texte d'origine (au blanc près) = pas de consignes propres, texte envoyé au caractère près ; test. Branche « sans listing » : test | lot 22 |
| 5 | T5-R9 | réserve | T4-B4, T4-B5, T4-DS1, T4-DS2 sans test | Corrigé : tests navigateur (404 en relecture, coupure sur Vérifier, glisser-déposer, curseur sur le nom), chacun vérifié en échec avant le correctif d'origine | lot 22 |
| 5 | T5-R8 | réserve | decisions.md sans ligne pour les lots 15 à 21 | Corrigé : 0175 à 0180 | 6a8c8a7 |
| 5 | T5-R1 / T5-R7 | réserve | Revérification globale ; statuts périmés | Corrigé : revérification id par id exigée (testeur-web.md, boucle-qualite.md) ; statuts à jour | 0cf18ea |
| 5 | T5-B4 | mineur | Quantité de plus de 4 300 chiffres : 500 | Corrigé : jamais convertie, refus en clair (Vérifier, lancement, relecture, Séparer), « ² » aussi ; configuration et JSON importé : refus en clair ; test | lot 22 |
| 5 | T5-B10 | mineur | Nom de vente sans limite côté serveur | Corrigé : 200 caractères au plus, caractères de contrôle remplacés (création, envoi par l'API, renommage) ; test | lot 22 |
| 5 | T5-B12 | mineur | Vérifier : refus de quantité qui redit le numéro, carte décalée | Corrigé : « Quantité invalide… » sous le champ, carte inchangée ; test | lot 22 |
| 5 | T5-B1 | majeur | Valider pendant une (ré)analyse : statut interne, bandeau faux, note inventée | Corrigé : « Valider » grisé avec sa raison (Ctrl+Entrée la dit) ; refus « le modèle ne l'a pas encore lue » ; bandeau « Analyse / Réanalyse en pause » ou « pas encore lancée » avec lien au suivi ; pas de « Note du modèle » sans lecture ; test | lot 23 |
| 5 | T5-B15 | suggestion | Fin de réanalyse muette | Corrigé : la page se recharge avec « Le modèle a lu la bouteille : relisez ses champs. » ; test | lot 23 |
| 5 | T5-B5 | mineur | Vérifier d'une vente lancée ou close : page vide | Corrigé : renvoi au suivi avec la raison (« Analyse déjà lancée », « Inventaire clos ») ; test | lot 23 |
| 5 | T5-B13 | suggestion | Appui ignoré 500 ms sans signe | Corrigé : bouton atténué pendant le délai | lot 23 |
| 5 | T5-B3 | majeur | Refus de configuration en jargon, plusieurs phrases pour une cause | Corrigé : mots de la page (types, sources, « Photos au plus par bouteille »), sans « contrat Bouteille », « noyau canonique » ni decisions.md ; un identifiant déjà pris = un seul refus, sur la nouvelle colonne ; test | lot 24 |
| 5 | T5-B2 | majeur | Avertissement permanent avec clé interne | Corrigé : « Sans la colonne « À vérifier »… » ; avertissements aussi sans quantité, sans « N° », sans colonne du noyau ; test | lot 24 |
| 5 | T5-B8 | mineur | Identifiant d'une nouvelle colonne figé au premier « Vérifier » | Corrigé : il suit le nom jusqu'à l'enregistrement ; test | lot 24 |
| 5 | T5-B9 | mineur | Import sans colonnes : onze phrases | Corrigé : « Aucune colonne », seul ; test | lot 24 |
| 5 | T5-B6 | mineur | Galerie : plusieurs cartes vides « Bouteille 4 » | Corrigé : « Ajouter une bouteille » montre la carte vide existante au lieu d'en créer une ; test navigateur | lot 25 |
| 5 | T5-B7 / T4-D9 | mineur | Galerie : « déjà dans la bouteille 1 » en bas seulement | Corrigé : aussi dans la carte visée ; test navigateur | lot 25 |
| 5 | T5-B14 | suggestion | Barre de progression pleine après la fin | Corrigé : masquée quand tout est envoyé ; test navigateur | lot 25 |
| 5 | T5-B11 | mineur | Deux onglets sur le même dépôt : photos fondues | Corrigé : chaque onglet le signale (« ouvert dans un autre onglet ») ; test navigateur | lot 25 |
| 5 | T4-D14 (reste) | mineur | « (s) » partout ; « 0 / 4 photo » | Corrigé : accords (filtre `accord`, fonction JS) au dépôt, Vérifier, suivi, accueil, récapitulatif, relecture, configuration ; « N / 4 photos » | lot 25 |
| 5 | T4-D10 | mineur (régression) | ✕ qui voile l'étiquette | Corrigé : pastille ronde de 32 px dans le coin, zone à toucher de 44 px | lot 26 |
| 5 | T5-D1 | mineur | Refus de quantité au téléphone : carte déformée, champ remis à l'ancienne valeur | Corrigé : saisie refusée gardée dans son champ ; guillemets insécables ; test | lot 26 |
| 5 | T5-D2 | mineur | Coupure réseau sur Vérifier : quantité non enregistrée sans le dire | Corrigé : « Pas enregistrée (connexion interrompue) » dans la carte ; test navigateur | lot 26 |
| 5 | T5-D3 | mineur | Bouteilles faites en galerie invisibles en mode appareil photo | Corrigé : listées aussi, « Reprendre » possible ; test navigateur | lot 26 |
| 5 | T5-DS1 | suggestion | Glisser-déposer : pas annoncé ; hors carte, la photo s'ouvre | Corrigé : astuce au bureau ; dépôt hors carte refusé en clair ; test navigateur | lot 26 |
| 5 | T4-D4 (reste) | mineur | Téléphone : aucun champ au premier écran | Corrigé : navigation sur une ligne (mots courts), photo à 26 % de l'écran, vignettes sur une rangée ; test navigateur | lot 27 |
| 5 | T5-D4 | mineur | Récapitulatif mal aligné, cases bleues, libellés sur 2 lignes, nom coupé, versions avec « · » orphelin | Corrigé : récapitulatif aligné à gauche, `accent-color`, libellés de barre sur une ligne, nom en « … », versions en ligne souple | lot 27 |
| 5 | T4-D14 (reste) | mineur | « Corrections : 0 sur 0 » ; « Son analyse s'arrête » même finie | Corrigé : « aucune » ; la corbeille ne le dit que si l'analyse tourne ; test | lot 27 |
| 5 | T5-DS2 | suggestion | Inventaire clos : l'Excel pas en action principale | Corrigé ; test | lot 27 |
| 5 | T5-D5 | mineur | Configuration : nouvelle colonne hors de vue ; aperçus refermés ; refus sans lien | Corrigé : le nom de la colonne ajoutée a le focus ; aperçus gardés ouverts ; chaque refus mène à sa colonne ; tests | lot 28 |
| 5 | T3-D2 (reste) | mineur | Alerte d'exemple loin des consignes | Corrigé : aussi sous les consignes ; test | lot 28 |
| 5 | T5-DS3 | suggestion | Version reprise sans origine | Corrigé : « (reprise de la version N) » ; test | lot 28 |
| 5 | Choix n° 7 (décision) | décision | Plusieurs configurations : la première par ordre alphabétique, en silence | Appliqué (option A, 0182) : aucune choisie sans `CAVE_SCAN_MAISON` ; bandeau rouge sur Configuration et Nouvel inventaire, création et import refusés, ligne de commande arrêtée avec la raison ; test | lot 29 |
| 5 | Choix n° 8 (décision) | décision | Bouteille validée encore surlignée dans l'Excel (T4-B18) | Appliqué (option A, 0183) : validée = jamais surlignée, « À vérifier » vide, case d'abstention vide ; la validation d'une bouteille au format ou millésime vide le dit sur la suivante, sans bloquer ; tests | lot 30 |
| 6 | T6-X1 | majeur | Avis de validation de la dernière bouteille perdu, puis affiché dans une autre vente | Corrigé : au récapitulatif (`?validee=`) ; l'avis rangé avec son inventaire n'est jamais affiché ailleurs ; test | lot 31 |
| 6 | T6-D1 | mineur (régression) | Libellés longs coupés au téléphone | Corrigé : ils passent à la ligne | lot 31 |
| 6 | T6-D2 / T6-B3 | mineur (régression) | ✕ en ellipse au téléphone | Corrigé : la règle « pleine largeur » exclut le ✕ | lot 31 |
| 6 | T6-D3 / T5-B12 | mineur | Refus de quantité qui réorganise la carte | Corrigé : sous l'en-tête de la carte ; « Pas enregistrée » aussi, avec « elle partira avec Lancer l'analyse » (T6-D10) | lot 31 |
| 6 | T6-D8 | mineur | Nom de vente coupé sans « … » au toucher | Corrigé : `inline-block` + marge pour les 44 px | lot 31 |
| 6 | T6-D7 | mineur | Récapitulatif collé à gauche | Corrigé : même colonne que les autres écrans | lot 31 |
| 6 | T6-B8 | mineur | Plusieurs configurations : l'API crée un inventaire | Écarté : l'appelant de l'API nomme la maison, c'est une désignation explicite (comme `--maison`) ; 0182 vise le cas sans désignation | — |
| 6 | T6-B1 | majeur | Téléphone : premier appui sur « Valider » perdu depuis un champ | Corrigé : au toucher, validation au relâchement du doigt (même garde), clic suivant ignoré ; vignettes effacées sans perdre leur place ; test navigateur tactile | lot 32 |
| 6 | T6-B2 | mineur | Refus de validation qui reste après correction | Corrigé : retiré dès qu'aucun champ n'est refusé ; test navigateur | lot 32 |
| 6 | T6-B4 | mineur | Barre de navigation plus haute sur la première / dernière bouteille | Corrigé : boutons inactifs avec mots courts ; test navigateur | lot 32 |
| 6 | T6-B5 | mineur | « Bouteille suivante » sans photo : sans effet visible | Corrigé : grisé, avec sa raison ; test navigateur | lot 32 |
| 6 | T6-B7 | mineur | « Leurs photos » pour 1 ; Ctrl+Entrée au téléphone ; « doute du modèle » sans lecture | Corrigé ; tests | lot 32 |
| 6 | T6-D4 / T6-B7 (d) | mineur | Dépôt : quantité refusée effacée, rangée cassée | Corrigé : saisie gardée, raison sous la rangée ; test navigateur | lot 32 |
| 6 | T6-B6 / T6-D6 / T6-R7 | mineur | « (s) » restants (Clore, Séparer, historique, refus, photos) | Corrigé : un seul accord (`src/textes.py`) pour les écrans et les messages des services ; la ligne de commande garde ses « (s) » (outil de développeur) | lot 33 |
| 6 | T6-D5 / T6-B10 (1re partie) | mineur | Clôture : succès en jaune, message en double | Corrigé : le bandeau seul ; le texte jaune reste pour le renvoi depuis le dépôt | lot 33 |
| 6 | T6-D9 | mineur | Guillemets séparés de leur mot | Corrigé : espaces insécables (suivi en pause, configuration) | lot 33 |
| 6 | T6-R4 | réserve | Choix n° 7 : import et mesurer_reduction.py sans test ; phrase maladroite | Corrigé : tests ; « En ligne de commande, --maison la désigne aussi. » Le nom du réglage reste dans le bandeau : seul l'installateur peut agir | lot 33 |
| 6 | T6-R5 | réserve | Choix n° 8 : pas de test de l'avis à l'écran ; test qui se saute en silence | Corrigé : le test tactile vérifie l'avis ; plus de saut silencieux | lot 33 |
| 6 | T6-D11 | mineur | Photo déjà reçue rechoisie après rechargement : vignette grise muette | Corrigé : dite dans sa carte, sans vignette | lot 34 |
| 6 | T6-D12 | mineur | Configuration : en-tête qui change selon l'état | Corrigé : même fil d'Ariane et sous-titre ; test | lot 34 |
| 6 | T6-S1 | suggestion | « ex. » | Corrigé : « Exemplaires à séparer » ; test | lot 34 |
| 6 | T6-S2 | suggestion | Motif après son bouton | Corrigé : avant ; test | lot 34 |
| 6 | T6-S3 | suggestion | Récapitulatif au téléphone sur deux colonnes étroites | Corrigé : libellé au-dessus de sa valeur | lot 34 |
| 6 | T6-S4 | suggestion | « bouteilles identiques » seul sur sa ligne | Corrigé : dans le libellé « Quantité (bouteilles identiques) » ; test | lot 34 |
| 6 | T6-B10 (2e partie) | suggestion | Clôture sans la liste des non validées | Corrigé : numéros listés (12 au plus) ; test | lot 35 |
| 6 | T6-B9 | suggestion | « Ajouter une valeur » sans focus | Corrigé : curseur dans le libellé de la nouvelle ligne ; test navigateur | lot 35 |
| 6 | T6-R1 | réserve | Ids en plusieurs lignes : une seule marque ; statut R1 périmé | Corrigé : règle « pire marque » dans le critère R1 ; statut mis à jour | 7263ca7 |
| 6 | T6-R2 | réserve | decisions.md sans ligne pour les lots 22 à 28 | Corrigé : 0185 à 0189, et 0189 bis pour le lot 28 (oubli relevé en T7-R2) | 7263ca7, tour 7 |
| 6 | T6-R3 | réserve | Historique sans le tour 5 | Corrigé | 7263ca7 |
| 6 | T6-R6 | réserve | 0171 non annoté ; README imprécis | Corrigé | 7263ca7 |
| 6 | T6-D10 | mineur | Vérifier : « réessayez » sans effet si la même quantité est retapée | Corrigé par le texte, pas par le comportement : « elle partira avec « Lancer l'analyse », ou réessayez » (rien n'est perdu : le lancement emporte la saisie) | lot 31 |
| 7 | T7-B1 / T7-D1 | mineur | « Bouteille n°X validée » dans une autre vente | Corrigé : rangée avec son inventaire ; test navigateur | lot 36 |
| 7 | T7-B2 / T7-D9 | mineur | Champ renvoyé après une validation tactile (409) | Corrigé : la validation partie emporte les champs, aucun envoi derrière elle ; test navigateur | lot 36 |
| 7 | T7-D4 | mineur | « Autres actions » / « Historique » sans ▶ au toucher | Corrigé | lot 36 |
| 7 | T7-D8 | mineur | Récapitulatif d'un inventaire clos : « reprendre la relecture » | Corrigé : « consulter les bouteilles » | lot 36 |
| 7 | T7-D10 | mineur | « Valider » flottant sur les derniers champs | Corrigé : bande pleine, marge de défilement | lot 36 |
| 7 | T7-R4 | réserve | Place des vignettes (T6-B1) sans test | Corrigé : le test tactile la mesure | lot 36 |
| 7 | T7-D2 | mineur (régression lot 34) | Dépôt : rangée « − champ + » cassée | Corrigé : libellé au-dessus, « − champ + » ensemble | lot 37 |
| 7 | T7-D3 | mineur | Quantité refusée n'empêche pas « Bouteille suivante » | Corrigé : passage arrêté, champ mis en vue | lot 37 |
| 7 | T7-S1 | suggestion | Raison de « Bouteille suivante » grisée invisible au toucher | Corrigé : dite sous le bouton | lot 37 |
| 7 | T7-B3 / T7-D5 | mineur | ✕ de 32 px au toucher | Corrigé : 40 px au toucher | lot 37 |
| 7 | T7-D6 | mineur | Bandeau de coupure qui reste ; contradiction avec la carte | Corrigé : la carte seule le dit ; bandeau retiré dès qu'une réponse arrive ; test adapté | lot 37 |
| 7 | T7-B4 | suggestion | « Quantité invalide («  ») » | Corrigé : « Quantité vide » ; test | lot 37 |
| 7 | T7-D7 | mineur | « 1 bouteille ajoutée… : les vérifier » | Corrigé : « la vérifier et lancer son analyse » | lot 38 |
| 7 | T7-D12 | mineur | Séparer : « 0 au plus » | Corrigé : « une seule bouteille, rien à séparer » ; test | lot 38 |
| 7 | T7-R5 | réserve | Guillemets à espaces ordinaires dans les scripts | Corrigé : une fonction par script met des insécables | lot 38 |
| 7 | T7-S3 | suggestion | « 1 à 10 » seul sous son libellé | Corrigé : dans le libellé | lot 38 |
| 7 | T7-D11 | mineur | Barre de configuration différente des autres | Corrigé : fixe en bas, pleine largeur | lot 38 |
| 7 | T7-S2 | suggestion | Galerie : curseur sur « Ajouter ses photos » | Écarté : le choix de fichier est un champ masqué derrière son libellé ; la carte est déjà mise en vue | — |
| 7 | T7-R1 | réserve | tour6.md : ids sans marque, pas de marque consolidée | Corrigé : ligne « Marque consolidée » dans tour7.md, ids écrits en entier (T8-R1) ; règle dans boucle-qualite.md | 005b909, tour 8 |
| 7 | T7-R2 | réserve | decisions.md : lot 28 sans ligne ; 0194 mal découpée | Corrigé : 0189 bis ; 0194 et 0191 réparées | 005b909 |
| 7 | T7-R3 | réserve | Ids du tour 6 sans ligne propre au journal | Corrigé : lignes T6-R1, R2, R3, R6, T6-D10 | 005b909 |
| 7 | T7-R6 | réserve | Critère R6 différent de 0184 | Corrigé : aligné sur 0184 | 005b909 |
| 8 | T8-R3 | suggestion | Dépôt : « Quantité invalide » pour une quantité vide (lecture du code) | Écarté : ce chemin reçoit un entier (formulaire typé), une saisie vide n'y arrive pas ; l'écran refuse la saisie vide avant l'envoi | — |
| 8 | T8-D1 | mineur (régression lot 36) | Puces sur les liens au toucher | Corrigé : `list-item` réservé aux volets ; test navigateur | lot 39 |
| 8 | T8-D2 | mineur | Champ atteint par Tab sous la bande « Valider » | Corrigé : marge de défilement sur la saisie ; test navigateur | lot 39 |
| 8 | T8-D3 | mineur (régression lot 38) | Barre de configuration sur le champ tapé | Corrigé : le champ remonte quand la barre apparaît | lot 39 |
| 8 | T8-D4 | mineur | h2 plus grands que le h1 | Corrigé | lot 39 |
| 8 | T8-B2 | mineur | Avertissement « autre onglet » qui reste | Corrigé : retiré à la fermeture ; test navigateur | lot 39 |
| 8 | T8-D5 | mineur | Renommage vide : volet refermé | Corrigé : volet ouvert, curseur dans le champ ; test | lot 39 |
| 8 | T8-B1 | mineur | Séparer refusé à l'adresse du POST | Écarté : déjà écarté en T4-B20, sans élément nouveau | — |
| 8 | T8-B3 | suggestion | Renommage trop long : page « Action impossible » | Corrigé : retour au suivi avec la raison, volet ouvert ; test | lot 40 |
| 8 | T8-D6 | mineur | 404 de relecture avec numéros internes | Corrigé : « Cette bouteille n'existe pas (ou plus) dans « vente » » ; test API adapté | lot 40 |
| 8 | T8-D7 | mineur | Dépôt d'un inventaire clos : message en double | Corrigé : le bandeau « clos » seul | lot 40 |
| 8 | T8-S1 | suggestion | Avertissement de clôture peu visible | Corrigé : encadré | lot 40 |
| 8 | T8-S2 | suggestion | Source choisie seule pour un champ toujours lu | Écarté : changerait en silence une source choisie par l'expert ; le refus dit quoi choisir | — |
| 8 | T8-R1 | réserve | Journal sans ligne pour T7-R1, R2, R3, R6 ; ids abrégés dans tour7.md | Corrigé : lignes ajoutées, ids écrits en entier | a3282b2 |
| 8 | T8-R2 | réserve | Statut R1 périmé | Corrigé ; critère R1 désormais exécutable (`docs/tests/verifier_r1.py`, T9-R3) | a3282b2, tour 9 |
| 9 | T9-B1 | suggestion | Appui sur « Valider » dans les 500 ms de garde ignoré sans rien dire | Écarté : le rejouer validerait la bouteille suivante sans l'avoir vue (T4-B2, 0176) ; le bouton atténué signale déjà la garde (T5-B13) | — |
| 9 | T9-D1 | mineur | Clore : encadré dans une puce, information trois fois | Corrigé : un encadré hors liste, avec les numéros ; test | lot 41 |
| 9 | T9-D3 | mineur | Compteurs : « sautée pour l'instant », saut de mise en page | Corrigé : « en cours d'analyse » (plus court) ; test | lot 41 |
| 9 | T9-D4 | mineur | Renommage refusé au téléphone : bouton sous la barre | Corrigé : formulaire mis en vue au-dessus de la barre | lot 41 |
| 9 | T9-D5 | mineur | Conflit : phrase coupée par les boutons | Corrigé : phrase d'abord, boutons dessous | lot 41 |
| 9 | T9-D9 | mineur | Aide des raccourcis : « ( Maj + Tab » | Corrigé | lot 41 |
| 9 | T9-D10 | mineur | Versions : interligne irrégulier | Corrigé : même hauteur | lot 41 |
| 9 | T9-D2 | mineur | Alerte d'exemple absente au refus « sans cocher », puis en double | Corrigé : dès le refus, une seule fois sous les consignes ; test | lot 42 |
| 9 | T9-D6 | mineur | Nom de colonne déjà pris dit en identifiants | Corrigé : « une colonne « X » existe déjà » ; test | lot 42 |
| 9 | T9-D7 | mineur | Résumé du dépôt sans les photos d'avant le rechargement | Corrigé : « N photos reçues en tout · M envoyées à l'instant » | lot 42 |
| 9 | T9-D8 | mineur | Configuration au téléphone : boutons renvoyés à la ligne | Corrigé : nom seul sur sa ligne, même forme pour toutes | lot 42 |
| 9 | T9-S1 | suggestion | Motif du signalement absent du bandeau | Corrigé | lot 42 |
| 9 | T9-S2 | suggestion | « Créer la configuration » en deux clics | Corrigé : un clic depuis Nouvel inventaire ; test adapté | lot 42 |
