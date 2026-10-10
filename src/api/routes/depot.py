"""Dépôt des photos dans un brouillon : créer, envoyer une photo à la fois,
corriger l'ordre, voir les paires, finaliser (decisions.md 0126-0134).

Mêmes fonctions de service que les pages de l'application web.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from src.api import schemas
from src.api.dependances import SessionBase, Stockage
from src.services.depot import (
    ajouter_photo,
    apercu,
    creer_brouillon,
    deplacer_photo,
    finaliser,
    inverser_paire,
    retrier,
    signatures_deja_recues,
    supprimer_photo,
)
from src.services.envoi import config_de_la_maison
from src.services.pilotage import avancement

routeur = APIRouter(tags=["Dépôt des photos"], responses=schemas.REPONSES_ERREUR)


@routeur.post("/brouillons", status_code=201, response_model=schemas.BrouillonReponse, summary="Créer un inventaire en brouillon")
def creer(demande: schemas.BrouillonDemande, base: SessionBase, request: Request):
    cree = creer_brouillon(
        base, demande.maison, config_de_la_maison(request.app.state.configs, demande.maison), demande.nom, demande.sans_contre
    )
    return schemas.BrouillonReponse(
        id=cree.inventaire_id,
        config_numero=cree.config_numero,
        nouvelle_config=cree.nouvelle_config,
        avertissements=cree.avertissements,
    )


@routeur.post(
    "/inventaires/{inventaire_id}/photos",
    response_model=schemas.PhotoRecueReponse,
    summary="Envoyer UNE photo (idempotent)",
)
def envoyer(
    inventaire_id: int,
    base: SessionBase,
    stockage: Stockage,
    fichier: Annotated[UploadFile, File(description="La photo, JPEG ou PNG.")],
    prise_de_vue: Annotated[
        datetime | None, Form(description="Date de prise de vue lue AVANT toute réduction (ISO 8601).")
    ] = None,
    signature: Annotated[
        str | None, Form(max_length=300, description="Signature du fichier d'origine : nom|taille|date.")
    ] = None,
):
    recue = ajouter_photo(
        base, inventaire_id, fichier.file, fichier.filename or "photo", stockage, prise_de_vue, signature
    )
    return schemas.depuis_photo_recue(recue)


@routeur.post(
    "/inventaires/{inventaire_id}/photos/deja-recues",
    response_model=schemas.SignaturesReponse,
    summary="Quels fichiers sont déjà arrivés (reprise après coupure)",
)
def deja_recues(inventaire_id: int, demande: schemas.SignaturesDemande, base: SessionBase):
    return schemas.SignaturesReponse(deja_recues=signatures_deja_recues(base, inventaire_id, demande.signatures))


@routeur.get("/inventaires/{inventaire_id}/apercu", response_model=schemas.ApercuReponse, summary="Les paires et les anomalies")
def voir(inventaire_id: int, base: SessionBase):
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.delete(
    "/inventaires/{inventaire_id}/photos/{photo_id}", response_model=schemas.ApercuReponse, summary="Retirer une photo"
)
def supprimer(inventaire_id: int, photo_id: int, base: SessionBase):
    supprimer_photo(base, inventaire_id, photo_id)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.post(
    "/inventaires/{inventaire_id}/photos/{photo_id}/deplacer",
    response_model=schemas.ApercuReponse,
    summary="Déplacer une photo",
)
def deplacer(inventaire_id: int, photo_id: int, demande: schemas.DeplacementDemande, base: SessionBase):
    deplacer_photo(base, inventaire_id, photo_id, demande.position)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.post(
    "/inventaires/{inventaire_id}/paires/{numero}/inverser",
    response_model=schemas.ApercuReponse,
    summary="Inverser étiquette et contre-étiquette d'une paire",
)
def inverser(inventaire_id: int, numero: int, base: SessionBase):
    inverser_paire(base, inventaire_id, numero)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.post(
    "/inventaires/{inventaire_id}/retrier", response_model=schemas.ApercuReponse, summary="Revenir à l'ordre automatique"
)
def remettre_en_ordre(inventaire_id: int, base: SessionBase):
    retrier(base, inventaire_id)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.post(
    "/inventaires/{inventaire_id}/finaliser",
    response_model=schemas.Finalisation,
    summary="Lancer l'analyse : former les bouteilles et démarrer l'extraction",
)
def lancer_l_analyse(inventaire_id: int, base: SessionBase, stockage: Stockage):
    nombre = finaliser(base, inventaire_id, stockage)
    return schemas.Finalisation(nb_bouteilles=nombre, progression=schemas.depuis_avancement(avancement(base, inventaire_id)))
