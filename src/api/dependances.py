"""Dépendances communes aux routes : session, stockage, accès, auteur.

`acces` et `auteur` sont les deux points d'accroche de la connexion (session 7) :
aujourd'hui `acces` ne vérifie rien (le serveur n'écoute qu'en local) et
l'auteur est déclaré dans l'en-tête `X-Auteur`. Les remplacer suffira : aucune
route n'aura à être réécrite (decisions.md 0118).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from src.donnees.modeles import FicheBouteille
from src.services.consultation import bouteille_de


def session(request: Request) -> Iterator[Session]:
    """Une session par requête, toujours fermée."""
    with Session(request.app.state.moteur, expire_on_commit=False) as ouverte:
        yield ouverte


def stockage(request: Request) -> Path:
    return request.app.state.stockage


def acces() -> None:
    """Contrôle d'accès de toutes les routes — vide tant que la connexion
    n'existe pas (session 7)."""


def auteur(
    x_auteur: Annotated[
        str, Header(min_length=1, max_length=200, description="Qui agit : tracé dans l'historique.")
    ],
) -> str:
    return x_auteur.strip()


SessionBase = Annotated[Session, Depends(session)]
Stockage = Annotated[Path, Depends(stockage)]
Auteur = Annotated[str, Depends(auteur)]


def bouteille_de_l_inventaire(inventaire_id: int, bouteille_id: int, base: SessionBase) -> FicheBouteille:
    """La bouteille demandée, refusée si elle n'appartient pas à l'inventaire."""
    return bouteille_de(base, inventaire_id, bouteille_id)


BouteilleVerifiee = Annotated[FicheBouteille, Depends(bouteille_de_l_inventaire)]
