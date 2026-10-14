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
    "nom_vide": "Donnez un nom à la vente : il ne peut pas rester vide. Rien n'a été renommé.",
    "desarchive": "Inventaire sorti des archives.",
    "rouvert": "Inventaire rouvert : il est de nouveau modifiable.",
    "reprise": "Analyse reprise.",
    "restaure": "Inventaire restauré.",
    "excel_refuse": "L'Excel n'est pas encore disponible : chaque bouteille doit d'abord avoir sa ligne (voir ci-dessous).",
    "corbeille": "Inventaire mis à la corbeille.",
    "deja_lancee": "Analyse déjà lancée : plus rien à vérifier. Suivez-la ici.",
    "clos": "Inventaire clos : ses photos ne se modifient plus (rouvrez-le pour en ajouter).",
}


def suivi(inventaire_id: int, fait: str) -> str:
    return f"/app/inventaires/{inventaire_id}/suivi?fait={fait}"


def _geste(request: Request, base, inventaire_id: int, faire, fait: str, retour: str | None = None):
    """Fait le geste puis revient au suivi avec un message ; refusé, la page
    d'erreur dit pourquoi, en clair."""
    try:
        faire()
    except ERREURS_DE_SERVICE as refus:
        return page(request, "erreur.html", 409, message=str(refus), titre="Action impossible",
                    retour=f"/app/inventaires/{inventaire_id}/suivi", libelle_retour="Revenir à l'inventaire")
    return RedirectResponse(retour or suivi(inventaire_id, fait), status_code=303)


@routeur.post("/app/inventaires/{inventaire_id}/renommer")
def renommer_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran,
                          nom: Annotated[str, Form()] = ""):
    if not (nom or "").strip():  # rester sur l'inventaire, le refus en clair (T4-B20)
        return RedirectResponse(suivi(inventaire_id, "nom_vide"), status_code=303)
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
    # « Son analyse s'arrête » seulement si elle tourne encore (T4-D14).
    en_cours = inventaire.extraction == "lancee" and any(b.statut in ("a_extraire", "en_cours") for b in inventaire.bouteilles)
    return page(
        request, "confirmation.html", inventaire=inventaire, action="supprimer",
        titre=f"Mettre « {inventaire.nom} » à la corbeille ?",
        explications=[
            "Son analyse s'arrête ; rien n'est effacé." if en_cours else "Rien n'est effacé.",
            "Il se restaure depuis la corbeille, en bas de l'accueil.",
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
        f"{etat.total} bouteille(s), dont {etat.validees} validée(s).",
        "Ensuite : lecture seule. L'Excel reste téléchargeable ; l'inventaire peut être rouvert.",
    ]
    if etat.ce_qui_n_est_pas_valide():
        explications.insert(1, f"Attention : {etat.ce_qui_n_est_pas_valide()}. Les valider n'est pas obligatoire.")
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
            "Il redevient modifiable. La réouverture est notée dans l'historique.",
        ],
        bouton="Rouvrir l'inventaire", danger=False,
    )


@routeur.post("/app/inventaires/{inventaire_id}/rouvrir")
def rouvrir_l_inventaire(request: Request, inventaire_id: int, base: SessionBase, auteur: AuteurEcran):
    return _geste(request, base, inventaire_id, lambda: rouvrir(base, inventaire_id, auteur), "rouvert")
