---
paths:
  - "src/api/**"
  - "src/worker.py"
  - "worker.py"
  - "serveur.py"
  - "dev.py"
  - "src/services/file_attente.py"
  - "src/services/pilotage.py"
  - "src/services/debit.py"
  - "src/services/envoi.py"
---

# Règles : API et tâches de fond

- Route = valider l'entrée, appeler un service, mettre en forme la réponse.
- File d'attente en base ; aucun état en mémoire. Une bouteille « en cours »
  abandonnée après un arrêt brutal est remise à extraire.
- Réservation atomique : une bouteille n'est jamais extraite deux fois en même
  temps. Parallélisme borné et configurable, limites de débit respectées.
- Erreurs : systématique → arrêt de l'inventaire ; passagère → nouvelles
  tentatives avec délai croissant puis erreur sur la bouteille ; réponse
  inexploitable → erreur sur la bouteille.
- Photos servies uniquement par une route qui vérifie l'inventaire ; jamais de
  dossier statique ; jamais de métadonnées EXIF dans les réponses.
- Serveur en local par défaut ; écoute réseau local seulement via une option de
  développement explicite, avec avertissement.
- Format d'erreur unique : code, message en français, détail éventuel.
