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


def nouvelle_colonne(champs: dict[str, str]) -> int:
    """L'index de la colonne qui vient d'être ajoutée (sans nom) : elle arrive avant
    les colonnes calculées de fin, pas forcément en dernier (T4-B22)."""
    return next(k for k in range(int(champs["nb_colonnes"])) if not champs.get(f"c{k}_nom"))


def ouvrir(client) -> str:
    reponse = client.get(f"/app/configuration/{NOM}")
    assert reponse.status_code == 200, reponse.text
    return reponse.text


def agir(client, champs: dict[str, str], action: str, hx: bool = True):
    return client.post(
        f"/app/configuration/{NOM}", data={**champs, "action": action}, headers=HX if hx else {}, follow_redirects=False
    )


def test_la_configuration_est_celle_de_l_application_sans_nom_de_maison(client):
    """Une instance = une maison (decisions.md 0171) : « Configuration » ouvre
    directement LA configuration, et aucune page ne dit « maison »."""
    redirection = client.get("/app/configuration", follow_redirects=False)
    assert redirection.status_code == 303 and redirection.headers["location"] == f"/app/configuration/{NOM}"
    page = client.get(redirection.headers["location"]).text
    assert 'action="/app/configuration/importer"' in page
    visible = re.sub(r'<input type="hidden"[^>]*>', "", page)  # les données du formulaire ne s'affichent pas
    for mention in ("Maison Test", "de la maison", "des maisons", "chaque maison", "pour toutes les maisons"):
        assert mention not in visible, mention
    assert 'href="/app/configuration"' in client.get("/app").text  # accessible depuis l'accueil


def test_la_page_montre_les_colonnes_et_ce_que_recoit_le_modele(client):
    page = ouvrir(client)
    config = charger_config(CONFIG_TEST)
    for colonne in config.colonnes:
        assert f'value="{colonne.cle}"' in page
    assert page.count('<pre class="code">{') == len(config.colonnes_modele)  # aperçu des colonnes lues
    assert "Jamais envoyée au modèle" in page  # estimation, caisse, lot
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
    i = nouvelle_colonne(champs)
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
    assert "Version 3 enregistrée" in page and "déjà créés gardent la leur" in page


def test_une_config_invalide_n_est_jamais_ecrite(client, configs):
    avant = (configs / CONFIG_TEST.name).read_text(encoding="utf-8")
    champs = formulaire(ouvrir(client))
    champs["c2_nom"] = champs["c3_nom"]  # deux colonnes au même en-tête
    champs["photos_max_par_bouteille"] = "douze"
    refus = agir(client, champs, "enregistrer")
    assert refus.status_code == 422
    assert "Rien n'a été enregistré" in refus.text and "2 point(s) à corriger" in refus.text
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
    brut["colonnes"][1]["description"] = "Description venue du fichier importé."
    reponse = client.post(
        "/app/configuration/importer",
        files={"fichier": ("dupont.json", json.dumps(brut, ensure_ascii=False).encode("utf-8"), "application/json")},
        follow_redirects=False,
    )
    # Le fichier importé devient la nouvelle version de LA configuration, quel
    # que soit le nom de maison qu'il porte (0171).
    assert reponse.status_code == 303 and reponse.headers["location"].startswith(f"/app/configuration/{NOM}?")
    assert not (configs / "cave_dupont.json").exists()
    assert charger_config(configs / CONFIG_TEST.name).maison == "Maison Test"

    brut["colonnes"][0]["type"] = "date"
    refus = client.post(
        "/app/configuration/importer",
        files={"fichier": ("abime.json", json.dumps(brut).encode("utf-8"), "application/json")},
    )
    assert refus.status_code == 422 and "abime.json" in refus.text and "pas été importé" in refus.text
    assert "type &#39;date&#39; inconnu" in refus.text


def test_reimporter_la_version_active_n_est_pas_une_erreur(client):
    """Rapport du testeur, T1-B2 : le fichier qu'on vient d'exporter, réimporté tel quel."""
    active = client.get(f"/app/configuration/{NOM}/export")
    reponse = client.post(
        "/app/configuration/importer", files={"fichier": ("maison.json", active.content, "application/json")}
    )
    assert reponse.status_code == 200 and "ne change rien à la version active" in reponse.text


def test_un_refus_designe_la_colonne_par_son_nom_et_l_encadre(client):
    """Rapport du testeur, T1-M3 / T1-M4 : une colonne sans nom n'a qu'un message,
    en clair ; la colonne fautive est encadrée."""
    champs = formulaire(ouvrir(client))
    page = agir(client, champs, "ajouter_colonne").text
    champs = formulaire(page)
    reponse = agir(client, champs, "enregistrer")
    assert reponse.status_code == 422
    assert "n&#39;a pas de nom : donnez-lui un nom" in reponse.text
    assert "« cle »" not in reponse.text and "doit être un identifiant" not in reponse.text
    assert "colonne-config nouvelle en-erreur" in reponse.text


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


def test_creer_la_configuration_a_la_main_sans_json(tmp_path):
    """decisions.md 0172 : sans aucun fichier, « Créer la configuration » part
    des colonnes de base ; on ajoute ensuite une colonne à la main et on enregistre."""
    vide = tmp_path / "configs_vides"
    vide.mkdir()
    with TestClient(creer_app(tmp_path / "base.db", stockage=tmp_path / "stockage", configs=vide)) as client:
        page = client.get("/app/configuration").text
        assert "Créer la configuration" in page and "Aucune configuration" in page
        nouveau = client.get("/app/nouveau").text
        assert 'href="/app/configuration">Créer la configuration' in nouveau  # T3-D10 : on la crée, depuis là
        assert 'form="formulaire-nouveau" disabled' in nouveau

        creee = client.post("/app/configuration/creer", follow_redirects=False)
        assert creee.status_code == 303 and "creee=1" in creee.headers["location"]
        nom = creee.headers["location"].split("/app/configuration/")[1].split("?")[0]
        editeur = client.get(creee.headers["location"]).text
        assert "Configuration créée" in editeur
        config = charger_config(vide / f"{nom}.json")
        assert [c.cle for c in config.colonnes][:3] == ["id", "quantite", "domaine"]

        # Une colonne ajoutée à la main : nom, type liste, valeurs.
        champs = formulaire(editeur)
        champs = formulaire(client.post(f"/app/configuration/{nom}", data=dict(champs, action="ajouter_colonne"),
                                        headers=HX).text)
        i = nouvelle_colonne(champs)
        champs.update({f"c{i}_nom": "Caisse", f"c{i}_type": "liste", f"c{i}_source": "expert"})
        champs = formulaire(client.post(f"/app/configuration/{nom}", data=dict(champs, action="afficher"), headers=HX).text)
        champs = formulaire(client.post(f"/app/configuration/{nom}", data=dict(champs, action=f"ajouter_valeur-{i}"),
                                        headers=HX).text)
        champs.update({f"c{i}_v0_libelle": "Caisse bois d'origine", f"c{i}_v0_description": "CBO"})
        enregistree = client.post(f"/app/configuration/{nom}", data=dict(champs, action="enregistrer"), headers=HX)
        assert enregistree.status_code == 204, enregistree.text
        caisse = charger_config(vide / f"{nom}.json").colonne("caisse")
        assert caisse is not None and caisse.source == "expert" and "Caisse bois d'origine" in [v.libelle for v in caisse.valeurs]

        assert client.post("/app/configuration/creer").status_code == 409  # une seule configuration
        assert client.post("/app/nouveau", data={"nom": "Vente"}, follow_redirects=False).status_code == 303


def test_les_consignes_generales_se_modifient_avec_confirmation(client, configs):
    """decisions.md 0173 : modifiables depuis la page, mais seulement avec la case
    « Je confirme » (vérifiée par le serveur) ; elles partent alors au modèle et
    changent la version du prompt."""
    from src.extract.consignes import (
        CONSIGNES_MODIFIABLES,
        REGLES_FIXES_DEBUT,
        REGLES_FIXES_FIN,
        consignes_systeme,
        version_prompt,
    )
    from src.extract.schema import schema_extraction

    page = ouvrir(client)
    assert 'name="consignes"' in page and "Modifier les consignes" in page
    champs = formulaire(page)
    nouvelles = CONSIGNES_MODIFIABLES + "\nPrécise toujours le climat s'il est écrit."
    refus = agir(client, dict(champs, consignes=nouvelles), "enregistrer")
    assert refus.status_code == 422 and "Je confirme modifier les consignes" in refus.text
    assert charger_config(configs / CONFIG_TEST.name).consignes is None  # rien d'écrit

    accepte = agir(client, dict(champs, consignes=nouvelles, confirmer_consignes="1"), "enregistrer")
    assert accepte.status_code == 204
    config = charger_config(configs / CONFIG_TEST.name)
    assert config.consignes == nouvelles.strip()
    envoye = consignes_systeme(config)
    # Les contraintes dures restent envoyées, quoi que la maison écrive.
    assert envoye.startswith(REGLES_FIXES_DEBUT) and envoye.endswith(REGLES_FIXES_FIN)
    assert "tu ne devines jamais" in envoye.casefold() and "aucun prix" in envoye and nouvelles.strip() in envoye
    schema = schema_extraction(config)
    assert version_prompt(schema, consignes_systeme(config)) != version_prompt(schema)

    # Revenir au texte d'origine retire la clé : la config redevient « d'origine ».
    champs = formulaire(ouvrir(client))
    agir(client, dict(champs, consignes=CONSIGNES_MODIFIABLES, confirmer_consignes="1"), "enregistrer")
    assert charger_config(configs / CONFIG_TEST.name).consignes is None


def test_une_erreur_d_import_reste_sur_l_editeur(client):
    """T3-D9 : un fichier refusé laisse sur la configuration, le refus en haut."""
    refus = client.post("/app/configuration/importer",
                        files={"fichier": ("abime.json", b'{"maison": ', "application/json")})
    assert refus.status_code == 422 and "abime.json" in refus.text and "n&#39;a pas été importé" in refus.text
    assert 'id="editeur"' in refus.text  # l'éditeur, pas la page « Aucune configuration »


def test_le_refus_des_consignes_s_affiche_a_cote_de_la_case(client):
    """T3-D7 : sans la case cochée, le refus est près de la case, la case encadrée."""
    from src.extract.consignes import CONSIGNES_MODIFIABLES

    champs = formulaire(ouvrir(client))
    refus = agir(client, dict(champs, consignes=CONSIGNES_MODIFIABLES + "\nAjout."), "enregistrer")
    assert refus.status_code == 422 and 'id="refus-consignes"' in refus.text and "a-cocher" in refus.text


def test_ajouter_une_colonne_la_place_avant_a_verifier_et_l_identifiant_suit_le_libelle(client):
    """T4-B22 : une colonne ajoutée arrive avant « À vérifier » ; T4-B10 : l'identifiant
    tiré du libellé n'est pas figé ; T4-B12 : « Vérifier » garde la case cochée."""
    champs = formulaire(ouvrir(client))
    n = int(champs["nb_colonnes"])
    page = agir(client, champs, "ajouter_colonne").text
    champs = formulaire(page)
    assert champs[f"c{n}_cle"] == "a_verifier"  # « À vérifier » reste la dernière
    i = nouvelle_colonne(champs)
    assert i == n - 1
    champs.update({f"c{i}_nom": "Provenance", f"c{i}_type": "liste"})
    champs = formulaire(agir(client, champs, "afficher").text)
    champs = formulaire(agir(client, champs, f"ajouter_valeur-{i}").text)
    champs[f"c{i}_v0_libelle"] = "Cave Dupont"
    champs = formulaire(agir(client, champs, "verifier").text)
    assert champs.get(f"c{i}_v0_code", "") == ""  # tiré du libellé : non figé
    champs[f"c{i}_v0_libelle"] = "Cave Martin"
    verifiee = agir(client, dict(champs, confirmer_consignes="1"), "verifier")
    assert 'name="confirmer_consignes" value="1" checked' in verifiee.text


def test_revenir_a_une_ancienne_version(client, configs):
    """T4-DS5 : une ancienne version redevient la configuration, comme une NOUVELLE version."""
    champs = formulaire(ouvrir(client))
    agir(client, dict(champs, c1_nom="Nombre"), "enregistrer")  # version 3
    champs = formulaire(ouvrir(client))
    agir(client, dict(champs, c1_nom="Nb"), "enregistrer")  # version 4 : la 3 n'est plus active
    page = ouvrir(client)
    assert "revenir à cette version" in page and "active" in page
    numero = page.split(f"/app/configuration/{NOM}/revenir/")[1].split('"')[0]
    retour = client.post(f"/app/configuration/{NOM}/revenir/{numero}", follow_redirects=False)
    assert retour.status_code == 303 and "enregistree=5" in retour.headers["location"]
    assert charger_config(configs / CONFIG_TEST.name).colonne("quantite").nom == "Nombre"  # la version 3 revenue
