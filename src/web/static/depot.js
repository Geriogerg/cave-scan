/* Dépôt des photos, bouteille par bouteille (guides des sessions 4 et 6 ;
 * decisions.md 0127, 0130, 0166, 0167).
 *
 * Du JavaScript simple, sans framework : le navigateur l'impose pour prendre et
 * envoyer des photos une par une. Aucun garde-fou ici : le serveur décide de
 * tout (image lisible, plafond de photos, bouteille déjà analysée, doublon) et
 * ce script affiche sa réponse. Il ne fait que :
 *   1. rattacher chaque photo à SA bouteille : la bouteille en cours (mode
 *      appareil photo) ou une carte « Bouteille N » (mode galerie) ; chaque
 *      bouteille a une clé, donnée ici, et un numéro dans l'ordre de prise de vue ;
 *   2. garder dans le navigateur (IndexedDB) les photos prises depuis la page
 *      jusqu'à ce que le serveur les ait reçues : elles n'existent nulle part
 *      ailleurs. La bouteille en cours survit à un rechargement ;
 *   3. envoyer, au plus 3 à la fois, en réessayant après une coupure, et
 *      demander d'abord au serveur ce qu'il a déjà reçu ;
 *   4. garder l'écran allumé et reprendre au retour sur la page.
 */
(function () {
  "use strict";

  var racine = document.querySelector("[data-depot]");
  if (!racine) return;
  var inventaire = racine.dataset.inventaire;
  var maximum = parseInt(racine.dataset.max, 10) || 4;
  var prochainServeur = parseInt(racine.dataset.prochain, 10) || 1;
  var dejaFormees = parseInt(racine.dataset.formees, 10) || 0;
  var attenteServeur = lireJson(racine.dataset.attente);  // clé -> { photos: identifiants reçus, numero }
  var tailleCible = parseInt(racine.dataset.taille, 10) || 2500;
  var SIMULTANES = 3;
  var CLE_ETAT = "cave-scan-depot-" + inventaire;

  var caseReduire = document.getElementById("reduire");
  var liste = document.getElementById("envois");
  var resumeTexte = document.getElementById("resume-texte");
  var resumeInitial = resumeTexte.textContent;
  var barre = document.getElementById("barre");
  var garderOuvert = document.getElementById("garder-ouvert");
  var memoireIndisponible = document.getElementById("memoire-indisponible");
  var autreOnglet = document.getElementById("autre-onglet");
  var versVerification = document.getElementById("vers-verification");

  var file = [];       // les envois : { bouteille, fichier, nom, signature, etat, message, essais, ligne, idb }
  var avisDeLaPage = {};  // clé de bouteille -> dernier avis (photo déjà choisie), montré dans sa carte
  var actifs = 0;
  var verrouEcran = null;

  function api(chemin) { return "/inventaires/" + inventaire + chemin; }
  // « 1 photo », « 3 photos » : pas de « photo(s) » (T4-D14). Zéro s'accorde au singulier.
  function accord(nombre, singulier, pluriel) { return nombre + " " + (nombre > 1 ? pluriel : singulier); }
  function lireJson(texte) { try { return JSON.parse(texte || "{}") || {}; } catch (e) { return {}; } }

  // --- l'état du dépôt : la bouteille en cours, les cartes de la galerie ----------------------------

  var etat = lireEtat();

  // Deux onglets du même navigateur partagent l'état du dépôt : leurs photos
  // iraient dans les mêmes bouteilles. Chacun le dit (T5-B11).
  try {
    var canal = new BroadcastChannel(CLE_ETAT);
    canal.onmessage = function (evenement) {
      if (evenement.data === "ouvert") canal.postMessage("deja-ouvert");
      autreOnglet.hidden = false;
    };
    canal.postMessage("ouvert");
  } catch (e) { /* navigateur sans BroadcastChannel : rien à signaler */ }

  function lireEtat() {
    var lu = null;
    try { lu = JSON.parse(localStorage.getItem(CLE_ETAT)); } catch (e) { /* stockage refusé */ }
    lu = lu || {};
    return {
      // Premier passage : la galerie à l'ordinateur (souris), l'appareil photo au téléphone (T2-DS1).
      mode: lu.mode ? (lu.mode === "galerie" ? "galerie" : "appareil")
        : (window.matchMedia && matchMedia("(pointer: fine)").matches ? "galerie" : "appareil"),
      enCours: lu.enCours || null,
      precedentes: lu.precedentes || [],
      galerie: lu.galerie || [],
      prochain: Math.max(lu.prochain || 1, prochainServeur),
    };
  }

  function sauver() {
    try { localStorage.setItem(CLE_ETAT, JSON.stringify(etat)); } catch (e) { /* stockage refusé : la page reste utilisable */ }
  }

  function nouvelleCle() {
    var aleatoire = window.crypto && crypto.randomUUID ? crypto.randomUUID()
      : Date.now().toString(36) + Math.random().toString(36).slice(2);
    return aleatoire.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
  }

  function nouvelleBouteille() {
    var bouteille = { cle: nouvelleCle(), numero: etat.prochain, quantite: 1, recues: 0, quantiteAEnvoyer: false };
    etat.prochain += 1;
    return bouteille;
  }

  function toutes() {
    return (etat.enCours ? [etat.enCours] : []).concat(etat.precedentes, etat.galerie);
  }

  function enAttenteLocale(bouteille) {
    return file.filter(function (envoi) {
      return envoi.bouteille.cle === bouteille.cle && ["attente", "actif", "reessai"].indexOf(envoi.etat) >= 0;
    }).length;
  }

  function nombrePhotos(bouteille) { return bouteille.recues + enAttenteLocale(bouteille); }

  // Le numéro AFFICHÉ, celui que donnera l'écran « Vérifier » : les bouteilles
  // déjà dans l'inventaire, puis celles qui ont des photos, dans l'ordre. Une
  // bouteille encore vide (celle de l'appareil photo, en mode galerie) ne
  // prend pas de numéro aux autres (rapport du testeur, T1-m4).
  function rang(bouteille) {
    var vide = nombrePhotos(bouteille) === 0;  // vide : elle viendra après toutes les autres (T2-6)
    var avant = toutes().filter(function (b) {
      return b !== bouteille && nombrePhotos(b) > 0 && (vide || b.numero < bouteille.numero);
    }).length;
    return dejaFormees + avant + 1;
  }

  // Au chargement : le serveur dit ce qu'il a déjà. Une bouteille qu'il n'attend
  // plus (lancée, ou supprimée à la vérification) et sans envoi en cours est
  // terminée : la page passe à une nouvelle.
  function reconcilier() {
    function encoreAttendue(bouteille) {
      if (Object.prototype.hasOwnProperty.call(attenteServeur, bouteille.cle)) {
        bouteille.miniatures = attenteServeur[bouteille.cle].photos;
        bouteille.recues = bouteille.miniatures.length;
        // La quantité du serveur fait foi, sauf un changement fait ici et pas
        // encore envoyé (T3-D1 : jamais « 1 » écrasant la vraie quantité).
        if (!bouteille.quantiteAEnvoyer) bouteille.quantite = attenteServeur[bouteille.cle].quantite || 1;
        return true;
      }
      if (enAttenteLocale(bouteille)) return true;
      if (bouteille.recues > 0) return false;  // reçue puis lancée ou supprimée
      bouteille.recues = 0;
      return true;  // pas encore de photo : elle attend la première
    }
    // Les bouteilles en attente reçues d'un autre appareil (ou d'un autre
    // navigateur) : elles sont listées, numérotées, et comptées (T2-D1).
    Object.keys(attenteServeur).forEach(function (cle) {
      if (toutes().some(function (b) { return b.cle === cle; })) return;
      etat.precedentes.push({ cle: cle, numero: attenteServeur[cle].numero, quantite: attenteServeur[cle].quantite || 1,
                              recues: 0, quantiteAEnvoyer: false });
    });
    etat.precedentes.sort(function (a, b) { return a.numero - b.numero; });
    if (etat.enCours && !encoreAttendue(etat.enCours)) etat.enCours = null;
    etat.precedentes = etat.precedentes.filter(encoreAttendue);
    etat.galerie = etat.galerie.filter(encoreAttendue);
    if (!etat.enCours) etat.enCours = nouvelleBouteille();
    sauver();
  }

  // --- garder les photos prises dans le navigateur (IndexedDB) -------------------------------------

  var base = ouvrirBase();

  function ouvrirBase() {
    return new Promise(function (ok, ko) {
      if (!window.indexedDB) { ko(new Error("indisponible")); return; }
      var demande = indexedDB.open("cave-scan-depot", 1);
      demande.onupgradeneeded = function () {
        var magasin = demande.result.createObjectStore("photos", { keyPath: "id", autoIncrement: true });
        magasin.createIndex("inventaire", "inventaire");
      };
      demande.onsuccess = function () { ok(demande.result); };
      demande.onerror = function () { ko(demande.error); };
    });
  }

  function transaction(mode, faire) {
    return base.then(function (bd) {
      return new Promise(function (ok, ko) {
        var t = bd.transaction("photos", mode);
        var resultat = faire(t.objectStore("photos"));
        t.oncomplete = function () { ok(resultat && resultat.result); };
        t.onerror = function () { ko(t.error); };
        t.onabort = function () { ko(t.error); };
      });
    });
  }

  function garder(envoi) {
    return transaction("readwrite", function (magasin) {
      return magasin.add({
        inventaire: inventaire, cle: envoi.bouteille.cle, numero: envoi.bouteille.numero,
        nom: envoi.nom, signature: envoi.signature, fichier: envoi.fichier,
      });
    }).then(function (id) { envoi.idb = id; })
      .catch(function () { memoireIndisponible.hidden = false; });
  }

  function oublier(envoi) {
    if (envoi.idb == null) return;
    var id = envoi.idb;
    envoi.idb = null;
    transaction("readwrite", function (magasin) { return magasin.delete(id); }).catch(function () {});
  }

  function photosGardees() {
    return transaction("readonly", function (magasin) {
      return magasin.index("inventaire").getAll(inventaire);
    }).catch(function () { return []; });
  }

  // --- mode appareil photo -----------------------------------------------------------------------

  var titreEnCours = document.getElementById("titre-en-cours");
  var compteur = document.getElementById("compteur");
  var vignettesEnCours = document.getElementById("vignettes-en-cours");
  var boutonPhoto = document.getElementById("bouton-photo");
  var camera = document.getElementById("camera");
  var champQuantite = document.getElementById("quantite");
  var precedentes = document.getElementById("precedentes");

  camera.addEventListener("change", function (evenement) {
    var fichiers = Array.prototype.slice.call(evenement.target.files);
    evenement.target.value = "";
    fichiers.forEach(function (fichier) { ajouter(etat.enCours, fichier, true); });
  });

  document.querySelectorAll("[data-quantite]").forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      changerQuantite(etat.enCours, (etat.enCours.quantite || 1) + parseInt(bouton.dataset.quantite, 10));
    });
  });
  champQuantite.addEventListener("change", function () {
    changerQuantite(etat.enCours, parseInt(champQuantite.value, 10), champQuantite);
  });

  document.getElementById("suivante").addEventListener("click", function () {
    if (!nombrePhotos(etat.enCours)) {
      afficherResume("Prenez au moins une photo de cette bouteille avant de passer à la suivante.");
      return;
    }
    etat.precedentes.unshift(etat.enCours);
    etat.enCours = nouvelleBouteille();
    sauver();
    afficherAppareil();
  });

  function reprendre(bouteille) {
    etat.precedentes = etat.precedentes.filter(function (b) { return b !== bouteille; });
    etat.galerie = etat.galerie.filter(function (b) { return b !== bouteille; });
    if (nombrePhotos(etat.enCours)) etat.precedentes.unshift(etat.enCours);
    else etat.prochain = Math.max(etat.prochain - 1, etat.enCours.numero);  // numéro jamais utilisé : rendu
    etat.enCours = bouteille;
    sauver();
    afficherAppareil();
  }

  function afficherAppareil() {
    var bouteille = etat.enCours;
    var nombre = nombrePhotos(bouteille);
    titreEnCours.textContent = "Bouteille " + rang(bouteille);
    compteur.textContent = nombre + " / " + accord(maximum, "photo", "photos");
    champQuantite.value = bouteille.quantite;
    var plein = nombre >= maximum;
    boutonPhoto.classList.toggle("inactif", plein);
    boutonPhoto.textContent = plein ? "Plafond de " + maximum + " photos atteint" : "Prendre une photo";
    camera.disabled = plein;
    afficherVignettes(vignettesEnCours, bouteille);

    precedentes.textContent = "";
    // Les bouteilles faites en galerie aussi : un mode ne cache pas l'autre (T5-D3).
    var galerieFaite = etat.galerie.filter(function (b) { return nombrePhotos(b) > 0; });
    etat.precedentes.concat(galerieFaite).sort(function (a, b) { return a.numero - b.numero; }).forEach(function (b) {
      var ligne = document.createElement("li");
      ligne.className = "precedente";
      var texte = document.createElement("span");
      var enCours = enAttenteLocale(b);
      texte.textContent = "Bouteille " + rang(b) + " · " + accord(nombrePhotos(b), "photo", "photos")
        + (b.quantite > 1 ? " · × " + b.quantite : "") + (enCours ? " · envoi en cours" : " · reçue");
      var bouton = document.createElement("button");
      bouton.type = "button";
      bouton.className = "lien";
      bouton.textContent = "Reprendre";
      bouton.addEventListener("click", function () { reprendre(b); });
      ligne.appendChild(texte);
      ligne.appendChild(bouton);
      precedentes.appendChild(ligne);
    });
  }

  // --- mode galerie ou ordinateur -----------------------------------------------------------------

  var cartes = document.getElementById("bouteilles-galerie");

  // Une photo lâchée à côté d'une carte : le navigateur l'ouvrirait à la place de la
  // page ; on le dit au lieu de quitter le dépôt (T5-DS1).
  document.addEventListener("dragover", function (evenement) { evenement.preventDefault(); });
  document.addEventListener("drop", function (evenement) {
    evenement.preventDefault();
    if (!evenement.target.closest || !evenement.target.closest(".carte-galerie")) {
      afficherResume("Déposez les photos sur la carte d'une bouteille.");
    }
  });

  document.getElementById("ajouter-bouteille").addEventListener("click", function () {
    // Une carte encore vide l'attend déjà : on la montre au lieu d'en créer une
    // seconde, numérotée pareil (T5-B6).
    var vide = etat.galerie.filter(function (b) { return nombrePhotos(b) === 0; })[0];
    if (!vide) {
      vide = nouvelleBouteille();
      etat.galerie.push(vide);
      sauver();
      afficherGalerie();
    }
    var carte = cartes.querySelector('[data-cle="' + vide.cle + '"]');
    if (carte) {
      carte.scrollIntoView({ block: "center", behavior: "smooth" });
      var choisir = carte.querySelector("input[type=file]");
      if (choisir) choisir.focus({ preventScroll: true });
    }
  });

  // En galerie : les bouteilles déjà photographiées (ici, à l'appareil photo, ou
  // reçues d'un autre appareil) ont aussi leur carte, dans l'ordre (T3-D12).
  function bouteillesDeLaGalerie() {
    var avecPhotos = etat.precedentes.concat(etat.enCours && nombrePhotos(etat.enCours) ? [etat.enCours] : []);
    return avecPhotos.concat(etat.galerie).sort(function (a, b) { return a.numero - b.numero; });
  }

  function afficherGalerie() {
    cartes.textContent = "";
    bouteillesDeLaGalerie().forEach(function (bouteille) {
      var carte = document.createElement("li");
      carte.className = "carte-galerie";
      carte.dataset.cle = bouteille.cle;
      var tete = document.createElement("div");
      tete.className = "en-cours-tete";
      var titre = document.createElement("strong");
      titre.textContent = "Bouteille " + rang(bouteille);
      var nombre = document.createElement("span");
      nombre.className = "compteur";
      nombre.textContent = nombrePhotos(bouteille) + " / " + accord(maximum, "photo", "photos");
      tete.appendChild(titre);
      tete.appendChild(nombre);
      carte.appendChild(tete);

      var vignettes = document.createElement("ul");
      vignettes.className = "vignettes-depot";
      carte.appendChild(vignettes);  // d'abord dans la carte : le refus s'y insère (T3-D5)
      afficherVignettes(vignettes, bouteille);

      var actions = document.createElement("div");
      actions.className = "actions-galerie";
      var etiquette = document.createElement("label");
      etiquette.className = "bouton" + (nombrePhotos(bouteille) >= maximum ? " inactif" : "");
      etiquette.textContent = "Ajouter ses photos";
      var choix = document.createElement("input");
      choix.type = "file";
      choix.multiple = true;
      choix.accept = "image/*,.heic,.heif";
      choix.className = "cache";
      choix.disabled = nombrePhotos(bouteille) >= maximum;
      choix.addEventListener("change", function (evenement) {
        var fichiers = Array.prototype.slice.call(evenement.target.files);
        evenement.target.value = "";
        fichiers.forEach(function (fichier) { ajouter(bouteille, fichier, false); });
      });
      etiquette.appendChild(choix);
      actions.appendChild(etiquette);
      // Au bureau : glisser des photos sur la carte les ajoute à cette bouteille (T4-DS1).
      carte.addEventListener("dragover", function (evenement) {
        if (nombrePhotos(bouteille) >= maximum) return;
        evenement.preventDefault();
        carte.classList.add("survol-depot");
      });
      carte.addEventListener("dragleave", function () { carte.classList.remove("survol-depot"); });
      carte.addEventListener("drop", function (evenement) {
        evenement.preventDefault();
        carte.classList.remove("survol-depot");
        Array.prototype.slice.call(evenement.dataTransfer.files || []).forEach(function (fichier) {
          ajouter(bouteille, fichier, false);
        });
      });

      var quantite = document.createElement("label");
      quantite.className = "quantite-galerie";
      quantite.textContent = "Quantité ";
      var champ = document.createElement("input");
      champ.type = "text";
      champ.inputMode = "numeric";
      champ.size = 3;
      champ.value = bouteille.quantite;
      champ.setAttribute("aria-label", "Quantité de la bouteille " + rang(bouteille));
      champ.addEventListener("change", function () { changerQuantite(bouteille, parseInt(champ.value, 10), champ); });
      quantite.appendChild(champ);
      actions.appendChild(quantite);

      // La seule carte vide : la retirer ne changerait rien à l'écran (T4-D9).
      if (!nombrePhotos(bouteille) && etat.galerie.length > 1) {
        var retirer = document.createElement("button");
        retirer.type = "button";
        retirer.className = "lien";
        retirer.textContent = "Retirer cette bouteille";
        retirer.addEventListener("click", function () {
          etat.galerie = etat.galerie.filter(function (b) { return b !== bouteille; });
          if (!etat.galerie.length) etat.galerie.push(nouvelleBouteille());
          sauver();
          afficherGalerie();
        });
        actions.appendChild(retirer);
      }
      carte.appendChild(actions);
      cartes.appendChild(carte);
    });
  }

  function afficherVignettes(conteneur, bouteille) {
    conteneur.textContent = "";
    // Les refus de cette bouteille, avec leur raison, là où l'on regarde (T2-D8).
    var carte = conteneur.parentNode;
    var refus = carte ? carte.querySelector(".refus-bouteille") : null;
    if (refus) refus.remove();
    var refusees = file.filter(function (envoi) { return envoi.bouteille.cle === bouteille.cle && envoi.etat === "refusee"; });
    var messages = refusees.map(function (envoi) { return envoi.message; });
    if (avisDeLaPage[bouteille.cle]) messages.push(avisDeLaPage[bouteille.cle]);
    if (carte && messages.length) {
      refus = document.createElement("ul");
      refus.className = "refus-bouteille";
      refus.setAttribute("role", "alert");
      messages.forEach(function (message) {
        var ligne = document.createElement("li");
        ligne.textContent = message;
        refus.appendChild(ligne);
      });
      conteneur.insertAdjacentElement("afterend", refus);
    }
    // Les photos déjà reçues avant cette page d'abord : c'est l'ordre du serveur (T4-D8).
    var anciennesAvant = bouteille.recues - file.filter(function (envoi) {
      return envoi.bouteille.cle === bouteille.cle && envoi.etat === "ok";
    }).length;
    (bouteille.miniatures || []).slice(0, Math.max(anciennesAvant, 0)).forEach(function (id) {
      var recue = document.createElement("li");
      recue.className = "vignette-depot ok";
      recue.title = "Photo déjà reçue";
      var image = document.createElement("img");
      image.src = api("/photos/" + id + "?taille=miniature");
      image.alt = "Photo déjà reçue";
      image.loading = "lazy";
      recue.appendChild(image);
      conteneur.appendChild(recue);
    });
    file.forEach(function (envoi) {
      if (envoi.bouteille.cle !== bouteille.cle || envoi.etat === "refusee") return;
      var element = document.createElement("li");
      element.className = "vignette-depot " + envoi.etat;
      element.title = envoi.nom + " — " + envoi.message;
      if (envoi.apercu) {
        var image = document.createElement("img");
        image.src = envoi.apercu;
        image.alt = envoi.nom;
        element.appendChild(image);
      } else {
        element.textContent = /\.hei[cf]$/i.test(envoi.nom) ? "📷 HEIC" : envoi.nom;
      }
      conteneur.appendChild(element);
    });
    var anciennes = anciennesAvant;
    var miniatures = (bouteille.miniatures || []).slice(0, Math.max(anciennes, 0));
    if (anciennes > miniatures.length) {
      var note = document.createElement("li");
      note.className = "vignette-depot deja";
      note.textContent = "+ " + accord(anciennes - miniatures.length, "déjà reçue", "déjà reçues");
      conteneur.appendChild(note);
    }
  }

  // --- changer de mode ----------------------------------------------------------------------------

  var boutonsMode = Array.prototype.slice.call(document.querySelectorAll("[data-mode]"));
  boutonsMode.forEach(function (bouton) {
    bouton.addEventListener("click", function () { choisirMode(bouton.dataset.mode); });
  });

  function choisirMode(mode) {
    etat.mode = mode;
    // La première carte n'est créée qu'ici : créée d'avance, elle prendrait un
    // numéro et la bouteille suivante de l'appareil photo en sauterait un.
    if (mode === "galerie" && !etat.galerie.length) etat.galerie.push(nouvelleBouteille());
    sauver();
    boutonsMode.forEach(function (bouton) {
      var actif = bouton.dataset.mode === mode;
      bouton.classList.toggle("actif", actif);
      bouton.setAttribute("aria-selected", actif ? "true" : "false");
    });
    document.querySelectorAll("[data-panneau]").forEach(function (panneau) {
      panneau.hidden = panneau.dataset.panneau !== mode;
    });
    // « Photographier » au téléphone, « Ajouter les photos » en galerie (T3-D18).
    var titre = document.getElementById("titre-depot");
    if (titre) titre.textContent = mode === "galerie" ? titre.dataset.galerie : titre.dataset.appareil;
    afficherGalerie();
  }

  // --- quantité (« × N ») ----------------------------------------------------------------------------

  var QUANTITE_MAX = 100000;

  function changerQuantite(bouteille, valeur, champ) {
    if (valeur > QUANTITE_MAX) {
      signalerQuantite(champ, "100 000 au plus.");
      if (champ) champ.value = bouteille.quantite;
      return;
    }
    if (!(valeur >= 1)) {  // 0, « abc », -3 : refusés comme sur « Vérifier » (T4-B15)
      signalerQuantite(champ, "Indiquez un nombre de bouteilles (1 ou plus).");
      if (champ) champ.value = bouteille.quantite;
      return;
    }
    signalerQuantite(champ, "");
    bouteille.quantite = valeur;
    bouteille.quantiteAEnvoyer = true;
    sauver();
    rafraichir();
    envoyerQuantites();
  }

  // Le refus d'une quantité s'affiche juste à côté du champ (T3-D8).
  function signalerQuantite(champ, message) {
    if (!champ) { if (message) afficherResume("Quantité : " + message); return; }
    var zone = champ.parentNode.querySelector(".refus-quantite");
    if (!zone && message) {
      zone = document.createElement("span");
      zone.className = "refus-quantite alerte-texte";
      zone.setAttribute("role", "alert");
      champ.insertAdjacentElement("afterend", zone);
    }
    if (zone) zone.textContent = message;
  }

  // Une bouteille déjà connue du serveur reçoit sa quantité tout de suite ; sinon
  // elle partira avec sa première photo.
  function envoyerQuantites() {
    toutes().forEach(function (bouteille) {
      if (!bouteille.quantiteAEnvoyer || !bouteille.recues || bouteille.envoiQuantite) return;
      bouteille.envoiQuantite = true;
      var valeur = bouteille.quantite;
      fetch(api("/bouteilles-en-cours/" + encodeURIComponent(bouteille.cle) + "/quantite"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quantite: valeur }),
      }).then(function (reponse) {
        if (reponse.ok && bouteille.quantite === valeur) bouteille.quantiteAEnvoyer = false;
        else if (reponse.status >= 400 && reponse.status < 500) {
          return reponse.json().then(function (corps) { afficherResume(corps.message || "Quantité refusée."); });
        }
      }).catch(function () { /* coupure : nouvel essai au retour du réseau */ })
        .then(function () { delete bouteille.envoiQuantite; sauver(); });
    });
  }

  // --- ajouter une photo à une bouteille -----------------------------------------------------------

  function ajouter(bouteille, fichier, depuisLaPage) {
    var signature = fichier.name + "|" + fichier.size + "|" + fichier.lastModified;
    var deja = file.filter(function (envoi) { return envoi.signature === signature && envoi.etat !== "refusee"; })[0];
    if (deja) {  // choisie une seconde fois : on le dit, dans la carte visée aussi (T4-B15, T5-B7)
      var avis = "« " + (fichier.name || "photo") + " » est déjà dans la bouteille " + rang(deja.bouteille) + ".";
      avisDeLaPage[bouteille.cle] = avis;
      afficherResume(avis);
      afficherGalerie();
      return;
    }
    delete avisDeLaPage[bouteille.cle];
    var envoi = {
      bouteille: bouteille, fichier: fichier, nom: fichier.name || "photo.jpg", signature: signature,
      etat: "attente", message: "En attente", essais: 0, idb: null,
      apercu: apercuLocal(fichier, fichier.name),
    };
    if (nombrePhotos(bouteille) >= maximum) {
      envoi.ligne = creerLigne(envoi);
      file.push(envoi);  // affiché dans la carte et compté dans le résumé (T3-D5)
      marquer(envoi, "refusee", "« " + envoi.nom + " » : " + maximum
        + " photos au plus par bouteille. Ajoutez-la à une autre bouteille.");
      rafraichir();
      return;
    }
    envoi.ligne = creerLigne(envoi);
    file.push(envoi);
    // Prise depuis la page, la photo n'existe que dans le navigateur : gardée
    // jusqu'à sa réception. (Une photo de la galerie reste dans la galerie.)
    var avant = depuisLaPage ? garder(envoi) : Promise.resolve();
    avant.then(function () {
      return fetch(api("/photos/deja-recues"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signatures: [signature] }),
      }).then(function (reponse) { return reponse.ok ? reponse.json() : { deja_recues: [] }; })
        .then(function (corps) { if (corps.deja_recues.indexOf(signature) >= 0) terminer(envoi, "deja", "Déjà reçue"); })
        .catch(function () { /* hors ligne : le serveur dédoublonnera de toute façon */ });
    }).then(function () { rafraichir(); pomper(); });
    rafraichir();
  }

  // Au retour sur la page : les photos prises et pas encore reçues repartent.
  function reprendreLesPhotosGardees() {
    return photosGardees().then(function (gardees) {
      gardees.forEach(function (garde) {
        var bouteille = toutes().filter(function (b) { return b.cle === garde.cle; })[0];
        if (!bouteille) {
          bouteille = { cle: garde.cle, numero: garde.numero, quantite: 1, recues: 0, quantiteAEnvoyer: false };
          etat.precedentes.push(bouteille);
        }
        var envoi = {
          bouteille: bouteille, fichier: garde.fichier, nom: garde.nom, signature: garde.signature,
          etat: "attente", message: "Reprise après interruption", essais: 0, idb: garde.id,
          apercu: apercuLocal(garde.fichier, garde.nom),
        };
        envoi.ligne = creerLigne(envoi);
        file.push(envoi);
      });
      if (gardees.length) {
        afficherResume(gardees.length > 1
          ? gardees.length + " photos prises ici et pas encore reçues : l'envoi reprend."
          : "1 photo prise ici et pas encore reçue : l'envoi reprend.");
      }
    });
  }

  // --- la file d'envoi ---------------------------------------------------------------------------

  function pomper() {
    envoyerQuantites();
    if (!navigator.onLine) {
      afficherResume("Connexion perdue : l'envoi reprendra tout seul dès son retour.");
      return;
    }
    while (actifs < SIMULTANES) {
      var suivant = file.find(function (envoi) { return envoi.etat === "attente" && !doitAttendre(envoi); });
      if (!suivant) break;
      envoyer(suivant);
    }
    rafraichir();
  }

  // Les photos d'UNE bouteille partent une à la fois, dans l'ordre où elles ont
  // été prises : le serveur les range dans l'ordre d'arrivée (« Photo 1 sur 3 »).
  // Plusieurs bouteilles, elles, partent en parallèle.
  function doitAttendre(envoi) {
    var avant = file.slice(0, file.indexOf(envoi));
    return avant.some(function (autre) {
      return autre.bouteille.cle === envoi.bouteille.cle && ["attente", "actif", "reessai"].indexOf(autre.etat) >= 0;
    });
  }

  function envoyer(envoi) {
    actifs += 1;
    marquer(envoi, "actif", "Préparation…");
    garderEcranAllume();
    // La quantité ne part que si elle a été changée sur cet appareil (T3-D1).
    var quantite = envoi.bouteille.quantiteAEnvoyer ? envoi.bouteille.quantite : null;
    preparer(envoi.fichier, envoi.nom)
      .then(function (prete) {
        marquer(envoi, "actif", "Envoi…");
        var donnees = new FormData();
        donnees.append("fichier", prete.contenu, prete.nom);
        donnees.append("bouteille", envoi.bouteille.cle);
        donnees.append("numero", envoi.bouteille.numero);
        if (quantite !== null) donnees.append("quantite", quantite);
        donnees.append("signature", envoi.signature);
        return fetch(api("/photos"), { method: "POST", body: donnees });
      })
      .then(function (reponse) {
        if (reponse.ok) {
          return reponse.json().then(function (corps) {
            if (corps.deja_recue) { terminer(envoi, "deja", "Déjà reçue"); return; }
            envoi.bouteille.recues += 1;
            if (envoi.bouteille.quantite === quantite) envoi.bouteille.quantiteAEnvoyer = false;
            terminer(envoi, "ok", "Envoyée");
          });
        }
        if (reponse.status >= 400 && reponse.status < 500) {
          // Refusée par le serveur : la raison est affichée, jamais ignorée.
          return reponse.json()
            .catch(function () { return { message: "Refusée par le serveur." }; })
            .then(function (corps) { terminer(envoi, "refusee", corps.message || "Refusée par le serveur."); });
        }
        // 502/503/504 : passage ; toute autre erreur du serveur n'est PAS une
        // coupure : au bout de 3 essais, la photo est refusée avec la raison,
        // et elle n'est plus renvoyée (T4-B1).
        if ([502, 503, 504].indexOf(reponse.status) < 0 && envoi.essais >= 2) {
          terminer(envoi, "refusee", "« " + envoi.nom + " » : le serveur n'a pas pu l'enregistrer. Retirez-la, "
            + "ou reprenez la photo.");
          return;
        }
        throw new Error("serveur " + reponse.status);
      })
      .catch(function () { reessayerPlusTard(envoi); })
      .then(function () {
        actifs -= 1;
        sauver();
        pomper();
      });
  }

  // Le navigateur n'affiche pas une photo HEIC : pas d'aperçu local, plutôt
  // qu'une image cassée (rapport du testeur, T1-m5). Elle est bien reçue.
  function apercuLocal(fichier, nom) {
    if (/\.hei[cf]$/i.test(nom || "") || /hei[cf]/i.test(fichier.type || "")) return null;
    return window.URL && URL.createObjectURL ? URL.createObjectURL(fichier) : null;
  }

  // Ce que le serveur a vraiment reçu, bouteille par bouteille : après une
  // reprise, le compteur dit juste (rapport du testeur, T1-m5).
  function resynchroniser() {
    return fetch(api("/apercu"), { headers: { Accept: "application/json" } })
      .then(function (reponse) { return reponse.ok ? reponse.json() : null; })
      .then(function (corps) {
        if (!corps) return;
        corps.bouteilles.forEach(function (attendue) {
          toutes().forEach(function (b) {
            if (b.cle && b.cle === attendue.cle) {
              b.miniatures = attendue.photos.map(function (p) { return p.id; });
              b.recues = b.miniatures.length;
            }
          });
        });
        sauver();
        rafraichir();
      })
      .catch(function () { /* hors ligne : on resynchronisera plus tard */ });
  }

  function terminer(envoi, etatFinal, message) {
    oublier(envoi);  // reçue (ou refusée, avec sa raison affichée) : plus besoin de la garder
    marquer(envoi, etatFinal, message);
    if (etatFinal === "deja") resynchroniser();
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
    file.forEach(function (envoi) { if (envoi.etat === "reessai") envoi.etat = "attente"; });
    pomper();
  });
  window.addEventListener("beforeunload", function (evenement) {
    if (enCours()) { evenement.preventDefault(); evenement.returnValue = ""; }
  });

  // --- préparer une photo --------------------------------------------------------------------------

  function preparer(fichier, nom) {
    if (!caseReduire.checked) return Promise.resolve({ contenu: fichier, nom: nom });
    return reduire(fichier)
      .then(function (reduit) {
        if (!reduit) return { contenu: fichier, nom: nom };
        return { contenu: reduit, nom: nom.replace(/\.[^.]*$/, "") + ".jpg" };
      })
      .catch(function () { return { contenu: fichier, nom: nom }; });
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
    nom.textContent = "Bouteille " + rang(envoi.bouteille) + " · " + envoi.nom;
    var etatEnvoi = document.createElement("span");
    etatEnvoi.className = "envoi-etat";
    etatEnvoi.textContent = envoi.message;
    ligne.appendChild(nom);
    ligne.appendChild(etatEnvoi);
    liste.insertBefore(ligne, liste.firstChild);
    return ligne;
  }

  function marquer(envoi, etatEnvoi, message) {
    envoi.etat = etatEnvoi;
    envoi.message = message;
    envoi.ligne.className = "envoi " + etatEnvoi;
    envoi.ligne.querySelector(".envoi-etat").textContent = message;
    envoi.ligne.dataset.etat = etatEnvoi;
    rafraichir();
  }

  function enCours() {
    return file.some(function (envoi) { return ["attente", "actif", "reessai"].indexOf(envoi.etat) >= 0; });
  }

  function compter(etatEnvoi) {
    return file.filter(function (envoi) { return envoi.etat === etatEnvoi; }).length;
  }

  function mettreEnAvantLaVerification() {
    var pret = toutes().some(function (b) { return nombrePhotos(b) > 0; });
    versVerification.classList.toggle("principal", pret);  // T2-DS4
  }

  function rafraichir() {
    mettreEnAvantLaVerification();
    afficherAppareil();
    afficherGalerie();
    afficherResume();
  }

  function afficherResume(message) {
    var total = file.length;
    var termines = compter("ok") + compter("deja") + compter("refusee");
    var parties = [];
    if (compter("ok")) parties.push(accord(compter("ok"), "envoyée", "envoyées"));
    if (compter("deja")) parties.push(accord(compter("deja"), "déjà reçue", "déjà reçues"));
    if (compter("refusee")) parties.push(accord(compter("refusee"), "refusée", "refusées") + " — voir la raison");
    if (total - termines) parties.push((total - termines) + " en cours");
    resumeTexte.textContent = message || (total ? parties.join(" · ") : resumeInitial);
    barre.hidden = !total || termines === total;  // tout est fini : le résumé suffit (T5-B14)
    barre.max = total || 1;
    barre.value = termines;

    var occupe = enCours();
    versVerification.classList.toggle("inactif", occupe);
    versVerification.setAttribute("aria-disabled", occupe ? "true" : "false");
    racine.dataset.etat = occupe ? "envoi" : "repos";
    if (!occupe) {
      garderOuvert.hidden = true;
      if (verrouEcran) { verrouEcran.release().catch(function () {}); verrouEcran = null; }
    }
  }

  versVerification.addEventListener("click", function (evenement) {
    if (enCours()) {
      evenement.preventDefault();
      afficherResume("Attendez la fin de l'envoi avant de vérifier les bouteilles.");
    }
  });

  // --- démarrage -------------------------------------------------------------------------------

  base.catch(function () { /* signalé à la première photo prise depuis la page */ });
  reprendreLesPhotosGardees().then(function () {
    reconcilier();
    choisirMode(etat.mode);
    rafraichir();
    pomper();
  });
})();
