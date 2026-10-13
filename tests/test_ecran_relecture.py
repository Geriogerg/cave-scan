"""L'écran de relecture, côté serveur (guide de session 5).

Le navigateur est simulé par le client de test : chaque sortie de champ est un
POST HTMX (`HX-Request`), la validation envoie tout le formulaire, comme le
fait la page. Les mêmes garde-fous qu'en service : ici, on vérifie que l'écran
les applique et les dit en français.
"""

from __future__ import annotations

import html
import re

import pytest
from sqlalchemy.orm import Session

from src.config.maison import charger_config
from src.donnees.base import creer_moteur, url_de_base
from src.donnees.modeles import FicheBouteille
from src.extract.fixture_extract import FixtureExtractor
from src.services.extraction import traiter_reservee
from src.services.file_attente import reserver_bouteille
from src.services.relecture import corriger, valeurs_courantes, valeurs_modele
from tests.conftest import CONFIG_TEST
from tests.test_api import api, charges, envoyer, extraire_en_arriere_plan  # noqa: F401 — fixture partagée
from tests.test_extraction import ExtracteurScenario

HX = {"HX-Request": "true"}


@pytest.fixture
def inventaire(api, dossier_photos):
    """6 bouteilles extraites (fixtures habituelles), créées et lancées par l'API."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    return inventaire_id


@pytest.fixture
def base(api):
    """Une autre connexion à la base de l'application : « un autre onglet », le worker."""
    moteur = creer_moteur(url_de_base(api.base_db))
    with Session(moteur, expire_on_commit=False) as session:
        yield session
    moteur.dispose()


def ids(base, inventaire_id):
    return [b.id for b in base.query(FicheBouteille).filter_by(inventaire_id=inventaire_id).order_by(FicheBouteille.position)]


def ouvrir(api, inventaire_id, bouteille_id, **params):
    page = api.get(f"/app/inventaires/{inventaire_id}/relecture/{bouteille_id}", params=params)
    assert page.status_code == 200, page.text
    return page.text


def version(texte):
    return re.search(r'id="version" name="_version" value="([^"]*)"', texte).group(1)


def formulaire(texte):
    """Ce que le formulaire de la page envoie tel qu'affiché (champs + contrôles)."""
    form = texte[texte.index('<form id="fiche"'):texte.index("</form>", texte.index('<form id="fiche"'))]
    valeurs = {nom: html.unescape(valeur) for nom, valeur in re.findall(r'<input type="(?:text|number|hidden)" [^>]*?name="([^"]+)"[^>]*? value="([^"]*)"', form)}
    valeurs.update(re.findall(r'id="[^"]*" name="([^"]+)" value="([^"]*)"', form))
    for nom, options in re.findall(r'<select id="saisie-[^"]+" name="([^"]+)"[^>]*>(.*?)</select>', form, re.S):
        choisie = re.search(r'<option value="([^"]*)" selected>', options)
        valeurs[nom] = choisie.group(1) if choisie else ""
    return valeurs


def enregistrer(api, inventaire_id, bouteille_id, cle, valeur, texte, **extra):
    donnees = formulaire(texte) | {cle: valeur} | extra
    return api.post(f"/app/inventaires/{inventaire_id}/relecture/{bouteille_id}/champ/{cle}", data=donnees, headers=HX)


# --- entrer, afficher -----------------------------------------------------------------------


def test_le_suivi_mene_a_la_relecture_qui_ouvre_la_premiere_bouteille_non_validee(api, inventaire, base):
    suivi = api.get(f"/app/inventaires/{inventaire}/progression").text
    assert "Relire les bouteilles" in suivi and f"/app/inventaires/{inventaire}/relecture" in suivi
    premiere, seconde = ids(base, inventaire)[:2]
    entree = api.get(f"/app/inventaires/{inventaire}/relecture", follow_redirects=False)
    assert entree.status_code == 303 and entree.headers["location"].endswith(f"/relecture/{premiere}")
    corriger(base, premiere, "cuvee", "X", "autre")
    api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/valider", data=formulaire(ouvrir(api, inventaire, premiere)))
    entree = api.get(f"/app/inventaires/{inventaire}/relecture", follow_redirects=False)
    assert entree.headers["location"].endswith(f"/relecture/{seconde}")


def test_la_page_d_une_bouteille(api, inventaire, base):
    premiere, seconde = ids(base, inventaire)[:2]
    texte = ouvrir(api, inventaire, premiere)
    assert "1</strong> / 6" in texte  # position
    assert "0</strong> validée(s) sur 6" in texte
    for attendu in ("Domaine / Château", "Millésime", "Estimation (€)", "Qté", "Valider et passer à la suivante",
                    "Ctrl+Entrée", "Raccourcis clavier", "/static/relecture.js", ">Original</a>"):
        assert attendu in texte, attendu
    assert 'value="Domaine Rossignol-Trapet"' in texte
    # Photos : par la route qui vérifie l'inventaire, jamais un dossier statique.
    photos = re.findall(r'(?:src|href)="(/[^"]*photos/[^"]*)"', texte)
    assert photos and all(p.startswith(f"/inventaires/{inventaire}/photos/") for p in photos)
    # La bouteille suivante est préchargée.
    suivante = base.get(FicheBouteille, seconde)
    for photo in suivante.photos:  # toutes ses photos (decisions.md 0166)
        assert f'rel="prefetch" href="/inventaires/{inventaire}/photos/{photo.id}?taille=reduite"' in texte
    assert f'data-suivante="/app/inventaires/{inventaire}/relecture/{seconde}"' in texte
    assert "Ctrl+Entrée" in texte and "Échap" in texte


def test_une_abstention_s_affiche_a_remplir_jamais_comme_une_valeur(api, inventaire, base):
    margaux = ids(base, inventaire)[1]  # millésime et cuvée non lisibles, couleur déduite
    texte = ouvrir(api, inventaire, margaux)
    assert "non_lisible" not in texte and "non_determinable" not in texte.replace('value="non_determinable"', "")
    assert re.search(r'name="millesime" class="saisie" value=""', texte)
    assert 'placeholder="à remplir"' in texte and "— à remplir —" in texte
    assert "déduite par le modèle" in texte and "proposée, à vérifier" in texte and "doute du modèle" in texte


# --- enregistrement immédiat ----------------------------------------------------------------


def test_chaque_sortie_de_champ_est_enregistree_sans_bouton(api, inventaire, base):
    premiere = ids(base, inventaire)[0]
    texte = ouvrir(api, inventaire, premiere)
    reponse = enregistrer(api, inventaire, premiere, "millesime", "2001", texte)
    assert reponse.status_code == 200
    assert "Enregistré" in reponse.text and 'data-etat="enregistre"' in reponse.text
    assert 'hx-swap-oob="true"' in reponse.text and version(reponse.text) != version(texte)  # nouvelle version
    assert "Millésime : 2018 → 2001" in reponse.text  # historique à jour
    assert 'id="saisie-millesime"' not in reponse.text  # la saisie elle-même n'est jamais remplacée
    base.expire_all()
    assert valeurs_courantes(base, premiere).millesime == "2001"
    assert valeurs_modele(base, premiere).millesime == "2018"
    assert "Enregistrer</button>" not in texte  # pas de bouton « Enregistrer »


def test_une_saisie_refusee_est_dite_a_cote_du_champ(api, inventaire, base):
    premiere = ids(base, inventaire)[0]
    texte = ouvrir(api, inventaire, premiere)
    couleur = enregistrer(api, inventaire, premiere, "couleur", "bleu", texte)
    assert couleur.status_code == 422 and "Refusé : « bleu » n&#39;est pas une valeur de la liste" in couleur.text
    quantite = enregistrer(api, inventaire, premiere, "quantite", "0", texte)
    assert quantite.status_code == 422 and "Quantité invalide" in quantite.text
    base.expire_all()
    assert valeurs_courantes(base, premiere).quantite == 1


def test_modifier_une_bouteille_validee_le_signale(api, inventaire, base):
    premiere = ids(base, inventaire)[0]
    api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/valider", data=formulaire(ouvrir(api, inventaire, premiere)))
    texte = ouvrir(api, inventaire, premiere)
    assert "Bouteille validée." in texte
    reponse = enregistrer(api, inventaire, premiere, "cuvee", "Autre", texte)
    assert "Cette bouteille était validée : cette modification la remet à relire." in reponse.text
    assert base.get(FicheBouteille, premiere).statut == "extraite"


def test_deux_onglets_l_avertissement_se_declenche(api, inventaire, base):
    premiere = ids(base, inventaire)[0]
    onglet_a, onglet_b = ouvrir(api, inventaire, premiere), ouvrir(api, inventaire, premiere)
    assert enregistrer(api, inventaire, premiere, "millesime", "2001", onglet_b).status_code == 200
    conflit = enregistrer(api, inventaire, premiere, "millesime", "1990", onglet_a)
    assert conflit.status_code == 409
    assert "modifiée ailleurs depuis l'ouverture de la page" in conflit.text and "2001" in conflit.text
    assert "Enregistrer quand même" in conflit.text
    base.expire_all()
    assert valeurs_courantes(base, premiere).millesime == "2001"
    force = enregistrer(api, inventaire, premiere, "millesime", "1990", onglet_a, _forcer="1")
    assert force.status_code == 200
    base.expire_all()
    assert valeurs_courantes(base, premiere).millesime == "1990"
    historique = [c.nouvelle_valeur for c in base.get(FicheBouteille, premiere).corrections]
    assert historique == ["2001", "1990"]  # l'historique garde les deux


def test_revenir_a_la_valeur_du_modele_depuis_l_ecran(api, inventaire, base):
    premiere = ids(base, inventaire)[0]
    texte = ouvrir(api, inventaire, premiere)
    reponse = enregistrer(api, inventaire, premiere, "millesime", "2001", texte)
    assert "Revenir à la valeur du modèle" in reponse.text and "Lu par le modèle : 2018" in reponse.text
    retour = api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/champ/millesime/revenir",
                      data={"_version": version(reponse.text)}, headers=HX)
    assert retour.status_code == 200 and 'name="millesime" class="saisie" value="2018"' in retour.text
    assert len(base.get(FicheBouteille, premiere).corrections) == 2


# --- valider ---------------------------------------------------------------------------------


def test_valider_passe_a_la_suivante_et_enregistre_le_temps(api, inventaire, base):
    premiere, seconde = ids(base, inventaire)[:2]
    donnees = formulaire(ouvrir(api, inventaire, premiere)) | {"_temps_ms": "5300", "millesime": "2015"}
    reponse = api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/valider", data=donnees, headers=HX)
    assert reponse.status_code == 204
    assert reponse.headers["HX-Redirect"] == f"/app/inventaires/{inventaire}/relecture/{seconde}"
    base.expire_all()
    bouteille = base.get(FicheBouteille, premiere)
    assert (bouteille.statut, bouteille.temps_relecture_ms) == ("validee", 5300)
    assert valeurs_courantes(base, premiere).millesime == "2015"  # saisie pas encore enregistrée : gardée


def test_sans_javascript_valider_reste_un_simple_formulaire(api, inventaire, base):
    premiere, seconde = ids(base, inventaire)[:2]
    reponse = api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/valider",
                       data=formulaire(ouvrir(api, inventaire, premiere)), follow_redirects=False)
    assert reponse.status_code == 303 and reponse.headers["location"].endswith(f"/relecture/{seconde}")


def test_une_saisie_invalide_bloque_la_validation(api, inventaire, base):
    premiere = ids(base, inventaire)[0]
    donnees = formulaire(ouvrir(api, inventaire, premiere)) | {"quantite": "0", "couleur": "bleu"}
    reponse = api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/valider", data=donnees, headers=HX)
    assert reponse.status_code == 422
    assert "Bouteille non validée : 2 saisies sont refusées" in reponse.text
    assert reponse.text.count('data-etat="refuse"') == 2 and "Quantité invalide" in reponse.text
    assert base.get(FicheBouteille, premiere).statut == "extraite"


def test_la_derniere_bouteille_validee_mene_au_recapitulatif(api, inventaire, base):
    for bouteille_id in ids(base, inventaire):
        reponse = api.post(f"/app/inventaires/{inventaire}/relecture/{bouteille_id}/valider",
                           data=formulaire(ouvrir(api, inventaire, bouteille_id)), headers=HX)
        assert reponse.status_code == 204, reponse.text
    assert reponse.headers["HX-Redirect"] == f"/app/inventaires/{inventaire}/recapitulatif"
    recap = api.get(f"/app/inventaires/{inventaire}/recapitulatif").text
    assert "Toutes les bouteilles sont validées : l'inventaire est validé." in recap
    assert f"/inventaires/{inventaire}/export" in recap
    assert api.get(f"/inventaires/{inventaire}").json()["statut"] == "valide"


# --- cas particuliers ------------------------------------------------------------------------


def test_bouteille_en_erreur_la_raison_en_clair_et_reanalyser(api, dossier_photos, base):
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, ExtracteurScenario({2: "passagere"}))
    en_erreur = ids(base, inventaire_id)[1]
    texte = ouvrir(api, inventaire_id, en_erreur)
    assert "Analyse en échec." in texte and "panne passagère" in texte
    assert "RateLimitError" not in texte and "quota dépassé" not in texte  # jamais le message brut
    refus = api.post(f"/app/inventaires/{inventaire_id}/relecture/{en_erreur}/valider", data=formulaire(texte), headers=HX)
    assert refus.status_code == 409 and "en erreur" in refus.text

    reanalyse = api.post(f"/app/inventaires/{inventaire_id}/relecture/{en_erreur}/reanalyser", follow_redirects=False)
    assert reanalyse.status_code == 303 and reanalyse.headers["location"].endswith("?fait=reanalyse")
    attente = ouvrir(api, inventaire_id, en_erreur)
    assert "Réanalyse en attente du modèle" in attente and 'hx-trigger="every 2s"' in attente
    assert api.get(f"/app/inventaires/{inventaire_id}/relecture/{en_erreur}/attente").headers.get("HX-Refresh") is None
    base.expire_all()
    traiter_reservee(base, reserver_bouteille(base, "w", inventaire_id), ExtracteurScenario(), api.stockage, "w")
    assert api.get(f"/app/inventaires/{inventaire_id}/relecture/{en_erreur}/attente").headers["HX-Refresh"] == "true"


def test_la_page_montre_toutes_les_photos_numerotees_sans_inversion(api, inventaire, base):
    """Une bouteille = ses photos, numérotées, sans rôle : « Inverser les photos »
    a disparu avec les rôles (decisions.md 0166)."""
    premiere = ids(base, inventaire)[0]
    texte = ouvrir(api, inventaire, premiere)
    for numero, photo in enumerate(base.get(FicheBouteille, premiere).photos, start=1):
        assert f'data-photo="{numero}"' in texte and f"/photos/{photo.id}?taille=miniature" in texte
    assert "Photo 2 sur 2 de la bouteille" in texte and "Inverser" not in texte
    assert api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/inverser").status_code in (404, 405)


def test_signaler_une_paire_empeche_la_validation(api, inventaire, base):
    premiere = ids(base, inventaire)[0]
    api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/signaler", data={"motif": "décalage"})
    texte = ouvrir(api, inventaire, premiere)
    assert "Problème de photos signalé : cette bouteille ne peut pas être validée." in texte
    refus = api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/valider", data=formulaire(texte), headers=HX)
    assert refus.status_code == 409 and "problème de photos" in refus.text
    assert "problème de photos signalé : décalage" in texte  # historique
    api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/lever-signalement")
    ok = api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/valider",
                  data=formulaire(ouvrir(api, inventaire, premiere)), headers=HX)
    assert ok.status_code == 204


def test_separer_depuis_l_ecran_ouvre_la_nouvelle_bouteille(api, inventaire, base):
    premiere = ids(base, inventaire)[0]
    texte = ouvrir(api, inventaire, premiere)
    enregistrer(api, inventaire, premiere, "quantite", "6", texte)
    reponse = api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/separer", data={"quantite": "1"}, follow_redirects=False)
    assert reponse.status_code == 303 and "fait=separee" in reponse.headers["location"]
    nouvelle = ids(base, inventaire)[1]
    assert reponse.headers["location"].startswith(f"/app/inventaires/{inventaire}/relecture/{nouvelle}")
    page = api.get(reponse.headers["location"]).text
    assert "Bouteille séparée. Ajustez l&#39;état et la description de cet exemplaire." in page
    assert "Née de la séparation de la bouteille n°1" in page
    assert "7</strong> / 7" not in page and "2</strong> / 7" in page
    trop = api.post(f"/app/inventaires/{inventaire}/relecture/{premiere}/separer", data={"quantite": "5"})
    assert trop.status_code == 409 and "on peut en séparer 4 au plus" in trop.text


def test_le_filtre_ne_montre_que_les_bouteilles_a_verifier(api, dossier_photos, base):
    from tests.test_relecture_ecran import PROPRE

    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    propres = [dict(PROPRE, domaine=f"Domaine {rang}") for rang in range(1, 7)]
    propres[3]["millesime"] = "non_lisible"  # seule la n°4 a un doute
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(propres, charger_config(CONFIG_TEST)))
    quatrieme = ids(base, inventaire_id)[3]
    entree = api.get(f"/app/inventaires/{inventaire_id}/relecture", params={"filtre": "a_verifier"}, follow_redirects=False)
    assert entree.headers["location"] == f"/app/inventaires/{inventaire_id}/relecture/{quatrieme}?filtre=a_verifier"
    texte = ouvrir(api, inventaire_id, quatrieme, filtre="a_verifier")
    assert 'data-precedente=""' in texte and 'data-suivante=""' in texte  # aucune autre à vérifier
    assert 'aria-checked="true"' in texte and "dont 1 avec un doute" in texte


def test_la_relecture_d_un_brouillon_renvoie_au_depot(api):
    reponse = api.post("/app/nouveau", data={"nom": "Brouillon", "maison": "Maison Test"}, follow_redirects=False)
    inventaire_id = int(re.search(r"/inventaires/(\d+)/", reponse.headers["location"]).group(1))
    assert api.get(f"/app/inventaires/{inventaire_id}/relecture", follow_redirects=False).headers["location"].endswith("/depot")


def test_une_bouteille_d_un_autre_inventaire_est_introuvable(api, inventaire, dossier_photos, base):
    autre = envoyer(api, dossier_photos, nom="Autre").json()["id"]
    etrangere = ids(base, autre)[0]
    reponse = api.get(f"/app/inventaires/{inventaire}/relecture/{etrangere}")
    assert reponse.status_code == 404 and "Impossible d'afficher cette page" in reponse.text
