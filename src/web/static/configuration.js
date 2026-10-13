/* Page Configuration : prévenir avant de quitter une config modifiée et pas
 * enregistrée (decisions.md 0163). Tout le reste est fait par le serveur. */
(function () {
  "use strict";

  var modifiee = false;
  // La barre « Annuler / Vérifier / Enregistrer » n'occupe l'écran qu'une fois
  // quelque chose de modifié (T2-DS5).
  function montrerLaBarre() {
    var barre = document.querySelector(".barre-config");
    if (barre) barre.removeAttribute("data-sans-modification");
  }
  // Masquée au chargement par le script seulement : sans JavaScript, elle reste là.
  var barreInitiale = document.querySelector(".barre-config");
  if (barreInitiale && !document.querySelector("#editeur > .message.alerte")) {
    barreInitiale.setAttribute("data-sans-modification", "");
  }

  document.addEventListener("input", function (evenement) {
    if (evenement.target.closest && evenement.target.closest("[data-config]")) { modifiee = true; montrerLaBarre(); }
  });
  document.addEventListener("change", function (evenement) {
    if (evenement.target.closest && evenement.target.closest("[data-config]")) { modifiee = true; montrerLaBarre(); }
  });
  // Ajouter, déplacer, retirer : la config affichée diffère de la version active.
  // Les colonnes ouvertes le restent après une action (ajouter une valeur,
  // monter, changer le type…) ; celle qui a agi est mise en vue (T2-2).
  var ouvertes = null, active = null;
  function indexDe(element) {
    var li = element && element.closest ? element.closest("li.colonne-config") : null;
    return li ? parseInt(li.id.replace("colonne-", ""), 10) : null;
  }
  document.body.addEventListener("htmx:beforeRequest", function (evenement) {
    ouvertes = Array.prototype.map.call(document.querySelectorAll("details.colonne-detail[open]"), indexDe);
    var config = evenement.detail.requestConfig || {};
    var bouton = config.triggeringEvent && config.triggeringEvent.submitter;
    var action = bouton ? bouton.value : "";
    active = indexDe(bouton || evenement.detail.elt);
    var m = /^(monter|descendre|supprimer)-(\d+)$/.exec(action);
    if (m) {
      var i = parseInt(m[2], 10), j = m[1] === "monter" ? i - 1 : m[1] === "descendre" ? i + 1 : null;
      ouvertes = ouvertes.map(function (k) {
        if (j === null) return k > i ? k - 1 : (k === i ? null : k);
        return k === i ? j : (k === j ? i : k);
      });
      active = j;
    }
  });

  // Un refus, ou un message, doit se voir : la page fait 10 000 px et le bouton
  // « Enregistrer » est en bas (rapport du testeur, T1-M3).
  document.body.addEventListener("htmx:afterSwap", function (evenement) {
    if (evenement.target.id !== "editeur" && evenement.detail.target.id !== "editeur") return;
    modifiee = true;
    montrerLaBarre();
    (ouvertes || []).concat(active === null ? [] : [active]).forEach(function (k) {
      var d = k === null ? null : document.querySelector("#colonne-" + k + " details.colonne-detail");
      if (d) d.open = true;
    });
    var message = document.getElementById("refus-consignes") || document.querySelector("#editeur > .message");
    var cible = active === null ? null : document.getElementById("colonne-" + active);
    if (message) message.scrollIntoView({ block: "start", behavior: "smooth" });
    else if (cible) cible.scrollIntoView({ block: "nearest" });
    ouvertes = active = null;
  });
  // Enregistrer (redirection) ou annuler volontairement : on peut partir.
  document.body.addEventListener("htmx:beforeRequest", function (evenement) {
    var bouton = evenement.detail.requestConfig && evenement.detail.requestConfig.triggeringEvent
      ? evenement.detail.requestConfig.triggeringEvent.submitter : null;
    if (bouton && bouton.value === "enregistrer") modifiee = false;
  });
  document.addEventListener("click", function (evenement) {
    if (evenement.target.closest && evenement.target.closest("[data-abandon]")) modifiee = false;
  });
  // Une config refusée (422) ou modifiée ailleurs (409) est une page à afficher,
  // avec ses raisons : HTMX l'insère comme les autres.
  document.body.addEventListener("htmx:beforeSwap", function (evenement) {
    var statut = evenement.detail.xhr.status;
    if (statut === 409 || statut === 422) {
      evenement.detail.shouldSwap = true;
      evenement.detail.isError = false;
    }
  });
  // Consignes générales : verrouillées par le script (sans JavaScript, la case
  // à cocher suffit) ; première confirmation pour les déverrouiller, seconde :
  // la case, exigée par le serveur à l'enregistrement.
  var consignesDeverrouillees = false;  // le reste après une action (ajouter une colonne…)
  function verrouillerLesConsignes() {
    var zone = document.getElementById("consignes");
    if (!zone) return;
    // Un refus des consignes : elles restent déverrouillées, la case visible (T3-D7).
    if (document.getElementById("refus-consignes")) consignesDeverrouillees = true;
    if (consignesDeverrouillees) {
      zone.readOnly = false;
      var caseConfirmer = document.getElementById("confirmer-consignes");
      if (caseConfirmer) caseConfirmer.hidden = false;
      var bouton = document.getElementById("deverrouiller-consignes");
      if (bouton) bouton.hidden = true;
      return;
    }
    zone.readOnly = true;
    document.getElementById("confirmer-consignes").hidden = true;
  }
  verrouillerLesConsignes();
  document.body.addEventListener("htmx:afterSwap", verrouillerLesConsignes);
  document.addEventListener("click", function (evenement) {
    var bouton = evenement.target.closest && evenement.target.closest("#deverrouiller-consignes");
    if (!bouton) return;
    if (!window.confirm(bouton.dataset.question)) return;
    var zone = document.getElementById("consignes");
    zone.readOnly = false;
    consignesDeverrouillees = true;
    zone.focus();
    document.getElementById("confirmer-consignes").hidden = false;
    bouton.hidden = true;
  });

  window.addEventListener("beforeunload", function (evenement) {
    if (modifiee) { evenement.preventDefault(); evenement.returnValue = ""; }
  });
})();
