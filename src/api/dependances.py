"""Dépendances communes aux routes : session, stockage, accès, auteur.

`acces` et `auteur` sont les deux points d'accroche de la connexion (session 7) :
aujourd'hui `acces` ne vérifie rien (le serveur n'écoute qu'en local) et
l'auteur est déclaré dans l'en-tête `X-Auteur` (API) ou configuré par défaut
(`CAVE_SCAN_AUTEUR`, écrans). Les remplacer suffira : aucune route n'aura à être
réécrite (decisions.md 0118, 0150).
"""

from __future__ import annotations

import os
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


VARIABLE_AUTEUR = "CAVE_SCAN_AUTEUR"
AUTEUR_PAR_DEFAUT = "Expert"


def auteur_des_ecrans() -> str:
    """Qui corrige depuis les écrans : l'auteur configuré par défaut, en
    attendant la connexion (guide de session 5, §7)."""
    return (os.environ.get(VARIABLE_AUTEUR) or "").strip()[:200] or AUTEUR_PAR_DEFAUT


async def formulaire(request: Request) -> dict[str, str]:
    """Les champs d'un formulaire dont les noms viennent de la config de la
    maison (relecture) : lus tels quels, fichiers exclus."""
    donnees = await request.form()
    return {cle: valeur for cle, valeur in donnees.items() if isinstance(valeur, str)}


SessionBase = Annotated[Session, Depends(session)]
Stockage = Annotated[Path, Depends(stockage)]
Auteur = Annotated[str, Depends(auteur)]
AuteurEcran = Annotated[str, Depends(auteur_des_ecrans)]
Formulaire = Annotated[dict[str, str], Depends(formulaire)]


def bouteille_de_l_inventaire(inventaire_id: int, bouteille_id: int, base: SessionBase) -> FicheBouteille:
    """La bouteille demandée, refusée si elle n'appartient pas à l'inventaire."""
    return bouteille_de(base, inventaire_id, bouteille_id)


BouteilleVerifiee = Annotated[FicheBouteille, Depends(bouteille_de_l_inventaire)]
