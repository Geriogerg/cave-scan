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
from src.config.maison import LIBELLES_SOURCES, LIBELLES_TYPES, NOYAU_CANONIQUE, ConfigInvalide
from src.extract.consignes import CONSIGNES_MODIFIABLES, REGLES_FIXES_DEBUT, REGLES_FIXES_FIN
from src.services.configuration import (
    _identifiant,
    config_de_l_instance,
    configurations_en_concurrence,
    consignes_modifiees,
    message_plusieurs_configurations,
    creer_configuration,
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
    reprises,
    versions_de,
)
from src.web.pages import page

routeur = APIRouter(include_in_schema=False)


def _contexte_edition(request: Request, base, nom: str, vue, **messages) -> dict:
    return dict(
        vue=vue,
        nom=nom,
        versions=versions_de(base, vue.active.config.maison),
        reprises=reprises(versions_de(base, vue.active.config.maison)),
        sources=[(s, LIBELLES_SOURCES[s]) for s in SOURCES_EDITABLES],
        types=[(t, LIBELLES_TYPES[t]) for t in TYPES_EDITABLES],
        noyau=NOYAU_CANONIQUE,
        commentaires_de_colonne=commentaires_de_colonne,
        identifiant=_identifiant,
        consignes=vue.brut.get("consignes") or CONSIGNES_MODIFIABLES,
        regles_fixes=(REGLES_FIXES_DEBUT, REGLES_FIXES_FIN),
        consignes_d_origine=not vue.brut.get("consignes"),
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
    return page(request, "configuration.html", plusieurs=_plusieurs(request))


def _plusieurs(request: Request) -> str | None:
    """Plusieurs configurations, aucune désignée : la raison, en rouge (0182)."""
    concurrentes = configurations_en_concurrence(request.app.state.configs)
    return message_plusieurs_configurations(concurrentes) if concurrentes else None


@routeur.post("/app/configuration/creer")
def creer(request: Request, base: SessionBase):
    """Créer la configuration à la main, sans JSON (decisions.md 0172)."""
    try:
        creee = creer_configuration(base, request.app.state.configs)
    except ConfigInvalide as refus:
        return page(request, "configuration.html", 409, erreurs=refus.erreurs, importe=None)
    return RedirectResponse(f"/app/configuration/{creee.fichier.stem}?creee=1", status_code=303)


@routeur.post("/app/configuration/importer")
async def importer_un_fichier(
    request: Request, base: SessionBase, fichier: Annotated[UploadFile, File()]
):
    contenu = await fichier.read()
    # Le fichier importé devient la nouvelle version de LA configuration de
    # l'application, quel que soit le nom de maison qu'il porte (0171).
    active = config_de_l_instance(request.app.state.configs)
    if active is None and _plusieurs(request):  # un fichier de plus ne lèverait pas l'ambiguïté (0182)
        return page(request, "configuration.html", 409, plusieurs=_plusieurs(request))
    try:
        texte = contenu.decode("utf-8-sig")
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
        if active is not None:
            return _afficher(request, base, active.fichier.stem, edition(active),
                             info=f"« {fichier.filename} » ne change rien à la version active : rien n'a été enregistré.")
        return page(request, "configuration.html", info=f"« {fichier.filename} » : {refus}")
    else:
        cible = f"/app/configuration/{enregistree.fichier.stem}?enregistree={enregistree.version}"
        return RedirectResponse(cible, status_code=303)
    if active is not None:  # on reste sur l'éditeur, le refus en haut (T3-D9)
        return _afficher(
            request, base, active.fichier.stem, edition(active), 422,
            # Chaque erreur commence déjà par le nom du fichier : ne pas le répéter (T4-D14).
            erreur=f"« {fichier.filename} » n'a pas été importé : "
            + " ; ".join(e.removeprefix(f"{fichier.filename} : ") for e in erreurs),
        )
    return page(request, "configuration.html", 422, erreurs=erreurs, importe=fichier.filename)


# --- une maison ---------------------------------------------------------------------------------


@routeur.get("/app/configuration/{nom}")
def ouvrir(request: Request, nom: str, base: SessionBase, enregistree: Annotated[int | None, Query()] = None,
           creee: Annotated[int | None, Query()] = None):
    vue = edition(config_du_fichier(request.app.state.configs, nom))
    fait = None
    if creee:
        fait = (
            "Configuration créée avec les colonnes de base. Ajoutez vos colonnes (« Ajouter une colonne », en bas), "
            "donnez-leur un nom, une description et, pour une liste, ses valeurs ; puis « Enregistrer »."
        )
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
        return _afficher(request, base, nom, vue, statut, fait=fait,
                         confirmer_consignes=champs.get("confirmer_consignes") == "1")

    # Garde-fou des consignes générales (decisions.md 0173) : les modifier
    # demande une confirmation explicite, vérifiée ici, côté serveur.
    if consignes_modifiees(active, brut) and champs.get("confirmer_consignes") != "1":
        return _afficher(
            request, base, nom, edition(active, brut), 422,
            erreur_consignes="Rien n'a été enregistré : cochez « Je confirme modifier les consignes » pour "
                             "enregistrer des consignes modifiées.",
        )
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


@routeur.post("/app/configuration/{nom}/revenir/{numero}")
def revenir(request: Request, nom: str, numero: int, base: SessionBase):
    """Une ancienne version redevient la configuration : enregistrée comme une
    NOUVELLE version (l'historique ne se réécrit pas, T4-DS5)."""
    active = config_du_fichier(request.app.state.configs, nom)
    _nom_fichier, texte = exporter_version(base, request.app.state.configs, active.config.maison, numero)
    try:
        enregistree = importer(base, request.app.state.configs, texte, f"version {numero}")
    except ConfigInchangee as refus:
        return _afficher(request, base, nom, edition(active), info=str(refus))
    except ConfigInvalide as refus:
        return _afficher(request, base, nom, edition(active), 422, erreur=" ; ".join(refus.erreurs))
    return RedirectResponse(f"/app/configuration/{enregistree.fichier.stem}?enregistree={enregistree.version}",
                            status_code=303)


@routeur.get("/app/configuration/{nom}/export")
def exporter(request: Request, nom: str, base: SessionBase, numero: Annotated[int | None, Query()] = None):
    active = config_du_fichier(request.app.state.configs, nom)
    nom_fichier, texte = exporter_version(base, request.app.state.configs, active.config.maison, numero)
    return Response(
        texte.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{nom_fichier}"'},
    )
