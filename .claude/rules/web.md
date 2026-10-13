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
- Une bouteille = un groupe de photos (plafond réglé par maison). Envoi des
  photos fichier par fichier, reprise après coupure ; chaque bouteille et
  l'ordre de ses photos visibles et corrigeables avant le lancement.
- Relecture : chaque modification est enregistrée immédiatement et l'état
  « enregistré / erreur » est visible ; pas de validation en masse, et valider
  une bouteille reste facultatif. « Clore l'inventaire » avertit de ce qui n'est
  pas validé ; ensuite l'inventaire est en lecture seule.
- Photos affichées uniquement par la route qui vérifie leur inventaire (jamais
  de dossier statique), toujours sans métadonnées EXIF (position GPS de la cave
  du client).
- Relecture : les doutes du modèle (`champs_a_verifier`) sont mis en évidence ;
  une abstention s'affiche « à remplir », jamais comme une valeur. Raccourcis à
  une lettre désactivés pendant la saisie dans un champ.
- Textes courts, orientés action ; chaque état visible (en cours, enregistré,
  refusé avec la raison).
- Une instance de l'application = une maison : aucune page ne nomme ni ne fait
  choisir la maison (decisions.md 0171).
