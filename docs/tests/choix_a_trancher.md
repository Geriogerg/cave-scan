# Choix à trancher par l'utilisateur (recommandation R4)

Choix faits pendant la boucle sans validation de l'utilisateur. (Les
textes d'aide réduits ne sont pas un choix de la boucle : c'est une demande de
l'utilisateur ; le parcours P12 vérifie seulement qu'ils restent compréhensibles.) L'avis du
testeur design (parcours P12) est reporté à chaque tour ; la décision de
l'utilisateur est notée ici quand elle est prise. La boucle ne tranche pas.

| # | Choix | Où | Avis du testeur (P12, tours 3 et 4) | Recommandation | Décision |
|---|---|---|---|---|---|
| 1 | Quantité plafonnée à 100 000 | dépôt, vérifier, relecture | Aide : jamais atteint en usage normal ; mais au dépôt la saisie n'est pas contrôlée et c'est la photo qui est refusée (T3-D8) | GARDER 100 000 ; contrôler dès la saisie au dépôt, ne jamais refuser une photo pour la quantité, champ assez large | ⏳ |
| 2 | Texte libre limité à 1 000 caractères | relecture | Aide : une description fait 50 à 300 caractères ; le refus arrive après coup et cite une clé interne (T3-D3) | GARDER 1 000 ; `maxlength`, compteur au-delà de 800, nom de la colonne dans le message | ⏳ |
| 3 | Photo collée en haut (30 % de l'écran) pendant la saisie au téléphone | relecture | Aide nettement (lire l'étiquette en tapant) ; avec le clavier, la photo prend 51 % et certains champs passent sous « Valider » | GARDER ; masquer les vignettes pendant la saisie, marge basse égale à « Valider », corriger T3-D13 | ⏳ |
| 4 | Colonnes de la configuration repliées | configuration | Aide : 2 800 px au lieu de 10 000, « ✎ Modifier » trouvé par le débutant ; en-tête non cliquable | GARDER ; en-tête cliquable, « Tout ouvrir » | ⏳ |
| 5 | Barre « Annuler / Vérifier / Enregistrer » masquée tant que rien n'est modifié | configuration | Plutôt une aide ; mais au chargement, ni action ni retour aux inventaires (T3-D11) Tour 4 : acceptable depuis « Inventaires › Configuration » dans l'en-tête ; la barre apparaît à tort après une erreur d'import (T4-D7). | GARDER (avis du tour 4), en corrigeant T4-D7 | ⏳ |
| 6 | Dépôt ouvert en mode « Galerie » à l'ordinateur | dépôt | Aide : pas d'appareil photo au bureau ; mais titre « Photographier » et bouteilles d'un autre appareil invisibles en galerie | GARDER ; titre « Ajouter les photos », bouteilles reçues en cartes | ⏳ |
| 7 | S'il y a plusieurs configurations dans `config/maisons/` et pas de `CAVE_SCAN_MAISON` : la première par ordre alphabétique | configuration | Gêne : un ancien fichier déposé à côté fait basculer la configuration EN SILENCE (testé : 16 colonnes au lieu de 9) Tour 4 : retesté, même bascule silencieuse (9 → 16 colonnes). | MODIFIER : ne pas choisir ; bandeau rouge « Plusieurs configurations trouvées » sur Configuration et Nouvel inventaire | ⏳ |
| 8 | Excel : une bouteille VALIDÉE par l'expert reste surlignée en jaune, avec « À vérifier » (doutes du modèle), si un champ lu est resté « non lisible » (T4-B18) | export | Testeur bugs : l'expert ne peut pas dire « rien à lire ici » ; la ligne reste à relire après validation Tour 5 (design) : MODIFIER — « validée » doit vouloir dire « relue » ; en échange, prévenir à la validation si Format ou Millésime est vide. | Ne plus surligner une bouteille validée ; renommer « À vérifier » en « Doutes du modèle » pour une bouteille validée — change la règle 0055 (« non lisible = case vide + ligne surlignée ») | ⏳ |
