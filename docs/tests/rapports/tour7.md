# Tour 7 — rapports des testeurs (2026-10-14)

## Vérificateur (Sonnet)

R1 ⚠️ · R2 ✅ · R2b ✅ · R3 ✅ · R4 ✅ · R5 ✅ · R6 ✅

- HEAD b5c8d6a : 726 passed (dépôt, copie `config/maisons/` vide, copie avec
  colonne renommée) ; dry-run OK ; totaux des commits des lots 31 à 35 égaux
  aux tests collectés ; 25 lignes « Corrigé » du tour 6 confirmées dans le code ;
  mutation de T6-B1 (handler retiré + `display:none`) : le test échoue.
- R6 : `main` en avance rapide uniquement, aucune fusion, aucun push.
- **T7-R1** — tour6.md : T4-D9 et T5-R1/R5/R7/R8/R9 sans marque ; pas de marque
  consolidée par id ; statut R1 périmé.
- **T7-R2** — decisions.md : pas de ligne pour le lot 28 ; 0194 contient deux
  phrases du lot 32.
- **T7-R3** — Journal : T6-R1, R2, R3, R6, T6-D10 sans ligne propre.
- **T7-R4** — T6-B1 : le correctif CSS (place des vignettes gardée) n'est pas
  protégé par le test (le handler `pointerup` suffit à le faire passer).
- **T7-R5** — Guillemets « » à espaces ordinaires écrits après T6-D9
  (base.html « Pas enregistrée… », relecture.js, depot.js).
- **T7-R6** — Critère R6 (« dernier tour sans majeur ») différent de 0184
  (« à la fin de chaque tour corrigé »).
