/* Page Configuration : prévenir avant de quitter une config modifiée et pas
 * enregistrée (decisions.md 0163). Tout le reste est fait par le serveur. */
(function () {
  "use strict";

  var modifiee = false;

  document.addEventListener("input", function (evenement) {
    if (evenement.target.closest && evenement.target.closest("[data-config]")) modifiee = true;
  });
  document.addEventListener("change", function (evenement) {
    if (evenement.target.closest && evenement.target.closest("[data-config]")) modifiee = true;
  });
  // Ajouter, déplacer, retirer : la config affichée diffère de la version active.
  document.body.addEventListener("htmx:afterSwap", function (evenement) {
    if (evenement.target.id === "editeur") modifiee = true;
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
  window.addEventListener("beforeunload", function (evenement) {
    if (modifiee) { evenement.preventDefault(); evenement.returnValue = ""; }
  });
})();
