# ROADMAP — stratégie et feuille de route

> Claude Code n'a PAS besoin de lire ce fichier pour coder. Il garde la trace
> de la stratégie et de la séquence des sessions, pour nous deux. On ne construit
> que ce que le guide de la session en cours demande.

## Positionnement

- B2B d'abord : le mur d'entrée est l'accès aux maisons et aux données annotées,
  pas la technique. Cycle lent mais compatible side project.
- Grand public plus tard, comme canal d'acquisition (modèle iDealwine), pas comme
  business, et seulement une fois la notation d'état bonne.
- Wedge = extraction/lotting (se vend, douleur quotidienne). Moat = notation
  d'état (nous rend durs à copier). On entre par le wedge, on greffe le moat.
- Livraison manuelle assistée avant toute automatisation.

## Les 3 briques

1. Identification (étiquette → référence). Se rattache au LWIN (Liv-ex), pas à un
   référentiel maison.
2. Valorisation (prix conditionnel à l'état). Problème de données, jamais produit
   depuis une photo. Après la v1.
3. Notation d'état (niveau, étiquette, capsule, bouchon). Best-effort en v1,
   fiabilisée ensuite. Niveau = candling requis ; bouchon quasi invisible.

## Feuille de route vers le pilote

Une session Claude Code = un guide dans `docs/sessions/`, écrit au moment de la
faire, à partir de l'état réel du code.

- [x] v0 : extraction VLM + export + comparaison au listing manuel (résultats
      concluants sur données réelles).
- [x] Session 1 : config par maison (JSON versionné, codes stables + libellés,
      sources modele / best effort / expert / système), une ligne = une bouteille,
      appariement des photos par ordre.
- [x] Session 2 : bibliothèque + base de données (extraction immuable,
      corrections séparées, config figée par inventaire, coût par bouteille).
- [ ] Session 3 : tâches de fond (file d'attente en base, worker, extraction en
      parallèle, reprise après arrêt) + API JSON (FastAPI). En cours.
- [ ] Session 4 : application web, écran de dépôt des photos (utilisable sur
      téléphone).
- [ ] Session 5 : écran de relecture (pièce maîtresse : paire de photos +
      champs, incertitudes surlignées, correction en un clic, clavier).
- [ ] Session 6 : export depuis les données validées + rédaction des
      descriptions dans le style de la maison.
- [ ] Session 7 : connexion, hébergement UE, RGPD, sauvegardes, journal
      d'erreurs. Vérifier les conditions de traitement des données de l'API.
- [ ] Session 8 : protocole du pilote (temps par lot avant/après, taux de
      corrections, champs les plus corrigés).

Choix techniques prévus pour l'application : FastAPI + pages HTML côté serveur
(HTMX), SQLite puis PostgreSQL, photos sur disque puis stockage objet en Europe,
worker simple pour les tâches de fond.

## Après le pilote (ou en parallèle quand les données arrivent)

- Normalisation + rattachement LWIN, écrits à partir des corrections réelles de
  l'expert enregistrées en base (pas au jugé).
- Few-shot seulement pour le flou de convention irréductible, exemples réels hors
  du set d'éval. Fine-tuning au frigo.
- Estimation par comparables : clé LWIN + millésime + format, fourchette avec
  ventes sourcées et datées. Source à choisir (historique de la maison pilote,
  cotes publiques, API payantes). Jamais depuis la photo.
- Lotting automatique, mode hors ligne dans l'application, éditeur de config dans
  l'interface, intégration aux logiciels métier (e-auction, Exeve).

## Concurrence

- Start (appstart.fr) : généraliste photo → fiche de lot pour commissaires-
  priseurs, clients sérieux (Millon, Ader, Giquello...), 79 à 199 € HT/mois.
  Valide le marché et la volonté de payer. Notre angle : la profondeur vin
  (LWIN, millésime, format, état, comparables), là où un généraliste reste en
  surface.

## Pièges stratégiques

- Estimation par la photo : jamais.
- « Apprend tout seul » vendu à un client : non, c'est un template de config.
- Authentification : jamais « certifié » ; détection d'anomalie avec expert.
- Pas de client en production tant qu'on ne peut pas assurer support/correctifs.
- Pilotes gratuits : en échange du droit de garder la donnée annotée, avec une
  date où l'on pose la question du prix.

## Signal qui compte

Pour la v1 : une maison pilote qui renvoie une DEUXIÈME consignation sans qu'on
la relance. Pas le chiffre d'affaires.