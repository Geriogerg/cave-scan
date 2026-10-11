"""Dépôt des photos, bouteille par bouteille : créer le brouillon, envoyer une
photo à la fois pour SA bouteille, corriger les bouteilles en attente, lancer
leur analyse — aussi pour ajouter des bouteilles après le lancement
(decisions.md 0126-0134, 0166, 0167).

Mêmes fonctions de service que les pages de l'application web.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from src.api import schemas
from src.api.dependances import SessionBase, Stockage
from src.services.depot import (
    ajouter_photo,
    apercu,
    couper,
    creer_brouillon,
    definir_quantite,
    finaliser,
    quantite_du_groupe,
    rattacher,
    signatures_deja_recues,
    supprimer_groupe,
    supprimer_photo,
)
from src.services.envoi import config_de_la_maison
from src.services.pilotage import avancement

routeur = APIRouter(tags=["Dépôt des photos"], responses=schemas.REPONSES_ERREUR)


@routeur.post("/brouillons", status_code=201, response_model=schemas.BrouillonReponse, summary="Créer un inventaire en brouillon")
def creer(demande: schemas.BrouillonDemande, base: SessionBase, request: Request):
    cree = creer_brouillon(base, demande.maison, config_de_la_maison(request.app.state.configs, demande.maison), demande.nom)
    return schemas.BrouillonReponse(
        id=cree.inventaire_id,
        config_numero=cree.config_numero,
        nouvelle_config=cree.nouvelle_config,
        avertissements=cree.avertissements,
    )


@routeur.post(
    "/inventaires/{inventaire_id}/photos",
    response_model=schemas.PhotoRecueReponse,
    summary="Envoyer UNE photo d'une bouteille (idempotent)",
)
def envoyer(
    inventaire_id: int,
    base: SessionBase,
    stockage: Stockage,
    fichier: Annotated[UploadFile, File(description="La photo, JPEG, PNG ou HEIC.")],
    bouteille: Annotated[str, Form(max_length=64, description="Clé de la bouteille, donnée par l'appareil.")],
    numero: Annotated[int, Form(ge=1, description="Numéro de la bouteille dans l'ordre de prise de vue.")],
    quantite: Annotated[int | None, Form(ge=1, description="« × N » saisi à la capture.")] = None,
    signature: Annotated[
        str | None, Form(max_length=300, description="Signature du fichier d'origine : nom|taille|date.")
    ] = None,
):
    recue = ajouter_photo(
        base, inventaire_id, fichier.file, fichier.filename or "photo", stockage,
        bouteille=bouteille, numero=numero, quantite=quantite, signature=signature,
    )
    return schemas.depuis_photo_recue(recue)


@routeur.post(
    "/inventaires/{inventaire_id}/photos/deja-recues",
    response_model=schemas.SignaturesReponse,
    summary="Quels fichiers sont déjà arrivés (reprise après coupure)",
)
def deja_recues(inventaire_id: int, demande: schemas.SignaturesDemande, base: SessionBase):
    return schemas.SignaturesReponse(deja_recues=signatures_deja_recues(base, inventaire_id, demande.signatures))


@routeur.get("/inventaires/{inventaire_id}/apercu", response_model=schemas.ApercuReponse, summary="Les bouteilles en attente")
def voir(inventaire_id: int, base: SessionBase):
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.delete(
    "/inventaires/{inventaire_id}/photos/{photo_id}", response_model=schemas.ApercuReponse, summary="Retirer une photo"
)
def supprimer(inventaire_id: int, photo_id: int, base: SessionBase):
    supprimer_photo(base, inventaire_id, photo_id)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.post(
    "/inventaires/{inventaire_id}/photos/{photo_id}/couper",
    response_model=schemas.ApercuReponse,
    summary="Nouvelle bouteille à partir de cette photo",
)
def couper_le_groupe(inventaire_id: int, photo_id: int, base: SessionBase):
    couper(base, inventaire_id, photo_id)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.post(
    "/inventaires/{inventaire_id}/groupes/{groupe_id}/rattacher",
    response_model=schemas.ApercuReponse,
    summary="Rattacher à la bouteille précédente",
)
def rattacher_le_groupe(inventaire_id: int, groupe_id: int, base: SessionBase):
    rattacher(base, inventaire_id, groupe_id)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.put(
    "/inventaires/{inventaire_id}/groupes/{groupe_id}/quantite",
    response_model=schemas.ApercuReponse,
    summary="Quantité d'une bouteille en attente",
)
def quantite_en_attente(inventaire_id: int, groupe_id: int, demande: schemas.QuantiteDeBouteille, base: SessionBase):
    quantite_du_groupe(base, inventaire_id, groupe_id, demande.quantite)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.put(
    "/inventaires/{inventaire_id}/bouteilles-en-cours/{cle}/quantite",
    response_model=schemas.ApercuReponse,
    summary="Quantité de la bouteille en cours (par sa clé)",
)
def quantite_par_cle(inventaire_id: int, cle: str, demande: schemas.QuantiteDeBouteille, base: SessionBase):
    definir_quantite(base, inventaire_id, cle, demande.quantite)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.delete(
    "/inventaires/{inventaire_id}/groupes/{groupe_id}",
    response_model=schemas.ApercuReponse,
    summary="Supprimer une bouteille en attente et ses photos",
)
def supprimer_le_groupe(inventaire_id: int, groupe_id: int, base: SessionBase):
    supprimer_groupe(base, inventaire_id, groupe_id)
    return schemas.depuis_apercu(apercu(base, inventaire_id))


@routeur.post(
    "/inventaires/{inventaire_id}/finaliser",
    response_model=schemas.Finalisation,
    summary="Lancer l'analyse des bouteilles en attente (aussi après un premier lancement)",
)
def lancer_l_analyse(inventaire_id: int, base: SessionBase, stockage: Stockage):
    nombre = finaliser(base, inventaire_id, stockage)
    return schemas.Finalisation(nb_bouteilles=nombre, progression=schemas.depuis_avancement(avancement(base, inventaire_id)))
