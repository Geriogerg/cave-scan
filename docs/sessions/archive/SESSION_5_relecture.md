# Session 5 — Écran de relecture

Objectif : l'écran où l'expert passe le plus de temps et où il jugera l'outil.
Pour chaque bouteille, il voit les deux photos et les champs extraits, corrige
ce qui doit l'être, valide, et passe à la suivante. Sur 300 bouteilles, chaque
seconde et chaque clic comptent.

Prérequis : session 4 terminée.

---

## 0. Allègement du contexte (première étape de la session)

Le `CLAUDE.md` est devenu trop long : tout était chargé à chaque session, même
les règles sans rapport avec le travail en cours. Nouvelle organisation :

- `CLAUDE.md` court : produit, contraintes dures, architecture, règles de
  session. Toujours chargé.
- `.claude/rules/` : un fichier par domaine (`extraction.md`, `donnees.md`,
  `api-worker.md`, `web.md`). Chacun commence par une liste `paths` et ne se
  charge que lorsque Claude Code travaille sur les fichiers concernés.
- `decisions.md` : consulté par section quand un choix s'y rapporte, plus lu en
  entier.
- Les guides des sessions passées sont déplacés dans `docs/sessions/archive/`.

À faire :
1. Remplacer `CLAUDE.md`, créer `.claude/rules/` avec les quatre fichiers.
2. **Adapter les `paths`** de chaque fichier de règles aux vrais dossiers du repo
   (ceux fournis sont des suppositions). Une règle dont les chemins ne
   correspondent à rien ne se charge jamais.
3. Vérifier que rien d'important de l'ancien `CLAUDE.md` n'a été perdu.
4. Compacter `decisions.md` : les décisions remplacées partent dans
   `docs/decisions-archive.md` avec un renvoi ; le fichier principal ne garde que
   les décisions en vigueur.

---

## 1. Le parcours

1. Depuis le suivi d'un inventaire (ou dès qu'une partie des bouteilles est
   extraite), l'expert ouvre la relecture.
2. Il arrive sur la première bouteille non validée.
3. Il vérifie, corrige, valide : la bouteille suivante s'affiche.
4. Une barre indique la progression (validées / total) et le nombre restant à
   vérifier.
5. Quand toutes les bouteilles sont validées, un récapitulatif s'affiche
   (bouteilles, corrections, champs les plus corrigés) avec l'export Excel.

La relecture peut commencer pendant que l'extraction continue : les bouteilles
pas encore extraites sont simplement sautées et signalées.

---

## 2. L'écran

Pensé pour un ordinateur, grand écran.

**À gauche, les photos**
- étiquette et contre-étiquette côte à côte, ou l'une en grand avec bascule ;
- zoom et déplacement dans la photo (molette, glisser), et ouverture de
  l'original en pleine résolution : un millésime en petits caractères doit pouvoir
  se vérifier ;
- les photos de la bouteille suivante sont préchargées.

**À droite, les champs**, dans l'ordre de la config de la maison :
- valeur courante, modifiable (liste déroulante pour les listes, avec recherche
  au clavier ; champ texte ; nombre pour la quantité) ;
- indication de l'origine de la valeur : lue, déduite, proposée (best effort),
  corrigée par l'expert, saisie par l'expert ;
- champs à vérifier mis en évidence ;
- « non déterminable » affiché clairement comme « à remplir », pas comme une
  valeur ;
- valeur d'origine du modèle visible au survol d'un champ corrigé, et possibilité
  de revenir à cette valeur ;
- les champs saisis par l'expert (quantité, estimation) sont dans le même
  formulaire.

**En haut** : nom de l'inventaire, position (« 47 / 300 »), progression,
navigation précédente / suivante, filtre « seulement les bouteilles avec des
champs à vérifier ».

---

## 3. Le clavier

L'expert doit pouvoir relire sans toucher la souris :

- **Entrée** (hors champ texte) ou **Ctrl+Entrée** (partout) : valider et passer
  à la suivante ;
- **flèches gauche / droite** ou **J / K** : bouteille précédente / suivante ;
- **Tab** : champ suivant ;
- **Z** : zoom sur la photo ; **E** : basculer étiquette / contre-étiquette ;
- **?** : afficher l'aide des raccourcis.

Les raccourcis à une lettre sont désactivés pendant la saisie dans un champ.

---

## 4. L'enregistrement

- **Chaque modification est enregistrée immédiatement** (à la sortie du champ ou
  au choix dans une liste), en passant par la fonction de correction existante.
  Pas de bouton « Enregistrer » à ne pas oublier.
- Un indicateur montre l'état : « enregistré » ou « erreur, nouvel essai ». Une
  correction non enregistrée bloque le passage à la bouteille suivante avec un
  message clair.
- Si la bouteille a été modifiée ailleurs depuis son ouverture (autre onglet), un
  avertissement s'affiche avant d'écraser ; l'historique garde de toute façon
  toutes les corrections.
- Modifier une bouteille déjà validée la remet à relire (règle existante),
  l'écran le signale.

---

## 5. Les cas particuliers

- **Bouteille en erreur d'extraction** : la raison est affichée, avec deux
  options : « Réanalyser » ou saisir les champs à la main. La saisie manuelle
  passe par les corrections ; aucune valeur inventée par l'outil.
- **Réanalyser une bouteille** : relance l'extraction pour cette bouteille
  seulement. La précédente est conservée (immuable) ; les corrections déjà faites
  restent prioritaires sur la nouvelle extraction.
- **Étiquette et contre-étiquette inversées** : bouton « Inverser les photos »,
  puis proposition de réanalyser.
- **Photos qui ne vont pas ensemble** (décalage après le lancement) : bouton
  « Signaler un problème de paire », qui marque la bouteille et l'empêche d'être
  validée. La réparation des paires après lancement est hors périmètre.
- **Bouteilles identiques d'état différent** (5 bonnes + 1 abîmée) : action
  « Séparer » qui crée une seconde bouteille avec les mêmes photos et une
  quantité donnée, que l'expert ajuste ensuite (état, description). La somme des
  quantités est conservée.

---

## 6. Ce qu'on mesure

Pour le protocole du pilote (session 8), sans effort supplémentaire de l'expert :

- temps passé sur chaque bouteille (de l'ouverture à la validation, en ignorant
  les absences longues) ;
- nombre de corrections par bouteille et par champ ;
- bouteilles réanalysées, séparées, signalées.

Ces chiffres apparaissent dans les statistiques de l'inventaire et dans le
récapitulatif.

---

## 7. Hors périmètre

- Validation en masse : chaque bouteille est vue par l'expert.
- Réparation des paires après lancement.
- Rédaction automatique des descriptions de catalogue (session 6).
- Connexion et gestion des utilisateurs (session 7) : l'auteur des corrections
  reste celui configuré par défaut.
- Estimation par comparables.

---

## 8. Critères d'acceptation

**Contexte**
- `CLAUDE.md` fait moins de 80 lignes ; les quatre fichiers de règles existent,
  leurs `paths` correspondent à des fichiers réels du repo ; `decisions.md` ne
  garde que les décisions en vigueur.

**Tests automatisés (hors ligne, extracteur factice)**
- Une modification est enregistrée sans action supplémentaire et apparaît dans
  l'historique ; l'extraction d'origine est inchangée.
- Revenir à la valeur du modèle crée une correction, ne supprime rien.
- Une valeur hors liste ou une quantité invalide est refusée avec un message
  clair, et la bouteille ne peut pas être validée tant qu'elle n'est pas
  corrigée.
- Modifier une bouteille validée la remet à relire.
- Réanalyser conserve l'ancienne extraction et les corrections restent
  prioritaires.
- Séparer crée une seconde bouteille liée aux mêmes photos, quantités cohérentes,
  et l'export produit deux lignes.
- Une bouteille signalée « problème de paire » ne peut pas être validée.
- Le temps de relecture est enregistré à la validation.
- L'avertissement de modification concurrente se déclenche.
- L'export reflète toutes les corrections.
- Tous les tests précédents restent verts ; `--dry-run` fonctionne.

**Test de navigation (navigateur automatisé, écran d'ordinateur)**
- Relire 10 bouteilles uniquement au clavier : corriger un champ liste, un champ
  texte, la quantité, valider, naviguer ; vérifier l'export.

**Rapidité**
- Passage d'une bouteille à la suivante perçu comme immédiat (photos
  préchargées) sur un inventaire de 300 bouteilles.

---

## 9. Ce qu'il faut surveiller

- **Un bouton « Enregistrer »** à la place de l'enregistrement immédiat.
- **Une correction qui écrase l'extraction** au lieu de s'ajouter à l'historique.
- **Des raccourcis qui se déclenchent pendant la saisie** dans un champ.
- **Une validation en masse** glissée « pour gagner du temps ».
- **Des `paths` de règles qui ne correspondent à rien** dans le repo.

---

## 10. Validation finale (toi)

1. Tests verts.
2. Relire un inventaire réel de 30 bouteilles au clavier ; chronométrer.
3. Ouvrir deux onglets sur la même bouteille, modifier dans les deux : vérifier
   l'avertissement et l'historique.
4. Séparer une bouteille, réanalyser une autre, signaler une paire : vérifier
   l'export.
5. Faire relire 20 bouteilles à ton frère sans explication ; noter ses
   hésitations et son temps moyen par bouteille. Comparer à son temps de saisie
   manuelle habituel : c'est le premier chiffre du gain réel.
6. Commit final.

Prochaine session : export final et rédaction des descriptions de catalogue.
