/* Envoi des photos, une par une (guide de session 4 ; decisions.md 0127-0130).
 *
 * Du JavaScript simple, sans framework : le navigateur l'impose pour préparer
 * les photos et les envoyer fichier par fichier. Aucun garde-fou ici : le
 * serveur décide de tout (image lisible, HEIC, doublon, taille) et ce script
 * affiche sa réponse. Il ne fait que :
 *   1. lire la date de prise de vue dans l'EXIF de l'ORIGINAL, avant toute
 *      réduction (la réduction l'efface) ;
 *   2. réduire la photo si l'option est cochée ;
 *   3. demander au serveur ce qu'il a déjà reçu, puis envoyer le reste, au plus
 *      3 à la fois, en réessayant après une coupure ;
 *   4. garder l'écran allumé et reprendre au retour sur la page.
 */
(function () {
  "use strict";

  var racine = document.querySelector("[data-depot]");
  if (!racine) return;
  var inventaire = racine.dataset.inventaire;
  var tailleCible = parseInt(racine.dataset.taille, 10) || 2500;
  var dejaAuServeur = parseInt(racine.dataset.deja, 10) || 0;
  var SIMULTANES = 3;

  var caseReduire = document.getElementById("reduire");
  var liste = document.getElementById("envois");
  var resumeTexte = document.getElementById("resume-texte");
  var barre = document.getElementById("barre");
  var garderOuvert = document.getElementById("garder-ouvert");
  var versOrdre = document.getElementById("vers-ordre");

  var file = [];       // { fichier, signature, etat, message, essais, ligne }
  var actifs = 0;
  var verrouEcran = null;

  function api(chemin) { return "/inventaires/" + inventaire + chemin; }

  // --- choisir des photos --------------------------------------------------------------------

  ["galerie", "camera"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", function (evenement) {
      ajouter(Array.prototype.slice.call(evenement.target.files));
      evenement.target.value = "";  // pouvoir reprendre la même photo
    });
  });

  function ajouter(fichiers) {
    var nouveaux = [];
    fichiers.forEach(function (fichier) {
      var signature = fichier.name + "|" + fichier.size + "|" + fichier.lastModified;
      if (file.some(function (envoi) { return envoi.signature === signature; })) return;
      var envoi = { fichier: fichier, signature: signature, etat: "attente", message: "En attente", essais: 0 };
      envoi.ligne = creerLigne(envoi);
      file.push(envoi);
      nouveaux.push(envoi);
    });
    if (!nouveaux.length) return;
    // Reprise après une coupure : ce que le serveur a déjà ne repart pas.
    fetch(api("/photos/deja-recues"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ signatures: nouveaux.map(function (e) { return e.signature; }) }),
    })
      .then(function (reponse) { return reponse.ok ? reponse.json() : { deja_recues: [] }; })
      .then(function (corps) {
        nouveaux.forEach(function (envoi) {
          if (corps.deja_recues.indexOf(envoi.signature) >= 0) marquer(envoi, "deja", "Déjà reçue");
        });
      })
      .catch(function () { /* hors ligne : le serveur dédoublonnera de toute façon */ })
      .then(pomper);
  }

  // --- la file d'envoi -----------------------------------------------------------------------

  function pomper() {
    if (!navigator.onLine) {
      afficherResume("Connexion perdue : l'envoi reprendra tout seul dès son retour.");
      return;
    }
    while (actifs < SIMULTANES) {
      var suivant = file.find(function (envoi) { return envoi.etat === "attente"; });
      if (!suivant) break;
      envoyer(suivant);
    }
    afficherResume();
  }

  function envoyer(envoi) {
    actifs += 1;
    marquer(envoi, "actif", "Préparation…");
    garderEcranAllume();
    preparer(envoi.fichier)
      .then(function (prete) {
        marquer(envoi, "actif", "Envoi…");
        var donnees = new FormData();
        donnees.append("fichier", prete.contenu, prete.nom);
        if (prete.date) donnees.append("prise_de_vue", prete.date);
        donnees.append("signature", envoi.signature);
        return fetch(api("/photos"), { method: "POST", body: donnees });
      })
      .then(function (reponse) {
        if (reponse.ok) {
          return reponse.json().then(function (corps) {
            if (corps.deja_recue) marquer(envoi, "deja", "Déjà reçue");
            else marquer(envoi, "ok", "Envoyée");
          });
        }
        if (reponse.status >= 400 && reponse.status < 500) {
          // Refusée par le serveur : la raison est affichée, jamais ignorée.
          return reponse.json()
            .catch(function () { return { message: "Refusée par le serveur." }; })
            .then(function (corps) { marquer(envoi, "refusee", corps.message || "Refusée par le serveur."); });
        }
        throw new Error("serveur " + reponse.status);
      })
      .catch(function () { reessayerPlusTard(envoi); })
      .then(function () {
        actifs -= 1;
        pomper();
      });
  }

  function reessayerPlusTard(envoi) {
    envoi.essais += 1;
    var delai = Math.min(30, Math.pow(2, envoi.essais));
    marquer(envoi, "reessai", "Coupure — nouvel essai dans " + delai + " s");
    setTimeout(function () {
      if (envoi.etat === "reessai") { envoi.etat = "attente"; pomper(); }
    }, delai * 1000);
  }

  window.addEventListener("online", pomper);
  window.addEventListener("offline", function () { afficherResume(); });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") return;
    // Retour sur la page : les envois suspendus repartent tout de suite.
    file.forEach(function (envoi) { if (envoi.etat === "reessai") envoi.etat = "attente"; });
    pomper();
  });
  window.addEventListener("beforeunload", function (evenement) {
    if (enCours()) { evenement.preventDefault(); evenement.returnValue = ""; }
  });

  // --- préparer une photo --------------------------------------------------------------------

  function preparer(fichier) {
    // La date AVANT toute réduction : la réduction efface l'EXIF (0129).
    return lireDate(fichier).then(function (date) {
      if (!caseReduire.checked) return { contenu: fichier, nom: fichier.name, date: date };
      return reduire(fichier)
        .then(function (reduit) {
          if (!reduit) return { contenu: fichier, nom: fichier.name, date: date };
          return { contenu: reduit, nom: fichier.name.replace(/\.[^.]*$/, "") + ".jpg", date: date };
        })
        .catch(function () { return { contenu: fichier, nom: fichier.name, date: date }; });
    });
  }

  function reduire(fichier) {
    if (!window.createImageBitmap) return Promise.resolve(null);
    return createImageBitmap(fichier, { imageOrientation: "from-image" }).then(function (image) {
      var echelle = Math.min(1, tailleCible / Math.max(image.width, image.height));
      if (echelle >= 1) return null;  // déjà assez petite : l'original part tel quel
      var toile = document.createElement("canvas");
      toile.width = Math.round(image.width * echelle);
      toile.height = Math.round(image.height * echelle);
      toile.getContext("2d").drawImage(image, 0, 0, toile.width, toile.height);
      return new Promise(function (ok) { toile.toBlob(ok, "image/jpeg", 0.9); });
    });
  }

  // Date de prise de vue dans l'EXIF d'un JPEG : DateTimeOriginal, sinon DateTime.
  function lireDate(fichier) {
    return fichier.slice(0, 256 * 1024).arrayBuffer().then(function (tampon) {
      try {
        var vue = new DataView(tampon);
        if (vue.getUint16(0) !== 0xFFD8) return null;  // pas un JPEG
        var position = 2;
        while (position + 10 <= vue.byteLength) {
          var marqueur = vue.getUint16(position);
          if ((marqueur & 0xFF00) !== 0xFF00 || marqueur === 0xFFDA) return null;
          if (marqueur === 0xFFE1 && vue.getUint32(position + 4) === 0x45786966) {  // « Exif »
            return dateTiff(vue, position + 10);
          }
          position += 2 + vue.getUint16(position + 2);
        }
      } catch (e) { /* EXIF tronqué ou illisible : pas de date */ }
      return null;
    }).catch(function () { return null; });
  }

  function dateTiff(vue, debut) {
    var petit = vue.getUint16(debut) === 0x4949;  // « II » : petit-boutiste
    function u16(o) { return vue.getUint16(debut + o, petit); }
    function u32(o) { return vue.getUint32(debut + o, petit); }
    function lireIfd(decalage) {
      var entrees = {};
      var nombre = u16(decalage);
      for (var i = 0; i < nombre; i += 1) {
        var e = decalage + 2 + i * 12;
        entrees[u16(e)] = { type: u16(e + 2), compte: u32(e + 4), valeur: e + 8 };
      }
      return entrees;
    }
    function texte(entree) {
      if (!entree || entree.type !== 2) return null;
      var ou = entree.compte > 4 ? u32(entree.valeur) : entree.valeur;
      var s = "";
      for (var i = 0; i < entree.compte - 1; i += 1) s += String.fromCharCode(vue.getUint8(debut + ou + i));
      return s;
    }
    var ifd0 = lireIfd(u32(4));
    var brute = null;
    if (ifd0[0x8769]) brute = texte(lireIfd(u32(ifd0[0x8769].valeur))[0x9003]);
    brute = brute || texte(ifd0[0x0132]);
    var m = brute && brute.match(/^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
    return m ? m[1] + "-" + m[2] + "-" + m[3] + "T" + m[4] + ":" + m[5] + ":" + m[6] : null;
  }

  // --- garder l'écran allumé -------------------------------------------------------------------

  function garderEcranAllume() {
    garderOuvert.hidden = false;
    if (verrouEcran || !("wakeLock" in navigator)) return;  // indisponible hors HTTPS : le message suffit
    navigator.wakeLock.request("screen").then(function (verrou) {
      verrouEcran = verrou;
      verrou.addEventListener("release", function () { verrouEcran = null; });
    }).catch(function () {});
  }

  // --- affichage -------------------------------------------------------------------------------

  function creerLigne(envoi) {
    var ligne = document.createElement("li");
    ligne.className = "envoi attente";
    var nom = document.createElement("span");
    nom.className = "envoi-nom";
    nom.textContent = envoi.fichier.name;
    var etat = document.createElement("span");
    etat.className = "envoi-etat";
    etat.textContent = "En attente";
    ligne.appendChild(nom);
    ligne.appendChild(etat);
    liste.insertBefore(ligne, liste.firstChild);
    return ligne;
  }

  function marquer(envoi, etat, message) {
    envoi.etat = etat;
    envoi.message = message;
    envoi.ligne.className = "envoi " + etat;
    envoi.ligne.querySelector(".envoi-etat").textContent = message;
    envoi.ligne.dataset.etat = etat;
    afficherResume();
  }

  function enCours() {
    return file.some(function (envoi) { return ["attente", "actif", "reessai"].indexOf(envoi.etat) >= 0; });
  }

  function compter(etat) {
    return file.filter(function (envoi) { return envoi.etat === etat; }).length;
  }

  function afficherResume(message) {
    var total = file.length;
    var termines = compter("ok") + compter("deja") + compter("refusee");
    var parties = [];
    if (compter("ok")) parties.push(compter("ok") + " envoyée(s)");
    if (compter("deja")) parties.push(compter("deja") + " déjà reçue(s)");
    if (compter("refusee")) parties.push(compter("refusee") + " refusée(s) — voir la raison");
    if (total - termines) parties.push((total - termines) + " en cours");
    resumeTexte.textContent = message || (total
      ? parties.join(" · ")
      : dejaAuServeur + " photo(s) déjà reçue(s) pour cet inventaire.");
    barre.hidden = !total;
    barre.max = total || 1;
    barre.value = termines;

    var occupe = enCours();
    versOrdre.classList.toggle("inactif", occupe);
    versOrdre.setAttribute("aria-disabled", occupe ? "true" : "false");
    racine.dataset.etat = occupe ? "envoi" : "repos";
    if (!occupe) {
      garderOuvert.hidden = true;
      if (verrouEcran) { verrouEcran.release().catch(function () {}); verrouEcran = null; }
    }
  }

  versOrdre.addEventListener("click", function (evenement) {
    if (enCours()) {
      evenement.preventDefault();
      afficherResume("Attendez la fin de l'envoi avant de vérifier l'ordre.");
    }
  });
})();
