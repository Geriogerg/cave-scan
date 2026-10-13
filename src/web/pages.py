"""Les écrans de l'expert : accueil, nouvel inventaire, dépôt des photos
bouteille par bouteille, vérification des bouteilles en attente, suivi (guides
des sessions 4 et 6 ; decisions.md 0131, 0167).

Pages générées côté serveur (Jinja2) + HTMX. Comme l'API, chaque route ne fait
qu'appeler une fonction de service et afficher : aucun garde-fou n'est vérifié
ici ni dans le navigateur seulement. Un refus d'un service s'affiche dans la
page, en français, jamais comme un message technique.
"""

from __future__ import annotations

import json
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.api.dependances import SessionBase, Stockage, auteur_des_ecrans
from src.api.erreurs import TRADUCTIONS
from src.services.consultation import tableau_des_inventaires
from src.services.depot import (
    apercu,
    couper,
    creer_brouillon,
    finaliser,
    quantite_du_groupe,
    rattacher,
    supprimer_groupe,
    supprimer_photo,
)
from src.services.depot import ModificationRefusee
from src.services.envoi import TAILLE_MAX_OCTETS, config_de_la_maison, configs_disponibles
from src.services.inventaires import charger_inventaire, lister_inventaires
from src.services.pilotage import avancement, reprendre

DOSSIER = Path(__file__).resolve().parent

# Sous Windows, le registre associe parfois « .js » à text/plain : un navigateur
# strict refuserait alors d'exécuter le script d'envoi.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
gabarits = Jinja2Templates(directory=DOSSIER / "gabarits")

# Réduction dans le navigateur avant l'envoi (decisions.md 0130) : désactivée par
# défaut tant que son effet sur l'extraction n'est pas mesuré.
REDUCTION_PAR_DEFAUT = False
TAILLE_REDUCTION = 2500  # côté long, en pixels

ERREURS_DE_SERVICE = tuple(classe for classe, _statut, _code in TRADUCTIONS)

routeur = APIRouter(include_in_schema=False)


def _duree(secondes: float | None) -> str:
    if secondes is None:
        return "—"
    secondes = int(round(secondes))
    if secondes < 60:
        return f"{secondes} s"
    minutes, secondes = divmod(secondes, 60)
    if minutes < 60:
        return f"{minutes} min {secondes:02d} s"
    heures, minutes = divmod(minutes, 60)
    return f"{heures} h {minutes:02d} min"


def _date(valeur: datetime | None) -> str:
    return valeur.strftime("%d/%m/%Y") if valeur else "—"


def _horodatage(valeur: datetime | None) -> str:
    """Une date de la base (UTC sans fuseau, decisions.md 0086) à l'heure du poste."""
    return valeur.replace(tzinfo=UTC).astimezone().strftime("%d/%m %H:%M") if valeur else "—"


gabarits.env.filters["duree"] = _duree
gabarits.env.filters["date"] = _date
gabarits.env.filters["horodatage"] = _horodatage
gabarits.env.globals["auteur_des_ecrans"] = auteur_des_ecrans


def page(request: Request, gabarit: str, statut: int = 200, **contexte) -> HTMLResponse:
    return gabarits.TemplateResponse(request, gabarit, contexte, status_code=statut)


# --- accueil et création -------------------------------------------------------------------------


@routeur.get("/")
def racine() -> RedirectResponse:
    return RedirectResponse("/app", status_code=303)


@routeur.get("/app")
def accueil(request: Request, base: SessionBase, fait: str | None = None):
    from src.web.cycle import MESSAGES

    tous = tableau_des_inventaires(base)
    return page(
        request, "accueil.html",
        inventaires=[(i, e) for i, e in tous if i.archive_le is None],
        archives=[(i, e) for i, e in tous if i.archive_le is not None],
        corbeille=lister_inventaires(base, corbeille=True),
        fait=MESSAGES.get(fait or ""),
    )


@routeur.get("/app/nouveau")
def nouveau(request: Request, base: SessionBase):
    return page(request, "nouveau.html", maisons=_maisons(request, base))


@routeur.post("/app/nouveau")
def creer(
    request: Request,
    base: SessionBase,
    nom: Annotated[str, Form()] = "",
    maison: Annotated[str, Form()] = "",
):
    try:
        cree = creer_brouillon(base, maison, config_de_la_maison(request.app.state.configs, maison), nom)
    except ERREURS_DE_SERVICE as erreur:
        return page(
            request, "nouveau.html", 422, maisons=_maisons(request, base), erreur=str(erreur), nom=nom, maison=maison,
        )
    return RedirectResponse(f"/app/inventaires/{cree.inventaire_id}/depot", status_code=303)


def _maisons(request: Request, base) -> list:
    return [m for m in configs_disponibles(base, request.app.state.configs) if m.erreur is None]


@routeur.get("/app/inventaires/{inventaire_id}")
def ouvrir(inventaire_id: int, base: SessionBase):
    inventaire = charger_inventaire(base, inventaire_id)
    suite = "depot" if inventaire.statut == "brouillon" else "suivi"
    return RedirectResponse(f"/app/inventaires/{inventaire_id}/{suite}", status_code=303)


# --- dépôt des photos, bouteille par bouteille -----------------------------------------------------


@routeur.get("/app/inventaires/{inventaire_id}/depot")
def depot(request: Request, inventaire_id: int, base: SessionBase):
    """Le dépôt d'un brouillon, ou l'ajout de bouteilles à un inventaire lancé —
    pas à un inventaire clos (lecture seule, 0168)."""
    if charger_inventaire(base, inventaire_id).clos_le is not None:
        return RedirectResponse(f"/app/inventaires/{inventaire_id}/suivi", status_code=303)
    vue = apercu(base, inventaire_id)
    # Clé -> photos déjà reçues (leurs identifiants : la page montre leurs miniatures).
    attente = {b.groupe.cle: [p.id for p in b.photos] for b in vue.bouteilles if b.groupe.cle}
    return page(
        request,
        "depot.html",
        vue=vue,
        attente=json.dumps(attente),
        reduction=REDUCTION_PAR_DEFAUT,
        taille_reduction=TAILLE_REDUCTION,
        taille_max_mo=TAILLE_MAX_OCTETS // (1024 * 1024),
    )


# --- vérifier les bouteilles en attente --------------------------------------------------------


@routeur.get("/app/inventaires/{inventaire_id}/verifier")
def verifier(request: Request, inventaire_id: int, base: SessionBase):
    return page(request, "verifier.html", vue=apercu(base, inventaire_id))


def _en_attente(request: Request, base, inventaire_id: int, action) -> HTMLResponse:
    """Applique une correction aux bouteilles en attente puis les réaffiche ; un
    refus s'affiche au-dessus, avec sa raison."""
    erreur = None
    try:
        action()
    except ERREURS_DE_SERVICE as refus:
        erreur = str(refus)
    return page(request, "_en_attente.html", vue=apercu(base, inventaire_id), erreur=erreur)


@routeur.post("/app/inventaires/{inventaire_id}/verifier/retirer-photo/{photo_id}")
def retirer_photo(request: Request, inventaire_id: int, photo_id: int, base: SessionBase):
    return _en_attente(request, base, inventaire_id, lambda: supprimer_photo(base, inventaire_id, photo_id))


@routeur.post("/app/inventaires/{inventaire_id}/verifier/couper/{photo_id}")
def couper_ici(request: Request, inventaire_id: int, photo_id: int, base: SessionBase):
    return _en_attente(request, base, inventaire_id, lambda: couper(base, inventaire_id, photo_id))


@routeur.post("/app/inventaires/{inventaire_id}/verifier/rattacher/{groupe_id}")
def rattacher_a_la_precedente(request: Request, inventaire_id: int, groupe_id: int, base: SessionBase):
    return _en_attente(request, base, inventaire_id, lambda: rattacher(base, inventaire_id, groupe_id))


@routeur.post("/app/inventaires/{inventaire_id}/verifier/supprimer/{groupe_id}")
def supprimer_bouteille(request: Request, inventaire_id: int, groupe_id: int, base: SessionBase):
    return _en_attente(request, base, inventaire_id, lambda: supprimer_groupe(base, inventaire_id, groupe_id))


@routeur.post("/app/inventaires/{inventaire_id}/verifier/quantite/{groupe_id}")
def quantite(request: Request, inventaire_id: int, groupe_id: int, base: SessionBase,
             quantite: Annotated[str, Form()] = ""):
    def changer():
        if not quantite.strip().isdigit() or int(quantite) < 1:
            raise ModificationRefusee(f"Quantité invalide : « {quantite} » (entier ≥ 1 attendu).")
        quantite_du_groupe(base, inventaire_id, groupe_id, int(quantite))

    return _en_attente(request, base, inventaire_id, changer)


@routeur.post("/app/inventaires/{inventaire_id}/lancer")
async def lancer_l_analyse(request: Request, inventaire_id: int, base: SessionBase, stockage: Stockage):
    # Les quantités affichées partent avec le lancement : une quantité tapée
    # sans avoir quitté son champ n'est jamais perdue.
    saisies = await request.form()
    try:
        for groupe, quantite in zip(saisies.getlist("groupe"), saisies.getlist("quantite"), strict=False):
            if not str(quantite).strip().isdigit() or int(quantite) < 1:
                raise ModificationRefusee(f"Quantité invalide : « {quantite} » (entier ≥ 1 attendu). Rien n'a été lancé.")
            quantite_du_groupe(base, inventaire_id, int(groupe), int(quantite))
        finaliser(base, inventaire_id, stockage)
    except ERREURS_DE_SERVICE as refus:
        return page(request, "_en_attente.html", vue=apercu(base, inventaire_id), erreur=str(refus))
    suivi = f"/app/inventaires/{inventaire_id}/suivi"
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": suivi})
    return RedirectResponse(suivi, status_code=303)


# --- suivi ---------------------------------------------------------------------------------


@routeur.get("/app/inventaires/{inventaire_id}/suivi")
def suivi(request: Request, inventaire_id: int, base: SessionBase, fait: str | None = None):
    from src.web.cycle import MESSAGES

    inventaire = charger_inventaire(base, inventaire_id)
    if inventaire.statut == "brouillon":
        return RedirectResponse(f"/app/inventaires/{inventaire_id}/depot", status_code=303)
    return page(
        request, "suivi.html", inventaire=inventaire, etat=avancement(base, inventaire_id),
        en_attente=apercu(base, inventaire_id).bouteilles, fait=MESSAGES.get(fait or ""),
    )


@routeur.get("/app/inventaires/{inventaire_id}/progression")
def progression(request: Request, inventaire_id: int, base: SessionBase):
    return page(request, "_progression.html", inventaire=charger_inventaire(base, inventaire_id), etat=avancement(base, inventaire_id))


@routeur.post("/app/inventaires/{inventaire_id}/relancer-erreurs")
def relancer(request: Request, inventaire_id: int, base: SessionBase):
    erreur = None
    try:
        reprendre(base, inventaire_id)
    except ERREURS_DE_SERVICE as refus:
        erreur = str(refus)
    return page(
        request, "_progression.html", inventaire=charger_inventaire(base, inventaire_id),
        etat=avancement(base, inventaire_id), erreur=erreur,
    )
