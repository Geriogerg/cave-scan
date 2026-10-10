---
paths:
  - "src/web/**"
  - "src/services/depot.py"
  - "src/services/consultation.py"
  - "src/services/relecture.py"
---

# Règles : écrans web

- Pages générées côté serveur + HTMX, dans la même application que l'API.
  JavaScript simple seulement où le navigateur l'impose.
- Garde-fous toujours vérifiés côté serveur, même s'ils sont aussi affichés dans
  le navigateur. Aucune logique métier dans les gabarits ni dans le JavaScript.
- Dépôt pensé pour le téléphone (une main, gros boutons, réseau instable) ;
  relecture pensée pour l'ordinateur (clavier, grand écran).
- Envoi des photos fichier par fichier, reprise après coupure ; date de prise de
  vue lue avant toute réduction ; ordre des paires visible et corrigeable avant
  le lancement.
- Relecture : chaque modification est enregistrée immédiatement et l'état
  « enregistré / erreur » est visible ; pas de validation en masse, chaque
  bouteille est vue par l'expert. « Valider l'inventaire » ne fait que
  constater que toutes les bouteilles ont été validées une par une.
- Photos affichées uniquement par la route qui vérifie leur inventaire (jamais
  de dossier statique), toujours sans métadonnées EXIF (position GPS de la cave
  du client).
- Relecture : les doutes du modèle (`champs_a_verifier`) sont mis en évidence ;
  une abstention s'affiche « à remplir », jamais comme une valeur. Raccourcis à
  une lettre désactivés pendant la saisie dans un champ.
- Textes courts, orientés action ; chaque état visible (en cours, enregistré,
  refusé avec la raison).
