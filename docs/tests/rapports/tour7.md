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

## Testeur bugs (Sonnet, relancé après une limite de session)

0 bloquant, 0 majeur, 3 mineurs, 1 suggestion. Écrans ≈ 75 ms (le plus lent :
configuration au téléphone, 261 ms) ; aucun 500, aucune erreur JavaScript hors
4xx attendus ; aucun défilement horizontal ; Excel conforme (validées jamais
surlignées). P3 et P8 non refaits en entier.

### Points du tour précédent

- [T6-X1] ✅ (reste voisin : T7-B1) · [T6-B1] ✅ (effet de bord : T7-B2)
- [T6-D1] ✅ · [T6-D2 / T6-B3] ❌ en partie (pastille de 32 px : T7-B3)
- [T6-D3] ✅ · [T6-D8] ✅ · [T6-D7] ✅ · [T6-B2] ✅ · [T6-B4] ✅ · [T6-B5] ✅
- [T6-B7] ✅ · [T6-D4] ✅ · [T6-B6 / T6-D6 / T6-R7] ✅ · [T6-D5 / T6-B10] ✅
- [T6-R4] ✅ · non retestés : T6-R5, T6-D9, T6-D10, T6-D11, T6-D12, T6-S1 à S4,
  T6-B9, T6-R1, T6-R2, T6-R3, T6-R6

### Nouveaux points

- **T7-B1** mineur — « Bouteille n°N validée. » affiché dans une autre vente
  (la position rangée en sessionStorage n'est pas liée à son inventaire ni
  effacée au récapitulatif).
- **T7-B2** mineur — Au téléphone, valider depuis un champ modifié envoie
  ensuite le champ seul : 409 inutile en console (aucune perte).
- **T7-B3** mineur — ✕ de Vérifier mesuré 32×32 px au téléphone.
- **T7-B4** suggestion — Quantité vide : « Quantité invalide («  ») ».

## Testeur design (Opus, relancé après une limite de session)

0 bloquant, 0 majeur, 12 mineurs, 3 suggestions. Écrans ≈ 66 ms (le plus lent :
relecture au téléphone, 136 ms) ; valider et passer 170 à 234 ms ; aucun 500,
aucune erreur JavaScript, aucun défilement horizontal.

### Points du tour précédent

- [T6-X1] ❌ (reste : T7-D1) · [T6-D1] ✅ · [T6-D2] ✅ (taille : T7-D5) · [T6-B3] ✅
- [T6-D3] ✅ · [T5-B12] ✅ · [T6-D4] ❌ (rangée cassée : T7-D2) · [T6-D5] ✅
- [T6-D6] ❌ (reste : T7-D7) · [T6-D7] ✅ · [T6-D8] ✅ · [T6-D9] ✅ · [T6-D10] ✅
- [T6-D11] ✅ · [T6-D12] ✅ · [T6-S1] ✅ · [T6-S2] ✅ · [T6-S3] ✅
- [T6-S4] ❌ (régression : T7-D2) · [T6-B1] ✅ (effet de bord : T7-D9)
- [T6-B2] ✅ · [T6-B4] ✅ · [T6-B5] ✅ (raison invisible au toucher : T7-S1)
- [T6-B7] ✅ · [T6-B9] ✅ · [T6-B10] ✅ · [Choix n° 7] ✅ · [Choix n° 8] ✅

### Marque consolidée (pire des deux testeurs)

T6-X1 ❌ · T6-D2/B3 ❌ en partie (taille) · T6-D4 ❌ · T6-D6/B6 ❌ en partie ·
T6-S4 ❌ · T6-B1 ✅ (effet de bord à corriger) · tous les autres ids vus : ✅.
Réserves documentaires : [T6-R1] non retestable · [T6-R2] non retestable ·
[T6-R3] non retestable · [T6-R5] non retestable · [T6-R6] non retestable (par
l'écran ; vérifiés par le vérificateur dans le code et les tests). T6-B7 : ✅, sauf sa partie (d),
liée à T6-D4 ❌ (pire marque : ❌ en partie).

### Nouveaux points

- **T7-D1** mineur — « Bouteille n°X validée. » dans une autre vente (= T7-B1).
- **T7-D2** mineur (régression lot 34) — Dépôt au téléphone : rangée « − champ + »
  cassée en permanence.
- **T7-D3** mineur — Dépôt : une quantité refusée n'empêche pas « Bouteille
  suivante », et le refus reste affiché sur la suivante.
- **T7-D4** mineur — Relecture au téléphone : « Autres actions » et « Historique »
  sans ▶ (inline-flex).
- **T7-D5** mineur — ✕ de Vérifier à 32×32 px au téléphone (= T7-B3).
- **T7-D6** mineur — Vérifier : bandeau « Connexion interrompue » qui reste après
  un réessai réussi.
- **T7-D7** mineur — Suivi : « 1 bouteille ajoutée… : les vérifier et lancer leur
  analyse ».
- **T7-D8** mineur — Récapitulatif d'un inventaire clos : « reprendre la
  relecture » au lieu de « consulter ».
- **T7-D9** mineur — Au téléphone, champ renvoyé après la validation : 409 (= T7-B2).
- **T7-D10** mineur — Relecture à l'ordinateur : « Valider » flottant couvre la
  dernière rangée de champs.
- **T7-D11** mineur — Configuration : barre « Annuler / Vérifier / Enregistrer »
  différente des autres barres.
- **T7-D12** mineur — Séparer : « on peut en séparer 0 au plus ».
- **T7-S1** suggestion — Raison de « Bouteille suivante » grisée invisible au toucher.
- **T7-S2** suggestion — Galerie : focus sur « Ajouter ses photos » de la nouvelle carte.
- **T7-S3** suggestion — Configuration au téléphone : « (1 à 10) » dans le libellé.
