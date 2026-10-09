"""Maisons et leur config active."""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.api import schemas
from src.api.dependances import SessionBase
from src.services.envoi import configs_disponibles

routeur = APIRouter(prefix="/maisons", tags=["Maisons"])


@routeur.get("", response_model=list[schemas.Maison], summary="Lister les maisons et leur config active")
def lister(base: SessionBase, request: Request):
    return [schemas.depuis_config(c) for c in configs_disponibles(base, request.app.state.configs)]
