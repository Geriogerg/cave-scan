/* Relecture au clavier (guide de session 5 ; decisions.md 0150-0153).
 *
 * Du JavaScript simple, sans framework, seulement là où le navigateur l'impose :
 *   1. raccourcis clavier — les raccourcis à une lettre et les flèches sont
 *      désactivés pendant la saisie dans un champ ;
 *   2. zoom et déplacement dans la photo, passage d'une photo à l'autre,
 *      chargement de l'original pour lire les petits caractères ;
 *   3. état de l'enregistrement : chaque champ est enregistré à sa sortie par
 *      HTMX ; ce script affiche l'état, réessaie après une coupure, et bloque le
 *      passage à une autre bouteille tant qu'une saisie n'est pas enregistrée ;
 *   4. temps de relecture actif (onglet visible, absences longues exclues),
 *      envoyé avec la validation.
 * Aucun garde-fou métier ici : le serveur vérifie chaque saisie et la validation.
 */
(function () {
  "use strict";

  var racine = document.querySelector("[data-relecture]");
  if (!racine) return;
  var fiche = document.getElementById("fiche");
  var indicateur = document.getElementById("indicateur");
  var champTemps = document.getElementById("temps");
  var aide = document.getElementById("aide-clavier");
  var PAUSE_MS = 60000;          // au-delà, l'expert n'est plus devant la bouteille
  var ATTENTE_MAX_MS = 15000;    // attendre la fin d'un enregistrement avant de changer de bouteille

  // --- état des enregistrements -------------------------------------------------------------
  // cle -> "modifie" | "envoi" | "enregistre" | "inchange" | "refuse" | "conflit" | "erreur"
  var etats = {};
  var essais = {};
  var quitterSansAlerte = false;

  function cleDe(element) {
    var champ = element && element.closest ? element.closest("[data-cle]") : null;
    return champ ? champ.dataset.cle : null;
  }

  function nomDe(cle) {
    var champ = document.getElementById("champ-" + cle);
    return champ ? champ.dataset.nom : cle;
  }

  function poser(cle, etat) {
    etats[cle] = etat;
    var champ = document.getElementById("champ-" + cle);
    if (champ) champ.dataset.etat = etat;
    afficherIndicateur();
  }

  function cles(predicat) {
    return Object.keys(etats).filter(function (cle) { return predicat(etats[cle]); });
  }

  function enCours() { return cles(function (e) { return e === "modifie" || e === "envoi"; }).length > 0; }

  function raisonDeBloquer() {
    var refuses = cles(function (e) { return e === "refuse"; });
    if (refuses.length) return "« " + nomDe(refuses[0]) + " » : la saisie est refusée. Corrigez-la avant de changer de bouteille.";
    var conflits = cles(function (e) { return e === "conflit"; });
    if (conflits.length) return "« " + nomDe(conflits[0]) + " » a été modifié ailleurs : choisissez « Enregistrer quand même » ou rechargez la bouteille.";
    var erreurs = cles(function (e) { return e === "erreur"; });
    if (erreurs.length) return "« " + nomDe(erreurs[0]) + " » n'est pas encore enregistré (connexion interrompue, nouvel essai en cours). Vous pourrez changer de bouteille dès qu'il le sera.";
    return null;
  }

  function afficherIndicateur() {
    var texte = "Tout est enregistré", classe = "ok";
    if (cles(function (e) { return e === "erreur"; }).length) { texte = "Erreur d'enregistrement, nouvel essai…"; classe = "alerte"; }
    else if (cles(function (e) { return e === "envoi"; }).length) { texte = "Enregistrement…"; classe = "encours"; }
    else if (enCours()) { texte = "Saisie en cours : enregistrée en quittant le champ"; classe = "encours"; }
    else if (cles(function (e) { return e === "refuse" || e === "conflit"; }).length) { texte = "Une saisie n'est pas enregistrée"; classe = "alerte"; }
    indicateur.textContent = texte;
    indicateur.className = "indicateur " + classe;
  }

  function annoncer(texte) {
    var zone = document.getElementById("messages");
    zone.innerHTML = "";
    var message = document.createElement("p");
    message.className = "message alerte";
    message.setAttribute("role", "alert");
    message.textContent = texte;
    zone.appendChild(message);
  }

  fiche.addEventListener("input", function (evenement) {
    var cle = cleDe(evenement.target);
    if (cle) poser(cle, "modifie");
  });

  // Une réponse « refusé » (422) ou « modifié ailleurs » (409) est une page à
  // afficher, pas une panne : HTMX l'insère comme les autres.
  document.body.addEventListener("htmx:beforeSwap", function (evenement) {
    var statut = evenement.detail.xhr.status;
    if (statut === 409 || statut === 422) {
      evenement.detail.shouldSwap = true;
      evenement.detail.isError = false;
    }
  });

  document.body.addEventListener("htmx:beforeRequest", function (evenement) {
    var cle = cleDe(evenement.detail.elt);
    if (cle) poser(cle, "envoi");
  });

  document.body.addEventListener("htmx:beforeOnLoad", function (evenement) {
    // Validation acceptée : tout ce que l'écran affichait est enregistré, la page change.
    if (evenement.detail.elt === fiche || /\/valider$/.test(evenement.detail.requestConfig.path)) {
      if (evenement.detail.xhr.status === 204) {
        etats = {};
        quitterSansAlerte = true;
      }
    }
  });

  document.body.addEventListener("htmx:afterRequest", function (evenement) {
    var elt = evenement.detail.elt;
    var statut = evenement.detail.xhr ? evenement.detail.xhr.status : 0;
    var chemin = evenement.detail.requestConfig ? evenement.detail.requestConfig.path : "";
    if (/\/valider$/.test(chemin)) return apresValidation(statut);
    var cle = cleDe(elt);
    if (!cle) return;
    if (statut === 0 || statut >= 500) {
      poser(cle, "erreur");
      reessayer(cle);
      return;
    }
    essais[cle] = 0;
    var pied = document.getElementById("pied-" + cle);
    var etat = pied && pied.dataset.etat ? pied.dataset.etat : "enregistre";
    // Saisi de nouveau pendant l'envoi : le prochain envoi suit déjà.
    if (etats[cle] === "modifie") return;
    poser(cle, etat);
  });

  function apresValidation(statut) {
    if (statut === 0 || statut >= 500) {
      annoncer("La validation n'a pas pu être envoyée (connexion interrompue ?). Rien n'est perdu : réessayez avec Ctrl+Entrée.");
      return;
    }
    if (statut === 204) return;
    if (document.querySelector("#messages [data-conflit]")) return;  // rien n'a été écrit
    // Refus : le serveur a enregistré les saisies valides, les autres sont signalées.
    Object.keys(etats).forEach(function (cle) {
      var pied = document.getElementById("pied-" + cle);
      poser(cle, pied && pied.dataset.etat === "refuse" ? "refuse" : "enregistre");
    });
    var refuse = document.querySelector('.champ-pied[data-etat="refuse"]');
    if (refuse) {
      var saisie = document.getElementById("saisie-" + refuse.id.replace("pied-", ""));
      if (saisie) entrerDans(saisie);
    }
  }

  function reessayer(cle) {
    essais[cle] = (essais[cle] || 0) + 1;
    var delai = Math.min(30000, 1000 * Math.pow(2, essais[cle] - 1));
    setTimeout(function () {
      var saisie = document.getElementById("saisie-" + cle);
      if (saisie && etats[cle] === "erreur") htmx.trigger(saisie, "change");
    }, delai);
  }

  // Attendre la fin des enregistrements en cours, puis agir — ou dire pourquoi on ne peut pas.
  function quandToutEstEnregistre(action) {
    var debut = Date.now();
    (function verifier() {
      var raison = raisonDeBloquer();
      if (raison) { annoncer(raison); return; }
      if (!enCours()) { action(); return; }
      if (Date.now() - debut > ATTENTE_MAX_MS) {
        annoncer("Un enregistrement ne répond pas : vérifiez la connexion. Vous pourrez changer de bouteille dès qu'il aura abouti.");
        return;
      }
      setTimeout(verifier, 100);
    })();
  }

  function allerA(adresse) {
    if (!adresse) return;
    var actif = document.activeElement;
    if (estSaisie(actif)) actif.blur();  // le champ quitté s'enregistre d'abord
    quandToutEstEnregistre(function () {
      quitterSansAlerte = true;
      location.href = adresse;
    });
  }

  document.addEventListener("click", function (evenement) {
    var lien = evenement.target.closest("a[data-navigation]");
    if (lien) {
      evenement.preventDefault();
      allerA(lien.href);
      return;
    }
    if (evenement.target.closest("[data-recharger]")) {  // choix explicite : abandonner la saisie
      evenement.preventDefault();
      quitterSansAlerte = true;
      location.reload();
    }
  });

  // Les autres actions (réanalyser, inverser, signaler, séparer) quittent la page.
  document.addEventListener("submit", function (evenement) {
    var formulaire = evenement.target;
    if (formulaire === fiche) {
      compterLeTemps();
      return;
    }
    if (!formulaire.hasAttribute("data-action") || formulaire.dataset.pret === "oui") return;
    evenement.preventDefault();
    quandToutEstEnregistre(function () {
      formulaire.dataset.pret = "oui";
      quitterSansAlerte = true;
      formulaire.submit();
    });
  }, true);

  window.addEventListener("beforeunload", function (evenement) {
    if (quitterSansAlerte) return;
    if (enCours() || raisonDeBloquer()) {
      evenement.preventDefault();
      evenement.returnValue = "";
    }
  });

  // --- valider ---------------------------------------------------------------------------------

  function valider() {
    if (aide && aide.open) return;
    compterLeTemps();
    fiche.requestSubmit();  // tout le formulaire part : rien de ce qui est affiché n'est perdu
  }

  // --- raccourcis clavier ----------------------------------------------------------------------

  function estSaisie(element) {
    if (!element || !element.tagName) return false;
    return element.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(element.tagName);
  }

  function estTexte(element) {
    return element && element.tagName === "INPUT" && /^(text|number|search)$/.test(element.type);
  }

  function premierChamp() { return fiche.querySelector(".saisie"); }

  // Comme la touche Tab du navigateur : le contenu est sélectionné, la frappe le remplace.
  function entrerDans(champ) {
    champ.focus();
    if (champ.select) champ.select();
  }

  document.addEventListener("keydown", function (evenement) {
    if (evenement.defaultPrevented || evenement.isComposing) return;
    var cible = evenement.target;
    var touche = evenement.key;

    if (aide.open) {
      if (touche === "?") { evenement.preventDefault(); aide.close(); }
      return;  // Échap ferme la boîte d'aide (navigateur)
    }
    if (touche === "Enter" && (evenement.ctrlKey || evenement.metaKey)) {
      evenement.preventDefault();
      valider();
      return;
    }
    if (touche === "Escape" && estSaisie(cible)) {
      evenement.preventDefault();
      cible.blur();  // le champ s'enregistre en le quittant
      racine.focus({ preventScroll: true });
      return;
    }
    if (touche === "Enter") {
      if (estTexte(cible)) {  // enregistrer le champ, sans valider la bouteille
        evenement.preventDefault();
        cible.blur();
        cible.focus();
        return;
      }
      if (cible.closest && cible.closest("button, a, summary, dialog, details")) return;
      if (cible.closest && cible.closest("form") && cible.closest("form") !== fiche) return;
      evenement.preventDefault();
      valider();
      return;
    }
    if (touche === "Tab" && !evenement.shiftKey && !estSaisie(cible) && fiche.contains(cible) === false
        && !(cible.closest && cible.closest("a, button, details, form"))) {
      evenement.preventDefault();  // Tab depuis la page : directement au premier champ
      entrerDans(premierChamp());
      return;
    }
    // Pendant la saisie dans un champ : aucun raccourci à une lettre, aucune flèche.
    if (estSaisie(cible) || evenement.ctrlKey || evenement.metaKey || evenement.altKey) return;
    switch (touche) {
      case "ArrowLeft": case "j": case "J":
        evenement.preventDefault();
        allerA(racine.dataset.precedente);
        break;
      case "ArrowRight": case "k": case "K":
        evenement.preventDefault();
        allerA(racine.dataset.suivante);
        break;
      case "z": case "Z":
        evenement.preventDefault();
        basculerZoom();
        break;
      case "e": case "E":
        evenement.preventDefault();
        basculerPhoto(evenement.shiftKey ? -1 : 1);
        break;
      case "?":
        evenement.preventDefault();
        aide.showModal();
        break;
    }
  });

  document.querySelectorAll("[data-aide]").forEach(function (bouton) {
    bouton.addEventListener("click", function () { aide.showModal(); });
  });

  // --- photos : zoom, déplacement, bascule -------------------------------------------------------

  var visionneuse = document.querySelector("[data-visionneuse]");
  var image = document.getElementById("photo-active");
  var lienOriginal = document.getElementById("lien-original");
  var vignettes = Array.prototype.slice.call(document.querySelectorAll("[data-photo]"));
  var echelle = 1, decalageX = 0, decalageY = 0, originaleDemandee = false;
  var dernierPointeur = null, glisser = null;

  function appliquer() {
    image.style.transform = "translate(" + decalageX + "px, " + decalageY + "px) scale(" + echelle + ")";
    visionneuse.classList.toggle("zoomee", echelle > 1);
  }

  function borner() {
    var largeur = visionneuse.clientWidth, hauteur = visionneuse.clientHeight;
    decalageX = Math.min(0, Math.max(largeur - largeur * echelle, decalageX));
    decalageY = Math.min(0, Math.max(hauteur - hauteur * echelle, decalageY));
  }

  // Le point (x, y) de la visionneuse reste sous le curseur pendant le zoom.
  function zoomer(nouvelle, x, y) {
    nouvelle = Math.max(1, Math.min(8, nouvelle));
    decalageX = x - (x - decalageX) * nouvelle / echelle;
    decalageY = y - (y - decalageY) * nouvelle / echelle;
    echelle = nouvelle;
    if (echelle === 1) { decalageX = 0; decalageY = 0; }
    borner();
    appliquer();
    if (echelle > 1) chargerOriginale();
  }

  // Zoomé, l'image passe à l'original : un millésime en petits caractères se lit.
  function chargerOriginale() {
    if (originaleDemandee) return;
    originaleDemandee = true;
    var adresse = image.dataset.originale;
    var tampon = new Image();
    tampon.onload = function () { if (image.dataset.originale === adresse) image.src = adresse; };
    tampon.src = adresse;
  }

  function centre() {
    if (dernierPointeur) return dernierPointeur;
    return { x: visionneuse.clientWidth / 2, y: visionneuse.clientHeight / 2 };
  }

  function basculerZoom() {
    var point = centre();
    zoomer(echelle > 1 ? 1 : 2.5, point.x, point.y);
  }

  function montrer(vignette) {
    vignettes.forEach(function (v) { v.classList.toggle("active", v === vignette); });
    image.src = vignette.dataset.reduite;
    image.dataset.originale = vignette.dataset.originale;
    image.alt = vignette.dataset.libelle;
    lienOriginal.href = vignette.dataset.originale;
    originaleDemandee = false;
    echelle = 1; decalageX = 0; decalageY = 0;
    appliquer();
  }

  // E : photo suivante ; Maj+E : précédente (toutes les photos de la bouteille, 0166).
  function basculerPhoto(sens) {
    if (vignettes.length < 2) return;
    var active = vignettes.findIndex(function (v) { return v.classList.contains("active"); });
    montrer(vignettes[(active + sens + vignettes.length) % vignettes.length]);
  }

  vignettes.forEach(function (vignette) {
    vignette.addEventListener("click", function () { montrer(vignette); });
  });

  function position(evenement) {
    var cadre = visionneuse.getBoundingClientRect();
    return { x: evenement.clientX - cadre.left, y: evenement.clientY - cadre.top };
  }

  visionneuse.addEventListener("wheel", function (evenement) {
    evenement.preventDefault();
    var point = position(evenement);
    zoomer(echelle * (evenement.deltaY < 0 ? 1.25 : 0.8), point.x, point.y);
  }, { passive: false });

  visionneuse.addEventListener("dblclick", function (evenement) {
    var point = position(evenement);
    zoomer(echelle > 1 ? 1 : 2.5, point.x, point.y);
  });

  visionneuse.addEventListener("pointermove", function (evenement) {
    dernierPointeur = position(evenement);
    if (!glisser) return;
    decalageX = glisser.decalageX + evenement.clientX - glisser.x;
    decalageY = glisser.decalageY + evenement.clientY - glisser.y;
    borner();
    appliquer();
  });

  visionneuse.addEventListener("pointerleave", function () { dernierPointeur = null; });

  visionneuse.addEventListener("pointerdown", function (evenement) {
    if (echelle === 1) return;
    glisser = { x: evenement.clientX, y: evenement.clientY, decalageX: decalageX, decalageY: decalageY };
    visionneuse.setPointerCapture(evenement.pointerId);
    visionneuse.classList.add("glisse");
  });

  ["pointerup", "pointercancel"].forEach(function (nom) {
    visionneuse.addEventListener(nom, function () {
      glisser = null;
      visionneuse.classList.remove("glisse");
    });
  });

  // --- temps de relecture ----------------------------------------------------------------------
  // Compté seconde par seconde, seulement onglet visible et expert présent
  // (une touche, un geste de souris depuis moins d'une minute).

  var tempsActif = 0;
  var dernierTic = performance.now();
  var derniereActivite = Date.now();

  ["keydown", "pointerdown", "pointermove", "wheel", "input"].forEach(function (nom) {
    document.addEventListener(nom, function () { derniereActivite = Date.now(); }, { passive: true });
  });

  // Appelé chaque seconde, et juste avant une validation : une bouteille validée
  // en moins d'une seconde a aussi son temps.
  function compterLeTemps() {
    var maintenant = performance.now();
    var ecart = maintenant - dernierTic;
    dernierTic = maintenant;
    if (!document.hidden && Date.now() - derniereActivite < PAUSE_MS) tempsActif += ecart;
    champTemps.value = String(Math.round(tempsActif));
  }

  setInterval(compterLeTemps, 1000);
})();
