"""L'écran de relecture (guide de session 5 ; decisions.md 0150-0153).

Une page par bouteille, pensée pour l'ordinateur et le clavier. Comme les
autres écrans, chaque route appelle une fonction de service et affiche son
résultat ; les garde-fous (saisie hors liste, quantité invalide, paire
signalée, modification faite ailleurs) sont tous vérifiés par le serveur.

- Chaque champ est enregistré à sa sortie (HTMX, `.../champ/{cle}`) : la
  réponse ne remplace jamais le champ lui-même, seulement son état et son
  origine — une saisie en cours n'est jamais écrasée.
- Valider envoie tout le formulaire : ce qui n'était pas encore enregistré
  l'est d'abord, puis la page de la bouteille suivante s'affiche.
- Sans JavaScript, le formulaire et les actions restent de simples POST.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse, Response

from src.api.dependances import AuteurEcran, Formulaire, SessionBase
from src.services.cycle_de_vie import bouteilles_retirees, remettre_bouteille, retirer_bouteille
from src.services.cas_particuliers import (
    lever_signalement,
    reanalyser,
    separer,
    signaler_paire,
)
from src.services.consultation import (
    bouteille_de,
    etats_de_relecture,
    fiche_de_relecture,
    prochaine_a_relire,
    recapitulatif,
)
from src.services.inventaires import InventaireClos, charger_inventaire, config_figee
from src.services.relecture import (
    CorrectionRefusee,
    ModificationConcurrente,
    SaisiesRefusees,
    ajouter_temps_de_relecture,
    corriger_en_relecture,
    revenir_a_la_valeur_du_modele,
    valider_en_relecture,
)
from src.web.pages import ERREURS_DE_SERVICE, page

FILTRE = "a_verifier"

# Après une action, un message court (jamais un texte arbitraire dans l'adresse).
MESSAGES_FAIT = {
    "remise": "Bouteille remise dans l'inventaire : elle revient dans la relecture et dans l'Excel.",
    "levee": "Signalement levé : la bouteille peut de nouveau être validée.",
    "separee": "Bouteille séparée. Ajustez l'état et la description de cet exemplaire.",
    "retiree": "Bouteille retirée de l'inventaire. Elle se remet depuis le récapitulatif.",
}

routeur = APIRouter(include_in_schema=False)

Filtre = Annotated[str | None, Query()]


def adresse(inventaire_id: int, bouteille_id: int | None = None, filtre: bool = False, fait: str | None = None) -> str:
    if bouteille_id is None:
        return f"/app/inventaires/{inventaire_id}/recapitulatif"
    parametres = [p for p in (f"filtre={FILTRE}" if filtre else "", f"fait={fait}" if fait else "") if p]
    return f"/app/inventaires/{inventaire_id}/relecture/{bouteille_id}" + ("?" + "&".join(parametres) if parametres else "")


def _redirection(request: Request, cible: str) -> Response:
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": cible})
    return RedirectResponse(cible, status_code=303)


def _page_bouteille(request: Request, base, inventaire_id: int, bouteille_id: int, filtre: bool, statut: int = 200, **contexte):
    fiche = fiche_de_relecture(base, inventaire_id, bouteille_id, filtre)
    return page(
        request,
        "relecture.html",
        statut,
        fiche=fiche,
        adresse_precedente=adresse(inventaire_id, fiche.precedente_id, filtre) if fiche.precedente_id else None,
        adresse_suivante=adresse(inventaire_id, fiche.suivante_id, filtre) if fiche.suivante_id else None,
        adresse_filtre=adresse(inventaire_id, bouteille_id, not filtre),
        **contexte,
    )


# --- entrer, afficher ----------------------------------------------------------------------------


@routeur.get("/app/inventaires/{inventaire_id}/relecture")
def entrer(inventaire_id: int, base: SessionBase, filtre: Filtre = None):
    """La première bouteille non validée — ou le récapitulatif s'il n'en reste pas."""
    inventaire = charger_inventaire(base, inventaire_id)
    if inventaire.statut == "brouillon":
        return RedirectResponse(f"/app/inventaires/{inventaire_id}/depot", status_code=303)
    avec_filtre = filtre == FILTRE
    prochaine = prochaine_a_relire(etats_de_relecture(base, inventaire_id), None, avec_filtre)
    return RedirectResponse(adresse(inventaire_id, prochaine, avec_filtre), status_code=303)


@routeur.get("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}")
def afficher(request: Request, inventaire_id: int, bouteille_id: int, base: SessionBase, auteur: AuteurEcran,
             filtre: Filtre = None, fait: Filtre = None):
    if bouteille_de(base, inventaire_id, bouteille_id).retiree:  # hors de l'inventaire : au récapitulatif
        return RedirectResponse(adresse(inventaire_id), status_code=303)
    return _page_bouteille(request, base, inventaire_id, bouteille_id, filtre == FILTRE,
                           fait=MESSAGES_FAIT.get(fait or ""), auteur=auteur)


@routeur.get("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/attente")
def attente(request: Request, inventaire_id: int, bouteille_id: int, base: SessionBase):
    """Réanalyse en attente : la page se recharge d'elle-même quand elle est faite."""
    bouteille = bouteille_de(base, inventaire_id, bouteille_id)
    if bouteille.statut in ("a_extraire", "en_cours"):
        return page(request, "_attente.html", inventaire_id=inventaire_id, bouteille=bouteille)
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@routeur.get("/app/inventaires/{inventaire_id}/recapitulatif")
def recapituler(request: Request, inventaire_id: int, base: SessionBase, erreur: str | None = None):
    inventaire = charger_inventaire(base, inventaire_id)
    if inventaire.statut == "brouillon":
        return RedirectResponse(f"/app/inventaires/{inventaire_id}/depot", status_code=303)
    return page(request, "recapitulatif.html", recap=recapitulatif(base, inventaire_id),
                retirees=bouteilles_retirees(base, inventaire_id))


@routeur.post("/app/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/remettre")
def remettre(request: Request, inventaire_id: int, bouteille_id: int, base: SessionBase, auteur: AuteurEcran):
    bouteille_de(base, inventaire_id, bouteille_id)
    try:
        remettre_bouteille(base, bouteille_id, auteur)
    except ERREURS_DE_SERVICE as refus:
        return page(request, "erreur.html", 409, message=str(refus))
    return RedirectResponse(adresse(inventaire_id, bouteille_id, fait="remise"), status_code=303)


# --- enregistrer un champ, revenir à la valeur du modèle --------------------------------------


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/champ/{cle}")
def enregistrer_champ(request: Request, inventaire_id: int, bouteille_id: int, cle: str,
                      base: SessionBase, auteur: AuteurEcran, saisies: Formulaire):
    """Enregistre UN champ à sa sortie. Réponse : l'état du champ (enregistré,
    refusé avec la raison, ou modifié ailleurs), et ce qui en découle ailleurs
    dans la page (version, origine, compteurs, historique)."""
    bouteille = bouteille_de(base, inventaire_id, bouteille_id)
    etait_validee = bouteille.statut == "validee"
    contexte: dict = {"message": None, "changements": None}
    try:
        if cle not in saisies:
            raise CorrectionRefusee("Aucune valeur reçue pour ce champ : rien n'a été enregistré.")
        correction = corriger_en_relecture(
            base, bouteille_id, cle, saisies[cle], auteur, saisies.get("_version"), saisies.get("_forcer") == "1"
        )
        etat, statut = ("enregistre" if correction is not None else "inchange"), 200
    except (CorrectionRefusee, InventaireClos) as refus:
        etat, statut, contexte["message"] = "refuse", 422, str(refus)
    except ModificationConcurrente as conflit:
        etat, statut, contexte["changements"] = "conflit", 409, conflit.changements
    fiche = fiche_de_relecture(base, inventaire_id, bouteille_id, saisies.get("_filtre") == FILTRE)
    return page(
        request, "_reponse_champ.html", statut, fiche=fiche, champ=_le_champ(fiche, cle), cle=cle, etat=etat,
        remise_a_relire=etait_validee and fiche.bouteille.statut != "validee", **contexte,
    )


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/champ/{cle}/revenir")
def revenir(request: Request, inventaire_id: int, bouteille_id: int, cle: str,
            base: SessionBase, auteur: AuteurEcran, saisies: Formulaire):
    bouteille_de(base, inventaire_id, bouteille_id)
    contexte: dict = {"message": None, "changements": None}
    try:
        revenir_a_la_valeur_du_modele(base, bouteille_id, cle, auteur, saisies.get("_version"), saisies.get("_forcer") == "1")
        etat, statut = "enregistre", 200
    except (CorrectionRefusee, InventaireClos) as refus:
        etat, statut, contexte["message"] = "refuse", 422, str(refus)
    except ModificationConcurrente as conflit:
        etat, statut, contexte["changements"] = "conflit", 409, conflit.changements
    fiche = fiche_de_relecture(base, inventaire_id, bouteille_id, saisies.get("_filtre") == FILTRE)
    return page(request, "_reponse_revenir.html", statut, fiche=fiche, champ=_le_champ(fiche, cle), cle=cle,
                etat=etat, **contexte)


def _le_champ(fiche, cle: str):
    return next((champ for champ in fiche.champs if champ.cle == cle), None)


# --- valider ---------------------------------------------------------------------------------


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/valider")
def valider(request: Request, inventaire_id: int, bouteille_id: int,
            base: SessionBase, auteur: AuteurEcran, saisies: Formulaire):
    """Valide la bouteille avec ce que l'écran affiche, puis passe à la suivante
    à relire (ou au récapitulatif)."""
    bouteille = bouteille_de(base, inventaire_id, bouteille_id)
    position = bouteille.position
    filtre = saisies.get("_filtre") == FILTRE
    affiches = [c.cle for c in config_figee(bouteille.inventaire).colonnes if c.source != "systeme"]
    try:
        valider_en_relecture(
            base, bouteille_id, auteur,
            {cle: saisies[cle] for cle in affiches if cle in saisies},
            saisies.get("_version"), _entier(saisies.get("_temps_ms")), saisies.get("_forcer") == "1",
        )
    except SaisiesRefusees as refus:
        return _refus_de_validation(request, base, inventaire_id, bouteille_id, filtre, 422, str(refus), refus=refus.refus)
    except ModificationConcurrente as conflit:
        return _refus_de_validation(request, base, inventaire_id, bouteille_id, filtre, 409, None,
                                    changements=conflit.changements)
    except ERREURS_DE_SERVICE as refus:
        return _refus_de_validation(request, base, inventaire_id, bouteille_id, filtre, 409, str(refus))
    prochaine = prochaine_a_relire(etats_de_relecture(base, inventaire_id), position, filtre)
    return _redirection(request, adresse(inventaire_id, prochaine, filtre))


def _refus_de_validation(request, base, inventaire_id, bouteille_id, filtre, statut, message, refus=None, changements=None):
    if not request.headers.get("HX-Request"):  # sans JavaScript : la page entière, avec le message
        return _page_bouteille(request, base, inventaire_id, bouteille_id, filtre, statut,
                               erreur=message or "Cette bouteille a été modifiée ailleurs : rechargez-la.")
    fiche = fiche_de_relecture(base, inventaire_id, bouteille_id, filtre)
    return page(request, "_reponse_validation.html", statut, fiche=fiche, message=message,
                refus=refus or {}, changements=changements)


def _entier(texte: str | None) -> int | None:
    try:
        return int(float(texte)) if texte else None
    except ValueError:
        return None


# --- cas particuliers --------------------------------------------------------------------------


def _action(request: Request, base, inventaire_id: int, bouteille_id: int, saisies: dict, faire, fait: str):
    """Une action de la page (réanalyser, signaler, séparer) : faite, puis
    retour sur la bouteille avec un message ; refusée, la page dit pourquoi."""
    bouteille_de(base, inventaire_id, bouteille_id)
    filtre = saisies.get("_filtre") == FILTRE
    try:
        cible = faire()
    except ERREURS_DE_SERVICE as refus:
        return _page_bouteille(request, base, inventaire_id, bouteille_id, filtre, 409, erreur=str(refus))
    return RedirectResponse(adresse(inventaire_id, cible or bouteille_id, filtre, fait), status_code=303)


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/reanalyser")
def demander_reanalyse(request: Request, inventaire_id: int, bouteille_id: int,
                       base: SessionBase, auteur: AuteurEcran, saisies: Formulaire):
    return _action(request, base, inventaire_id, bouteille_id, saisies,
                   lambda: reanalyser(base, bouteille_id, auteur) and None, "reanalyse")


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/temps")
def temps_sans_validation(inventaire_id: int, bouteille_id: int, base: SessionBase, saisies: Formulaire):
    """Le temps passé sur la bouteille, envoyé par l'écran en la quittant (0169)."""
    bouteille_de(base, inventaire_id, bouteille_id)
    ajouter_temps_de_relecture(base, bouteille_id, _entier(saisies.get("temps_ms")))
    return Response(status_code=204)


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/retirer")
def retirer(request: Request, inventaire_id: int, bouteille_id: int,
            base: SessionBase, auteur: AuteurEcran, saisies: Formulaire):
    """Retirer la bouteille de l'inventaire (rien n'est effacé, 0168), puis passer
    à la suivante à relire."""
    filtre = saisies.get("_filtre") == FILTRE
    position = bouteille_de(base, inventaire_id, bouteille_id).position

    def faire():
        retirer_bouteille(base, bouteille_id, auteur, saisies.get("motif", ""))
        return prochaine_a_relire(etats_de_relecture(base, inventaire_id), position, filtre)

    try:
        suivante = faire()
    except ERREURS_DE_SERVICE as refus:
        return _page_bouteille(request, base, inventaire_id, bouteille_id, filtre, 409, erreur=str(refus))
    if suivante is None:
        return RedirectResponse(adresse(inventaire_id), status_code=303)
    return RedirectResponse(adresse(inventaire_id, suivante, filtre, "retiree"), status_code=303)


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/signaler")
def signaler(request: Request, inventaire_id: int, bouteille_id: int,
             base: SessionBase, auteur: AuteurEcran, saisies: Formulaire):
    return _action(request, base, inventaire_id, bouteille_id, saisies,
                   lambda: signaler_paire(base, bouteille_id, auteur, saisies.get("motif", "")) and None, "signalee")


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/lever-signalement")
def lever(request: Request, inventaire_id: int, bouteille_id: int,
          base: SessionBase, auteur: AuteurEcran, saisies: Formulaire):
    return _action(request, base, inventaire_id, bouteille_id, saisies,
                   lambda: lever_signalement(base, bouteille_id, auteur) and None, "levee")


@routeur.post("/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/separer")
def separer_bouteille(request: Request, inventaire_id: int, bouteille_id: int,
                      base: SessionBase, auteur: AuteurEcran, saisies: Formulaire):
    """La nouvelle bouteille s'affiche : l'expert ajuste son état et sa description."""
    return _action(request, base, inventaire_id, bouteille_id, saisies,
                   lambda: separer(base, bouteille_id, saisies.get("quantite", ""), auteur).id, "separee")
