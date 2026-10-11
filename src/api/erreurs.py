"""Un seul format d'erreur, lisible par l'expert : `{code, message, detail}`.

Chaque exception des services est traduite ICI, une fois pour toutes ; les
routes ne rattrapent rien (decisions.md 0118). Les messages des garde-fous —
nombre impair de photos, valeur hors liste, bouteille en erreur… — sont déjà
écrits pour l'expert dans les services : on les transmet tels quels.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException

from src.config.maison import ConfigInvalide
from src.io.photos import PhotosInvalides
from src.services.cas_particuliers import ActionRefusee
from src.services.configuration import ConfigIntrouvable
from src.services.cycle_de_vie import CycleRefuse
from src.services.depot import DepotFerme, ModificationRefusee
from src.services.envoi import EnvoiRefuse, PhotoIntrouvable
from src.services.extraction import BouteilleIntrouvable, BouteilleOccupee
from src.services.inventaires import InventaireClos, InventaireIntrouvable
from src.services.pilotage import LancementRefuse
from src.services.relecture import (
    CorrectionRefusee,
    ModificationConcurrente,
    SaisiesRefusees,
    ValidationRefusee,
)

journal = logging.getLogger("cave_scan.api")

# Exception de service -> (statut HTTP, code stable pour les écrans).
TRADUCTIONS: list[tuple[type[Exception], int, str]] = [
    (EnvoiRefuse, 422, "envoi_refuse"),
    (PhotosInvalides, 422, "photos_invalides"),
    (CorrectionRefusee, 422, "saisie_refusee"),
    (SaisiesRefusees, 422, "saisie_refusee"),
    (ConfigInvalide, 422, "config_invalide"),
    (ValidationRefusee, 409, "validation_refusee"),
    (ModificationConcurrente, 409, "modification_concurrente"),
    (ActionRefusee, 409, "action_refusee"),
    (CycleRefuse, 409, "action_refusee"),
    (InventaireClos, 409, "inventaire_clos"),
    (LancementRefuse, 409, "lancement_refuse"),
    (DepotFerme, 409, "depot_ferme"),
    (ModificationRefusee, 422, "modification_refusee"),
    (BouteilleOccupee, 409, "bouteille_occupee"),
    (InventaireIntrouvable, 404, "introuvable"),
    (BouteilleIntrouvable, 404, "introuvable"),
    (PhotoIntrouvable, 404, "introuvable"),
    (ConfigIntrouvable, 404, "introuvable"),
    # Pas `LookupError` : un KeyError de programmation deviendrait un faux 404.
]

MESSAGES_HTTP = {
    404: ("introuvable", "Cette adresse n'existe pas."),
    405: ("methode_refusee", "Cette action n'est pas possible à cette adresse."),
}


def erreur(statut: int, code: str, message: str, detail: object = None) -> JSONResponse:
    return JSONResponse(status_code=statut, content={"code": code, "message": message, "detail": detail})


PageErreur = Callable[[Request, int, str], Response]


def installer(app: FastAPI, page_erreur: PageErreur | None = None) -> None:
    """`page_erreur` : pour les écrans (adresses /app), la même erreur rendue en
    page HTML lisible plutôt qu'en JSON."""

    def repondre(request: Request, statut: int, code: str, message: str, detail: object = None) -> Response:
        if page_erreur is not None and request.url.path.startswith("/app"):
            return page_erreur(request, statut, message)
        return erreur(statut, code, message, detail)

    for classe, statut, code in TRADUCTIONS:

        def gerer(request: Request, exception: Exception, statut: int = statut, code: str = code):
            # Refus par champ (validation) ou liste des changements faits ailleurs.
            detail = getattr(exception, "refus", None) or getattr(exception, "changements", None)
            return repondre(request, statut, code, str(exception).strip("'\""), detail)

        app.add_exception_handler(classe, gerer)

    @app.exception_handler(RequestValidationError)
    def requete_invalide(request: Request, exception: RequestValidationError):
        champs = [
            {"champ": ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path", "header")),
             "probleme": e["msg"]}
            for e in exception.errors()
        ]
        noms = ", ".join(c["champ"] for c in champs if c["champ"]) or "la requête"
        return repondre(request, 422, "requete_invalide", f"Saisie incomplète ou invalide : {noms}.", champs)

    @app.exception_handler(HTTPException)
    def http(request: Request, exception: HTTPException):
        code, message = MESSAGES_HTTP.get(exception.status_code, ("erreur", str(exception.detail)))
        return repondre(request, exception.status_code, code, message)

    @app.exception_handler(Exception)
    def imprevue(request: Request, exception: Exception):
        journal.exception("Erreur imprévue")
        return repondre(request, 500, "erreur_interne", "Erreur inattendue du serveur : l'opération n'a pas abouti.")
