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
