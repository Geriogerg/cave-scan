"""La page « Configuration » (decisions.md 0161, 0163) : chaque action renvoie
toute la config, rien n'est écrit avant « Enregistrer », rien d'invalide n'est
jamais écrit, et l'aperçu montre ce que reçoit le modèle.

L'application travaille sur une COPIE du dossier des configs : la vraie config
de test n'est jamais réécrite."""

from __future__ import annotations

import json
import re
import shutil

import pytest
from fastapi.testclient import TestClient

from src.api.app import creer_app
from src.config.maison import charger_config
from tests.conftest import CONFIG_TEST

HX = {"HX-Request": "true"}
NOM = CONFIG_TEST.stem


@pytest.fixture
def configs(tmp_path):
    dossier = tmp_path / "configs"
    dossier.mkdir()
    shutil.copy(CONFIG_TEST, dossier / CONFIG_TEST.name)
    return dossier


@pytest.fixture
def client(tmp_path, configs):
    with TestClient(creer_app(tmp_path / "base.db", stockage=tmp_path / "stockage", configs=configs)) as c:
        yield c


def formulaire(page: str) -> dict[str, str]:
    """Les champs du formulaire tels que le navigateur les enverrait : valeurs des
    champs texte et cachés, options choisies, cases cochées, zones de texte."""
    champs: dict[str, str] = {}
    for balise in re.findall(r"<input[^>]*>", page):
        nom = re.search(r'name="([^"]+)"', balise)
        if not nom:
            continue
        type_ = re.search(r'type="([^"]+)"', balise)
        if type_ and type_.group(1) == "checkbox" and "checked" not in balise:
            continue
        if type_ and type_.group(1) == "file":
            continue
        valeur = re.search(r'value="([^"]*)"', balise)
        champs[nom.group(1)] = _texte(valeur.group(1) if valeur else "")
    for nom, options in re.findall(r'<select name="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        choisie = re.search(r'<option value="([^"]*)" selected', options)
        champs[nom] = choisie.group(1) if choisie else ""
    for nom, contenu in re.findall(r'<textarea name="([^"]+)"[^>]*>(.*?)</textarea>', page, re.S):
        champs[nom] = _texte(contenu)
    return champs


def _texte(html: str) -> str:
    return (
        html.replace("&#34;", '"').replace("&quot;", '"').replace("&#39;", "'")
        .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    )


def ouvrir(client) -> str:
    reponse = client.get(f"/app/configuration/{NOM}")
    assert reponse.status_code == 200, reponse.text
    return reponse.text


def agir(client, champs: dict[str, str], action: str, hx: bool = True):
    return client.post(
        f"/app/configuration/{NOM}", data={**champs, "action": action}, headers=HX if hx else {}, follow_redirects=False
    )


def test_la_liste_montre_chaque_maison_et_l_import(client):
    page = client.get("/app/configuration").text
    assert "Maison Test" in page and f'href="/app/configuration/{NOM}"' in page
    assert 'action="/app/configuration/importer"' in page
    assert 'href="/app/configuration"' in client.get("/app").text  # accessible depuis l'accueil


def test_la_page_montre_les_colonnes_et_ce_que_recoit_le_modele(client):
    page = ouvrir(client)
    config = charger_config(CONFIG_TEST)
    for colonne in config.colonnes:
        assert f'value="{colonne.cle}"' in page
    assert page.count('<pre class="code">{') == len(config.colonnes_modele)  # aperçu des colonnes lues
    assert "Jamais envoyée au modèle : saisie par l&#39;expert" in page  # estimation, caisse, lot
    assert "Ne jamais deviner" in page  # la consigne ajoutée par l'outil, visible
    assert "RÈGLE ABSOLUE" in page  # les consignes générales aussi
    assert "Enregistrer la version 3" in page


def test_les_actions_ne_changent_que_l_affichage(client, configs):
    avant = (configs / CONFIG_TEST.name).read_text(encoding="utf-8")
    champs = formulaire(ouvrir(client))
    nb = int(champs["nb_colonnes"])

    ajout = agir(client, champs, "ajouter_colonne")
    assert ajout.status_code == 200 and 'id="editeur"' in ajout.text and "<html" not in ajout.text
    assert f'name="nb_colonnes" value="{nb + 1}"' in ajout.text and "Nouvelle colonne" in ajout.text

    retrait = agir(client, champs, "supprimer-1")  # la quantité
    assert f'name="nb_colonnes" value="{nb - 1}"' in retrait.text and 'value="quantite"' not in retrait.text

    monte = agir(client, champs, "monter-2")
    assert monte.text.index('value="domaine"') < monte.text.index('value="quantite"')
    assert (configs / CONFIG_TEST.name).read_text(encoding="utf-8") == avant  # rien d'écrit


def test_ajouter_une_colonne_puis_l_enregistrer_cree_une_version(client, configs):
    champs = formulaire(ouvrir(client))
    champs = formulaire(agir(client, champs, "ajouter_colonne").text)
    i = int(champs["nb_colonnes"]) - 1
    champs.update({f"c{i}_nom": "Bouchon", f"c{i}_type": "liste", f"c{i}_source": "modele_best_effort"})
    champs = formulaire(agir(client, champs, f"ajouter_valeur-{i}").text)
    champs.update({f"c{i}_v0_libelle": "Bouchon sain", f"c{i}_v0_description": "Aucune trace sur le liège."})
    champs[f"c{i}_regle"] = "Seulement si une photo montre le bouchon. Sinon non déterminable."

    verifiee = agir(client, champs, "verifier")
    assert verifiee.status_code == 200 and "Configuration valide" in verifiee.text
    assert '"bouchon_sain"' in verifiee.text  # code créé à partir du libellé, visible dans l'aperçu

    enregistree = agir(client, champs, "enregistrer")
    assert enregistree.status_code == 204
    assert enregistree.headers["HX-Redirect"] == f"/app/configuration/{NOM}?enregistree=3"
    config = charger_config(configs / CONFIG_TEST.name)
    assert config.version == 3
    bouchon = config.colonne("bouchon")
    assert bouchon.source == "modele_best_effort" and bouchon.codes == ("bouchon_sain", "non_determinable")
    page = client.get(enregistree.headers["HX-Redirect"]).text
    assert "Version 3 enregistrée" in page and "Les inventaires déjà créés gardent la leur" in page


def test_une_config_invalide_n_est_jamais_ecrite(client, configs):
    avant = (configs / CONFIG_TEST.name).read_text(encoding="utf-8")
    champs = formulaire(ouvrir(client))
    champs["c2_nom"] = champs["c3_nom"]  # deux colonnes au même en-tête
    champs["photos_max_par_bouteille"] = "douze"
    refus = agir(client, champs, "enregistrer")
    assert refus.status_code == 422
    assert "Rien n'a été enregistré : 2 point(s) à corriger" in refus.text
    assert "photos_max_par_bouteille" in refus.text and "même en-tête" in refus.text
    assert 'value="douze"' in refus.text  # la saisie reste à l'écran pour être corrigée
    assert (configs / CONFIG_TEST.name).read_text(encoding="utf-8") == avant


def test_une_config_modifiee_ailleurs_n_est_pas_ecrasee(client, configs):
    champs = formulaire(ouvrir(client))
    autre = dict(champs, c1_nom="Qté (autre onglet)")
    assert agir(client, autre, "enregistrer").status_code == 204
    mien = dict(champs, c1_nom="Qté (mon onglet)")
    refus = agir(client, mien, "enregistrer")
    assert refus.status_code == 409 and "modifiée ailleurs" in refus.text
    assert charger_config(configs / CONFIG_TEST.name).colonnes[1].nom == "Qté (autre onglet)"


def test_un_code_ou_une_cle_deja_enregistres_ne_sont_pas_modifiables(client):
    page = ouvrir(client)
    # Clés et codes existants : affichés, envoyés en champ caché, jamais en champ de saisie.
    assert re.search(r'<input type="hidden" name="c\d+_cle" value="domaine">', page)
    assert re.search(r'<input type="hidden" name="c\d+_v0_code" value="rouge">', page)
    assert not re.search(r'<input type="text" name="c\d+_cle" value="domaine"', page)


def test_les_commentaires_de_la_config_sont_gardes(client, configs):
    champs = formulaire(ouvrir(client))
    champs["c1_nom"] = "Quantité"
    agir(client, champs, "enregistrer")
    brut = json.loads((configs / CONFIG_TEST.name).read_text(encoding="utf-8"))
    assert brut["_fictif"].startswith("Config de TEST") and "source" in brut["_format"]


def test_sans_javascript_les_actions_affichent_la_page_entiere(client):
    champs = formulaire(ouvrir(client))
    reponse = agir(client, champs, "ajouter_colonne", hx=False)
    assert reponse.status_code == 200 and "<html" in reponse.text and 'id="editeur"' in reponse.text
    enregistree = agir(client, dict(champs, c1_nom="Quantité"), "enregistrer", hx=False)
    assert enregistree.status_code == 303 and enregistree.headers["location"].endswith("?enregistree=3")


def test_importer_un_fichier(client, configs):
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["maison"] = "Cave Dupont"
    reponse = client.post(
        "/app/configuration/importer",
        files={"fichier": ("dupont.json", json.dumps(brut, ensure_ascii=False).encode("utf-8"), "application/json")},
        follow_redirects=False,
    )
    assert reponse.status_code == 303 and reponse.headers["location"].startswith("/app/configuration/cave_dupont?")
    assert charger_config(configs / "cave_dupont.json").maison == "Cave Dupont"

    brut["colonnes"][0]["type"] = "date"
    refus = client.post(
        "/app/configuration/importer",
        files={"fichier": ("abime.json", json.dumps(brut).encode("utf-8"), "application/json")},
    )
    assert refus.status_code == 422 and "« abime.json » n'a pas été importé" in refus.text
    assert "type &#39;date&#39; inconnu" in refus.text


def test_exporter_la_version_active_et_les_anciennes(client):
    active = client.get(f"/app/configuration/{NOM}/export")
    assert active.status_code == 200 and "attachment" in active.headers["content-disposition"]
    assert json.loads(active.content)["maison"] == "Maison Test"
    champs = formulaire(ouvrir(client))
    agir(client, dict(champs, c1_nom="Quantité"), "enregistrer")
    agir(client, formulaire(ouvrir(client)) | {"c1_nom": "Nombre"}, "enregistrer")
    page = ouvrir(client)
    numeros = re.findall(rf"/app/configuration/{NOM}/export\?numero=(\d+)", page)
    assert len(numeros) == 2
    ancienne = client.get(f"/app/configuration/{NOM}/export", params={"numero": min(numeros)})
    assert json.loads(ancienne.content)["colonnes"][1]["nom"] == "Quantité"


def test_une_maison_inconnue_est_une_page_introuvable(client):
    reponse = client.get("/app/configuration/inconnue")
    assert reponse.status_code == 404 and "Aucune configuration" in reponse.text
    assert client.get("/app/configuration/..%2F..%2Fsecret").status_code == 404
