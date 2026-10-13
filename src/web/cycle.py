"""Les écrans du cycle de vie d'un inventaire (session 6 ; decisions.md 0168) :
renommer, archiver, mettre à la corbeille et restaurer, clore et rouvrir,
mettre l'analyse en pause et la reprendre.

Chaque route appelle le service et affiche ; les gestes lourds (corbeille,
clôture, réouverture) passent par une page de confirmation qui dit ce qui va se
passer. Un refus s'affiche en français, jamais comme un message technique.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse, Response

from src.api.dependances import AuteurEcran, SessionBase
from src.services.cycle_de_vie import (
    archiver,
    bilan,
    clore,
    desarchiver,
    renommer,
    restaurer,
    rouvrir,
    supprimer,
)
from src.services.inventaires import charger_inventaire
from src.services.pilotage import annuler, lancer
from src.web.pages import ERREURS_DE_SERVICE, page

routeur = APIRouter(include_in_schema=False)

# Après un geste, un message court (jamais un texte arbitraire dans l'adresse).
MESSAGES = {
    "renomme": "Inventaire renommé.",
    "archive": "Inventaire archivé : il est rangé dans « Archives », sur l'accueil.",
    "desarchive": "Inventaire sorti des archives.",
    "rouvert": "Inventaire rouvert : il est de nouveau modifiable.",
    "reprise": "Analyse reprise.",
    "restaure": "Inventaire restauré.",
    "corbeille": "Inventaire mis à la corbeille. Il se restaure depuis la corbeille, en bas de cette page.",
}


def suivi(inventaire_id: int, fait: str) -> str:
    return f"/app/inventaires/{inventaire_id}/suivi?fait={fait}"


def _geste(request: Request, base, inventaire_id: int, faire, fait: str, retour: str | None = None):
    """Fait le geste puis revient au suivi avec un message ; refusé, la page
    d'erreur dit pourquoi, en clair."""
    try:
        faire()
    except ERREURS_DE_SERVICE as refus:
        return page(request, "erreur.html", 409, message=str(refus),
                    retour=f"/app/inventaires/{inventaire_id}/suivi", libelle_retour="Revenir à l'inventaire")
    return RedirectResponse(retour or suivi(inventaire_id, fait), status_code=303)


@routeur.post("/app/inventaires/{inventaire_id}/renommer")
def renommer_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran,
                          nom: Annotated[str, Form()] = ""):
    return _geste(request, base, inventaire_id, lambda: renommer(base, inventaire_id, nom, auteur), "renomme")


@routeur.post("/app/inventaires/{inventaire_id}/archiver")
def archiver_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran):
    return _geste(request, base, inventaire_id, lambda: archiver(base, inventaire_id, auteur), "archive")


@routeur.post("/app/inventaires/{inventaire_id}/desarchiver")
def desarchiver_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran):
    return _geste(request, base, inventaire_id, lambda: desarchiver(base, inventaire_id, auteur), "desarchive")


@routeur.post("/app/inventaires/{inventaire_id}/pause")
def mettre_en_pause(request: Request, inventaire_id: int, base: SessionBase):
    return _geste(request, base, inventaire_id, lambda: annuler(base, inventaire_id), "pause")


@routeur.post("/app/inventaires/{inventaire_id}/reprendre-analyse")
def reprendre_l_analyse(request: Request, inventaire_id: int, base: SessionBase):
    return _geste(request, base, inventaire_id, lambda: lancer(base, inventaire_id), "reprise")


# --- gestes confirmés : corbeille, clôture, réouverture -----------------------------------------


@routeur.get("/app/inventaires/{inventaire_id}/supprimer")
def confirmer_la_suppression(request: Request, inventaire_id: int, base: SessionBase):
    inventaire = charger_inventaire(base, inventaire_id)
    etat = bilan(base, inventaire_id)
    return page(
        request, "confirmation.html", inventaire=inventaire, action="supprimer",
        titre=f"Mettre « {inventaire.nom} » à la corbeille ?",
        explications=[
            "Il disparaît de la liste des inventaires et son analyse s'arrête.",
            f"Rien n'est effacé : ses {etat.total} bouteille(s), leurs photos, les lectures du modèle et "
            f"vos corrections restent conservées.",
            "Il se restaure à tout moment depuis la corbeille, en bas de l'accueil.",
        ],
        bouton="Mettre à la corbeille", danger=True,
    )


@routeur.post("/app/inventaires/{inventaire_id}/supprimer")
def supprimer_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran):
    return _geste(request, base, inventaire_id, lambda: supprimer(base, inventaire_id, auteur), "corbeille",
                  retour="/app?fait=corbeille")


@routeur.post("/app/inventaires/{inventaire_id}/restaurer")
def restaurer_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran):
    return _geste(request, base, inventaire_id, lambda: restaurer(base, inventaire_id, auteur), "restaure")


@routeur.get("/app/inventaires/{inventaire_id}/clore")
def confirmer_la_cloture(request: Request, inventaire_id: int, base: SessionBase):
    inventaire = charger_inventaire(base, inventaire_id)
    etat = bilan(base, inventaire_id)
    if not etat.chaque_bouteille_a_sa_ligne:
        return page(request, "erreur.html", 409,
                    message=f"L'inventaire ne peut pas encore être clos : {etat.ce_qui_manque()}.")
    explications = [
        f"{etat.total} bouteille(s), dont {etat.validees} validée(s) une par une.",
        "Ensuite, l'inventaire est en lecture seule : plus de correction, d'ajout ni de retrait de bouteille. "
        "L'Excel reste téléchargeable, et l'inventaire peut être rouvert.",
    ]
    if etat.ce_qui_n_est_pas_valide():
        explications.insert(1, f"Attention : {etat.ce_qui_n_est_pas_valide()}. Valider reste facultatif ; "
                               f"ce qui ne l'est pas sera noté dans la trace de la clôture.")
    return page(
        request, "confirmation.html", inventaire=inventaire, action="clore",
        titre=f"Clore « {inventaire.nom} » ?", explications=explications,
        bouton="Clore l'inventaire" + (" quand même" if etat.ce_qui_n_est_pas_valide() else ""), danger=False,
    )


@routeur.post("/app/inventaires/{inventaire_id}/clore")
def clore_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran):
    return _geste(request, base, inventaire_id, lambda: clore(base, inventaire_id, auteur), "clos")


@routeur.get("/app/inventaires/{inventaire_id}/rouvrir")
def confirmer_la_reouverture(request: Request, inventaire_id: int, base: SessionBase):
    inventaire = charger_inventaire(base, inventaire_id)
    return page(
        request, "confirmation.html", inventaire=inventaire, action="rouvrir",
        titre=f"Rouvrir « {inventaire.nom} » ?",
        explications=[
            "Il redevient modifiable : corrections, ajout et retrait de bouteilles.",
            "La réouverture est notée dans l'historique de l'inventaire, avec votre nom.",
        ],
        bouton="Rouvrir l'inventaire", danger=False,
    )


@routeur.post("/app/inventaires/{inventaire_id}/rouvrir")
def rouvrir_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran):
    return _geste(request, base, inventaire_id, lambda: rouvrir(base, inventaire_id, auteur), "rouvert")
