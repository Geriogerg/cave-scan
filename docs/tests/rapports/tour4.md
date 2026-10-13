# Tour 4 — rapports (2026-10-13)

Trois passages : **bugs** (Sonnet, T4-B…), **design** (Opus, T4-D…),
**vérificateur** (Sonnet, T4-R…). Sections ajoutées à réception.

## Testeur design (Opus)

0 bloquant, 2 majeurs, 16 mineurs, 6 suggestions. Écrans ≈ 106 ms en moyenne
(relecture 465 ms au pire), aucune erreur JavaScript, aucun 500, aucun
défilement horizontal.

Points du tour 3 : tous ✅, sauf T3-D5 ❌ (galerie : le refus n'est pas dans
la carte — `afficherVignettes` appelé avant l'insertion de la liste dans la
carte) et T3-D2 ❌ en partie (« (few-shot) », fausse alerte sur toute citation
nouvelle). Régression du lot 13 : T4-D2.

- **T4-D1** MAJEUR — Après corbeille puis restauration, « Réanalyser » est
  refusé (« analyse annulée : relancez-la depuis le suivi ») et le suivi n'a
  aucun bouton de relance : impasse ; le mot « annulée » ; page laissée sur
  l'adresse POST.
- **T3-D5** MAJEUR (reste) — Galerie : photo refusée pour le plafond absente de
  la carte.
- **T4-D2** Régression — Au téléphone, « Raccourcis » réapparaît (la règle
  tactile du lot 13 l'emporte sur `[data-aide]{display:none}`) ; « ☐Seulement ».
- **T4-D3** Téléphone, clavier ouvert : le champ passe sous la photo collée.
- **T4-D4** Relecture au téléphone : aucun champ visible à l'ouverture ;
  « Bouteille n°X validée » caché sous « Valider ».
- **T4-D5** Vérifier : quantité refusée loin du champ, valeur remise en silence.
- **T4-D6** « L'Excel n'est pas encore disponible » en vert.
- **T3-D2** (reste) — « (few-shot) » ; fausse alerte sur toute citation ;
  alerte loin des consignes.
- **T4-D7** Aperçu « Ce que reçoit le modèle » périmé avant « Vérifier » ;
  barre « Enregistrer » affichée après une erreur d'import.
- **T4-D8** Galerie : ordre des photos dans la carte faux.
- **T4-D9** Dépôt : « Retirer » sur l'unique carte vide sans effet visible ;
  quantité « 0 »/« abc » remise à 1 en silence.
- **T4-D10** Vérifier : ✕ décalé, cartes hautes, « Couper » sans explication au
  toucher.
- **T4-D11** « Séparer » retire la validation sans le dire.
- **T4-D12** Retour arrière après validation : page en cache, paraît non validée.
- **T4-D13** Collage de plus de 1 000 caractères coupé en silence.
- **T4-D14** Textes : nom de fichier en double dans un refus d'import, deux
  deux-points ; « Vérifier » vide dit trois fois la même chose ; dépôt vide
  « 0 photo(s) … » ; « photo » / « photo(s) » ; « Signalées : 1 » après levée.
- **T4-D15** Mise en page : récapitulatif sans barre du bas ; suivi au
  téléphone avec 2 rangées et « Inventaires » en double ; inventaire clos :
  « Relire les bouteilles ».
- **T4-D16** Cibles < 44 px : lien d'en-tête, liens de la confirmation et de la
  configuration, bouton « − ».
- **T4-DS1** Glisser-déposer au bureau.
- **T4-DS2** Focus sur « Nom de la vente ».
- **T4-DS3** Bouteilles et exemplaires distingués.
- **T4-DS4** Millésime : avertissement doux hors 4 chiffres / NM.
- **T4-DS5** Configuration : nouvelle colonne avant « À vérifier » ; version
  active marquée, « Revenir à cette version ».
- **T4-DS6** Relecture à l'ordinateur : vignettes et aide coupées en bas.

Avis P12 : choix 1 à 6 GARDER (5 : acceptable depuis l'en-tête
« Inventaires ») ; choix 7 MODIFIER (bascule silencieuse retestée).

## Testeur bugs (Sonnet)

1 bloquant, 5 majeurs, 13 mineurs, 7 suggestions. Pages 41 à 370 ms
(« Vérifier » 150 bouteilles), relecture ≈ 230 ms entre bouteilles, Excel de
150 bouteilles 1,2 s ; aucune erreur JavaScript hors coupure réseau.

Points du tour 3 : tous ✅ sauf T3-D5 ❌ en galerie (= T4-B6), T3-D2 ⚠️
(« (few-shot) », clé `"domaine"` = T4-B11), T3-D16 ❌ sur la ligne de reprise,
T3-D20 ⚠️ (liens d'en-tête 25 px).

- **T4-B1** BLOQUANT — Photo tronquée ou de plus de 179 Mpx : 500
  (`DecompressionBombError`, `image file is truncated`) ; l'écran boucle sur
  « Coupure — nouvel essai » ; après rechargement la photo repart d'IndexedDB ;
  aucun moyen de la retirer ; « Vérifier et lancer » bloqué.
- **T4-B2** MAJEUR — Double appui sur « Valider » (200–350 ms) ou Entrée
  répétée : la bouteille suivante est validée sans avoir été vue (bouton
  réactivé avant le chargement de la page suivante).
- **T4-B3** MAJEUR — Retour arrière après validation : page périmée (pas de
  `Cache-Control`), puis faux « modifiée ailleurs » contre sa propre
  validation ; même chose sur « Vérifier » après « Lancer ».
- **T4-B4** MAJEUR — Relecture : une réponse 404 (inventaire mis à la corbeille
  ailleurs) affiche « Tout est enregistré » ; Valider muet ; saisie perdue en
  silence (contrainte 5).
- **T4-B5** MAJEUR — Coupure réseau sur « Vérifier » et la configuration : aucun
  message (`htmx:sendError` non traité).
- **T4-B6** MAJEUR — = T3-D5 (galerie : refus absent de la carte).
- **T4-B7** Double appui au téléphone : deux inventaires créés ; « Action
  impossible » après une réouverture ou une mise à la corbeille réussies.
- **T4-B8** Après un retrait : « 3 / 6 … 7 / 6 ».
- **T4-B9** Bouteille validée puis corrigée : le bouton garde « Déjà validée ».
- **T4-B10** Valeur de liste en double : l'identifiant auto figé ne suit pas le
  libellé corrigé ; « code » au lieu d'« Identifiant » ; refus loin de la ligne.
- **T4-B11** = T3-D2 (« (few-shot) », clé `"domaine"`).
- **T4-B12** « Vérifier » décoche « Je confirme modifier les consignes ».
- **T4-B13** Un mot long sans espace élargit la page (accueil, suivi,
  historique).
- **T4-B14** Identifiant de plus de 19 chiffres dans l'adresse : 500.
- **T4-B15** Dépôt : photo déjà choisie ignorée sans un mot ; quantité 0/abc/-3
  remise à 1 sans message.
- **T4-B16** Retirer la dernière photo d'une bouteille la supprime sans prévenir.
- **T4-B17** « dernier lancement : 27 s » après réanalyse d'une bouteille
  séparée.
- **T4-B18** Excel : une bouteille validée reste jaune avec « À vérifier »
  (champ lu laissé `non_lisible`) ; impossible de dire « rien à lire ».
  À trancher avec decisions.md 0055.
- **T4-B19** Cibles de l'en-tête 25 px ; ligne d'envoi en reprise coupée.
- **T4-B20** Refus servis sur l'adresse du POST (F5 renvoie le formulaire).
- **T4-B21** « Vérifier » : « ✂ Couper » / « Rattacher » expliqués seulement en
  infobulle.
- **T4-B22** Nouvelles colonnes après « À vérifier ».
- **T4-B23** = T4-D13 (collage coupé à 1 000 en silence).
- **T4-B25** Import : bouton « Importer » loin du sélecteur ; « Choose File »
  natif.

Avis P12 : choix 1 à 6 aident ; choix 7 : « sans danger pour un pilote à une
maison, mais silencieux » — refus de démarrer, ou nom du fichier actif affiché.
