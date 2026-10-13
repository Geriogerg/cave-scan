"""La page « Configuration » : la config de chaque maison, éditable sans toucher
au JSON, ou importée telle quelle (session 6 ; decisions.md 0161, 0163).

Comme les autres écrans, chaque route appelle le service de configuration et
affiche son résultat. Chaque action (ajouter une colonne, la déplacer, la
supprimer, vérifier) renvoie TOUTE la config au serveur, qui la réaffiche ;
rien n'est écrit avant « Enregistrer », et rien qui ne soit valide.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from src.api.dependances import Formulaire, SessionBase
from src.config.maison import NOYAU_CANONIQUE, ConfigInvalide
from src.extract.consignes import SYSTEM_PROMPT
from src.extract.schema import CHAMPS_MODELE
from src.services.configuration import (
    config_de_l_instance,
    SOURCES_EDITABLES,
    TYPES_EDITABLES,
    ConfigInchangee,
    ConfigModifieeAilleurs,
    appliquer,
    brut_depuis_formulaire,
    commentaires_de_colonne,
    config_du_fichier,
    edition,
    enregistrer_version,
    exporter_version,
    importer,
    versions_de,
)
from src.web.pages import page

routeur = APIRouter(include_in_schema=False)

LIBELLES_SOURCES = {
    "modele": "Lue par le modèle",
    "modele_best_effort": "Proposée par le modèle, toujours à vérifier",
    "expert": "Saisie par l'expert (jamais envoyée au modèle)",
    "systeme": "Calculée par l'outil (jamais envoyée au modèle)",
}
LIBELLES_TYPES = {"texte": "Texte", "liste": "Liste de valeurs", "nombre": "Nombre"}


def _contexte_edition(request: Request, base, nom: str, vue, **messages) -> dict:
    return dict(
        vue=vue,
        nom=nom,
        versions=versions_de(base, vue.active.config.maison),
        sources=[(s, LIBELLES_SOURCES[s]) for s in SOURCES_EDITABLES],
        types=[(t, LIBELLES_TYPES[t]) for t in TYPES_EDITABLES],
        noyau=NOYAU_CANONIQUE,
        commentaires_de_colonne=commentaires_de_colonne,
        consignes=SYSTEM_PROMPT,
        champs_toujours_lus=[c for c in CHAMPS_MODELE if c not in ("champs_a_verifier", "notes")],
        **messages,
    )


def _afficher(request: Request, base, nom: str, vue, statut: int = 200, **messages):
    """La page entière, ou seulement l'éditeur pour une action HTMX."""
    gabarit = "_config_editeur.html" if request.headers.get("HX-Request") else "configuration_maison.html"
    return page(request, gabarit, statut, **_contexte_edition(request, base, nom, vue, **messages))


# --- liste des maisons et import ------------------------------------------------------------


@routeur.get("/app/configuration")
def liste(request: Request, base: SessionBase):
    """LA configuration de l'instance (decisions.md 0171) ; à défaut, l'import."""
    active = config_de_l_instance(request.app.state.configs)
    if active is not None:
        return RedirectResponse(f"/app/configuration/{active.fichier.stem}", status_code=303)
    return page(request, "configuration.html")


@routeur.post("/app/configuration/importer")
async def importer_un_fichier(
    request: Request, base: SessionBase, fichier: Annotated[UploadFile, File()]
):
    contenu = await fichier.read()
    try:
        texte = contenu.decode("utf-8-sig")
        # Le fichier importé devient la nouvelle version de LA configuration de
        # l'application, quel que soit le nom de maison qu'il porte (0171).
        active = config_de_l_instance(request.app.state.configs)
        if active is not None:
            try:
                brut = json.loads(texte)
            except ValueError:
                brut = None  # illisible : la validation dira où
            if isinstance(brut, dict):
                brut["maison"] = active.config.maison
                texte = json.dumps(brut, ensure_ascii=False, indent=2)
        enregistree = importer(base, request.app.state.configs, texte, fichier.filename or "")
    except UnicodeDecodeError:
        erreurs = [f"« {fichier.filename} » n'est pas un fichier texte JSON (UTF-8 attendu)."]
    except ConfigInvalide as refus:
        erreurs = refus.erreurs
    except ConfigInchangee as refus:  # le fichier qu'on vient d'exporter : rien à faire
        return page(request, "configuration.html", info=f"« {fichier.filename} » : {refus}")
    else:
        cible = f"/app/configuration/{enregistree.fichier.stem}?enregistree={enregistree.version}"
        return RedirectResponse(cible, status_code=303)
    return page(request, "configuration.html", 422, erreurs=erreurs, importe=fichier.filename)


# --- une maison ---------------------------------------------------------------------------------


@routeur.get("/app/configuration/{nom}")
def ouvrir(request: Request, nom: str, base: SessionBase, enregistree: Annotated[int | None, Query()] = None):
    vue = edition(config_du_fichier(request.app.state.configs, nom))
    fait = None
    if enregistree is not None:
        fait = (
            f"Version {enregistree} enregistrée : elle s'applique aux prochains inventaires. "
            f"Les inventaires déjà créés gardent la leur."
        )
    return _afficher(request, base, nom, vue, fait=fait)


@routeur.post("/app/configuration/{nom}")
def agir(request: Request, nom: str, base: SessionBase, champs: Formulaire):
    active = config_du_fichier(request.app.state.configs, nom)
    brut = brut_depuis_formulaire(champs)
    action = champs.get("action", "")
    if action != "enregistrer":
        verifier = action == "verifier"
        vue = edition(active, brut if verifier else appliquer(brut, action), verifier=verifier)
        statut = 422 if vue.erreurs else 200
        fait = "Configuration valide : vous pouvez l'enregistrer." if verifier and not vue.erreurs else None
        return _afficher(request, base, nom, vue, statut, fait=fait)

    version_vue = champs.get("version_vue", "")
    try:
        enregistree = enregistrer_version(
            base, request.app.state.configs, active.config.maison, brut,
            int(version_vue) if version_vue.isdigit() else None,
        )
    except ConfigInvalide:
        return _afficher(request, base, nom, edition(active, brut, verifier=True), 422)
    except ConfigModifieeAilleurs as refus:
        return _afficher(request, base, nom, edition(active, brut), 409, erreur=str(refus))
    except ConfigInchangee as refus:
        return _afficher(request, base, nom, edition(active, brut), info=str(refus))
    cible = f"/app/configuration/{enregistree.fichier.stem}?enregistree={enregistree.version}"
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": cible})
    return RedirectResponse(cible, status_code=303)


@routeur.get("/app/configuration/{nom}/export")
def exporter(request: Request, nom: str, base: SessionBase, numero: Annotated[int | None, Query()] = None):
    active = config_du_fichier(request.app.state.configs, nom)
    nom_fichier, texte = exporter_version(base, request.app.state.configs, active.config.maison, numero)
    return Response(
        texte.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{nom_fichier}"'},
    )
