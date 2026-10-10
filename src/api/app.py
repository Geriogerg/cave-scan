"""L'application FastAPI (decisions.md 0118).

`creer_app` assemble les routeurs ; chacun passe par la dépendance `acces`,
point d'accroche de la future connexion. Aucune photo n'est servie comme un
dossier statique : seulement par la route qui vérifie son inventaire.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from src.api import erreurs
from src.api.dependances import acces
from src.api.routes import bouteilles, depot, inventaires, maisons, photos
from src.donnees.base import RACINE, creer_moteur, dossier_stockage, migrer, url_de_base

DOSSIER_CONFIGS = RACINE / "config" / "maisons"


def creer_app(
    base: str | Path | None = None,
    stockage: Path | None = None,
    configs: Path = DOSSIER_CONFIGS,
) -> FastAPI:
    url = url_de_base(base)
    migrer(url)
    moteur = creer_moteur(url)

    @asynccontextmanager
    async def cycle_de_vie(_app: FastAPI) -> AsyncIterator[None]:
        yield
        moteur.dispose()

    app = FastAPI(
        title="cave-scan",
        version="session 3",
        lifespan=cycle_de_vie,
        description=(
            "Catalogage de bouteilles à partir de photos d'étiquettes : créer un inventaire "
            "avec ses photos, lancer l'extraction (exécutée par le worker), relire, corriger, "
            "valider, exporter. Les actions de l'expert demandent l'en-tête `X-Auteur`."
        ),
    )
    app.state.moteur = moteur
    app.state.stockage = dossier_stockage(stockage)
    app.state.configs = Path(configs)
    from src.web import pages  # les écrans : mêmes services, même contrôle d'accès

    erreurs.installer(app, page_erreur=lambda request, statut, message: pages.page(request, "erreur.html", statut, message=message))
    for module in (maisons, inventaires, depot, bouteilles, photos):
        app.include_router(module.routeur, dependencies=[Depends(acces)])
    app.include_router(pages.routeur, dependencies=[Depends(acces)])
    # Feuille de style et scripts seulement : les photos ne sont JAMAIS servies
    # comme un dossier statique (decisions.md 0117).
    app.mount("/static", StaticFiles(directory=pages.DOSSIER / "static"), name="static")
    return app
