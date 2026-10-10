"""Photos : servies une à une, après vérification de leur inventaire, sans métadonnées."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from src.api import schemas
from src.api.dependances import SessionBase, Stockage
from src.services.envoi import photo_a_servir

routeur = APIRouter(prefix="/inventaires/{inventaire_id}/photos", tags=["Photos"], responses=schemas.REPONSES_ERREUR)


@routeur.get(
    "/{photo_id}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}, "description": "La photo, en JPEG, sans métadonnées."}},
    summary="Une photo (réduite par défaut)",
)
def servir(
    inventaire_id: int,
    photo_id: int,
    base: SessionBase,
    stockage: Stockage,
    taille: Annotated[Literal["miniature", "reduite", "originale"], Query()] = "reduite",
):
    contenu = photo_a_servir(base, stockage, inventaire_id, photo_id, taille)
    return Response(contenu, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
