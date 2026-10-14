"""Relecture dans un vrai navigateur, au clavier seulement (guide de session 5, §8).

Chromium, écran d'ordinateur, contre un vrai `dev.py` (application + worker,
extracteur factice). Trois parcours :
- relire 10 bouteilles uniquement au clavier : corriger un champ liste, un
  champ texte, la quantité, valider, naviguer ; vérifier qu'un raccourci tapé
  dans un champ reste du texte, qu'une saisie refusée bloque Ctrl+Entrée ;
  puis vérifier l'export ;
- deux onglets sur la même bouteille : l'avertissement, puis l'historique ;
- 300 bouteilles : le passage à la suivante est immédiat, ses photos ayant
  été préchargées.

Aucune pause fixe : chaque attente porte sur une condition, avec une limite.
"""

from __future__ import annotations

import io
import os
import statistics
import subprocess
import sys
import time

import httpx
import pytest
from openpyxl import load_workbook

from src.config.maison import charger_config
from src.donnees.base import session_de_base
from src.extract.factice import ExtracteurFactice
from src.extract.fixture_extract import generer_photos_fictives
from src.services.extraction import extraire_inventaire
from src.services.inventaires import creer_inventaire
from tests.conftest import CONFIG_TEST, RACINE
from tests.test_lancement import port_libre
from tests.test_worker import attendre

sync_api = pytest.importorskip("playwright.sync_api")

AUTEUR = "Expert clavier"


def demarrer(tmp_path, base):
    port = port_libre()
    environnement = dict(os.environ, CAVE_SCAN_STOCKAGE=str(tmp_path / "stockage"), PYTHONIOENCODING="utf-8",
                         CAVE_SCAN_AUTEUR=AUTEUR)
    for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        environnement.pop(variable, None)
    processus = subprocess.Popen(
        [sys.executable, str(RACINE / "dev.py"), "--port", str(port), "--base", str(base),
         "--backend", "factice", "--latence", "0.01", "--attente", "0.1"],
        cwd=RACINE, env=environnement, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"

    def repond():
        try:
            return httpx.get(f"{url}/app", timeout=1).status_code == 200
        except httpx.HTTPError:
            return False

    attendre(repond, message="dev.py répond")
    return processus, url


@pytest.fixture
def application(tmp_path):
    processus, url = demarrer(tmp_path, tmp_path / "base.db")
    try:
        yield url
    finally:
        processus.kill()
        processus.wait(30)


@pytest.fixture
def ordinateur():
    with sync_api.sync_playwright() as p:
        try:
            navigateur = p.chromium.launch()
        except Exception as erreur:  # pragma: no cover — Chromium non installé
            pytest.skip(f"Chromium indisponible ({erreur}) : python -m playwright install chromium")
        contexte = navigateur.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        yield contexte
        contexte.close()
        navigateur.close()


def inventaire_extrait(url, tmp_path, nombre):
    photos = generer_photos_fictives(tmp_path / "photos", nombre)
    # Une bouteille = ses photos (decisions.md 0166) : chaque sous-dossier en contient deux.
    fichiers = [("photos", (p.name, p.read_bytes(), "image/jpeg")) for d in sorted(photos.iterdir()) for p in sorted(d.iterdir())]
    donnees = {"nom": "Vente clavier", "maison": "Maison Test", "photos_par_bouteille": ",".join(["2"] * nombre)}
    cree = httpx.post(f"{url}/inventaires", data=donnees, files=fichiers, timeout=60)
    assert cree.status_code == 201, cree.text
    inventaire_id = cree.json()["id"]
    httpx.post(f"{url}/inventaires/{inventaire_id}/lancer")
    attendre(lambda: httpx.get(f"{url}/inventaires/{inventaire_id}").json()["progression"]["terminee"],
             message="extraction terminée")
    return inventaire_id


def ids(url, inventaire_id):
    return [b["id"] for b in httpx.get(f"{url}/inventaires/{inventaire_id}/bouteilles", params={"par_page": 200}).json()["bouteilles"]]


def tout_est_enregistre(page):
    page.wait_for_function("document.getElementById('indicateur').textContent === 'Tout est enregistré'", timeout=10_000)


def sur_la_bouteille(page, bouteille_id):
    page.wait_for_url(f"**/relecture/{bouteille_id}*", timeout=10_000)
    page.wait_for_function("document.querySelector('[data-relecture]') !== null")


def test_relire_dix_bouteilles_uniquement_au_clavier(application, ordinateur, tmp_path):
    inventaire_id = inventaire_extrait(application, tmp_path, 10)
    b = ids(application, inventaire_id)
    page = ordinateur.new_page()
    erreurs = []
    page.on("pageerror", lambda erreur: erreurs.append(str(erreur)))
    page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture")
    sur_la_bouteille(page, b[0])
    clavier = page.keyboard

    # Bouteille 1 : quantité, un champ texte, un champ liste — chacun enregistré en le quittant.
    clavier.press("Tab")  # premier champ : la quantité, contenu sélectionné
    clavier.type("3")
    clavier.press("Tab")  # domaine
    clavier.type("Domaine Clavier")
    clavier.press("Tab")  # appellation
    clavier.press("Tab")  # cuvée
    clavier.press("Tab")  # millésime
    clavier.type("2015")
    clavier.press("Tab")  # couleur : liste, recherche au clavier
    clavier.type("b")
    assert page.eval_on_selector("#saisie-couleur", "e => e.value") == "blanc"
    clavier.press("Escape")  # quitte le champ : il est enregistré
    tout_est_enregistre(page)
    assert "Enregistré" in page.inner_text("#pied-couleur")
    clavier.press("Enter")  # hors champ texte : valider et passer à la suivante
    sur_la_bouteille(page, b[1])

    # Naviguer sans valider : K (suivante), puis flèche gauche (précédente).
    clavier.press("k")
    sur_la_bouteille(page, b[2])
    clavier.press("ArrowLeft")
    sur_la_bouteille(page, b[1])
    clavier.press("Enter")
    sur_la_bouteille(page, b[2])  # la suivante à relire

    # Bouteille 3 : un raccourci tapé dans un champ reste du texte.
    clavier.press("Tab")
    clavier.press("Tab")  # domaine
    clavier.type("Jeroboam K Z E")
    assert page.url.endswith(f"/relecture/{b[2]}")  # ni J, ni K, ni Z, ni E n'ont agi
    assert page.eval_on_selector("#saisie-domaine", "e => e.value") == "Jeroboam K Z E"
    clavier.press("Escape")
    tout_est_enregistre(page)
    clavier.press("Enter")
    sur_la_bouteille(page, b[3])

    # Bouteille 4 : saisie dans un champ texte puis Ctrl+Entrée sans le quitter : rien n'est perdu.
    clavier.press("Tab")
    clavier.press("Tab")
    clavier.type("Château Ctrl")
    clavier.press("Control+Enter")
    sur_la_bouteille(page, b[4])

    # Bouteille 5 : une quantité refusée bloque Ctrl+Entrée, avec un message clair.
    clavier.press("Tab")
    clavier.type("0")
    clavier.press("Control+Enter")
    page.wait_for_selector("#messages .message.alerte", timeout=10_000)
    assert "Bouteille non validée" in page.inner_text("#messages")
    assert "Quantité invalide" in page.inner_text("#pied-quantite")
    assert page.url.endswith(f"/relecture/{b[4]}")
    clavier.type("2")  # le champ refusé a repris le focus, contenu sélectionné
    clavier.press("Control+Enter")
    sur_la_bouteille(page, b[5])

    # Bouteilles 6 à 10 : vues, validées.
    for suivante in b[6:]:
        clavier.press("Enter")
        sur_la_bouteille(page, suivante)
    clavier.press("Enter")
    page.wait_for_url("**/recapitulatif*", timeout=10_000)
    assert "Toutes les bouteilles sont validées" in page.inner_text("main")
    assert erreurs == []

    # L'export reflète les corrections.
    feuille = load_workbook(io.BytesIO(httpx.get(f"{application}/inventaires/{inventaire_id}/export").content)).active
    entetes = [c.value for c in feuille[1]]
    lignes = [dict(zip(entetes, [c.value for c in ligne])) for ligne in feuille.iter_rows(min_row=2)]
    par_domaine = {ligne["Domaine / Château"]: ligne for ligne in lignes}
    premiere = par_domaine["Domaine Clavier"]
    assert (premiere["Qté"], premiere["Millésime"], premiere["Couleur"]) == (3, "2015", "Blanc")
    assert "Jeroboam K Z E" in par_domaine and "Château Ctrl" in par_domaine
    assert sum(ligne["Qté"] for ligne in lignes) == 3 + 2 + 8

    # L'historique dit qui, et le temps de relecture est enregistré.
    fiche = httpx.get(f"{application}/inventaires/{inventaire_id}/bouteilles/{b[0]}").json()
    assert {h["auteur"] for h in fiche["historique"]} == {AUTEUR}
    stats = httpx.get(f"{application}/inventaires/{inventaire_id}").json()["statistiques"]
    assert stats["bouteilles_chronometrees"] == 10 and stats["temps_relecture_total_ms"] > 0


def test_le_temps_passe_sur_une_bouteille_compte_meme_sans_la_valider(application, ordinateur, tmp_path):
    """Ouverte, regardée, quittée sans validation : son temps est envoyé en la
    quittant (decisions.md 0169)."""
    inventaire_id = inventaire_extrait(application, tmp_path, 2)
    b = ids(application, inventaire_id)
    page = ordinateur.new_page()
    page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture/{b[0]}")
    sur_la_bouteille(page, b[0])
    page.wait_for_function("Number(document.getElementById('temps').value) >= 1500", timeout=10_000)
    page.keyboard.press("k")  # la suivante, sans valider
    sur_la_bouteille(page, b[1])

    def statistiques():
        return httpx.get(f"{application}/inventaires/{inventaire_id}").json()["statistiques"]

    attendre(lambda: statistiques()["temps_relecture_total_ms"] >= 1500, message="temps envoyé en quittant la bouteille")
    assert statistiques()["bouteilles_chronometrees"] == 1
    assert httpx.get(f"{application}/inventaires/{inventaire_id}/bouteilles/{b[0]}").json()["statut"] == "extraite"


def test_revenir_au_modele_ou_retaper_la_meme_valeur_ne_bloque_pas(application, ordinateur, tmp_path):
    """Rapport du testeur, T1-M1 : après « Revenir à la valeur du modèle », ou une
    saisie revenue à l'identique, l'écran ne doit pas rester « en cours »."""
    inventaire_id = inventaire_extrait(application, tmp_path, 3)
    b = ids(application, inventaire_id)
    page = ordinateur.new_page()
    page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture/{b[0]}")
    sur_la_bouteille(page, b[0])

    page.fill("#saisie-millesime", "1961")
    page.keyboard.press("Escape")
    tout_est_enregistre(page)
    page.click("#pied-millesime button:has-text('Revenir')")
    tout_est_enregistre(page)
    page.keyboard.press("k")
    sur_la_bouteille(page, b[1])

    domaine = page.input_value("#saisie-domaine")
    page.click("#saisie-domaine")
    page.keyboard.press("End")
    page.keyboard.type("x")
    page.keyboard.press("Backspace")
    assert page.input_value("#saisie-domaine") == domaine
    page.keyboard.press("Escape")
    tout_est_enregistre(page)
    page.keyboard.press("k")
    sur_la_bouteille(page, b[2])


def test_deux_onglets_sur_la_meme_bouteille(application, ordinateur, tmp_path):
    inventaire_id = inventaire_extrait(application, tmp_path, 2)
    premiere = ids(application, inventaire_id)[0]
    adresse = f"{application}/app/inventaires/{inventaire_id}/relecture/{premiere}"
    onglet_a, onglet_b = ordinateur.new_page(), ordinateur.new_page()
    onglet_a.goto(adresse)
    onglet_b.goto(adresse)

    onglet_b.fill("#saisie-millesime", "2001")
    onglet_b.keyboard.press("Escape")
    tout_est_enregistre(onglet_b)

    onglet_a.fill("#saisie-millesime", "1990")
    onglet_a.keyboard.press("Escape")
    onglet_a.wait_for_selector("#pied-millesime [data-conflit]", timeout=10_000)
    assert "modifiée ailleurs" in onglet_a.inner_text("#pied-millesime")
    assert "2001" in onglet_a.inner_text("#pied-millesime")
    assert onglet_a.inner_text("#indicateur") == "Une saisie n'est pas enregistrée"
    onglet_a.keyboard.press("k")  # changer de bouteille : bloqué, avec la raison
    onglet_a.wait_for_selector("#messages .message.alerte", timeout=5_000)
    assert "modifié ailleurs" in onglet_a.inner_text("#messages")
    assert onglet_a.url == adresse

    onglet_a.click("#pied-millesime button:has-text('Enregistrer quand même')")
    tout_est_enregistre(onglet_a)
    historique = httpx.get(f"{application}/inventaires/{inventaire_id}/bouteilles/{premiere}").json()["historique"]
    assert [h["nouvelle_valeur"] for h in historique if h["champ"] == "millesime"] == ["2001", "1990"]


def test_une_coupure_reseau_est_signalee_rattrapee_et_bloque_le_changement_de_bouteille(application, ordinateur, tmp_path):
    """« Erreur, nouvel essai » : rien n'est perdu, et on ne passe pas à la suivante
    tant que la correction n'est pas enregistrée (guide, §4)."""
    inventaire_id = inventaire_extrait(application, tmp_path, 2)
    premiere = ids(application, inventaire_id)[0]
    page = ordinateur.new_page()
    coupures = {"restantes": 2}

    def reseau_instable(route):
        if route.request.method == "POST" and coupures["restantes"] > 0:
            coupures["restantes"] -= 1
            route.abort("internetdisconnected")
        else:
            route.continue_()

    page.route("**/champ/*", reseau_instable)
    page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture/{premiere}")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.keyboard.type("Domaine du réseau coupé")
    page.keyboard.press("Escape")
    page.wait_for_function("document.getElementById('indicateur').textContent.startsWith('Erreur d\\'enregistrement')",
                           timeout=10_000)
    page.keyboard.press("k")  # bloqué tant que ce n'est pas enregistré
    page.wait_for_selector("#messages .message.alerte", timeout=5_000)
    assert "pas encore enregistré" in page.inner_text("#messages")
    assert page.url.endswith(f"/relecture/{premiere}")

    tout_est_enregistre(page)  # nouvel essai automatique
    assert coupures["restantes"] == 0
    fiche = httpx.get(f"{application}/inventaires/{inventaire_id}/bouteilles/{premiere}").json()
    assert fiche["valeurs_courantes"]["domaine"] == "Domaine du réseau coupé"
    page.keyboard.press("k")
    page.wait_for_url(f"**/relecture/{ids(application, inventaire_id)[1]}*", timeout=10_000)


@pytest.fixture
def trois_cents(tmp_path):
    """300 bouteilles extraites, préparées en base avant le démarrage du serveur."""
    base = tmp_path / "base.db"
    photos = generer_photos_fictives(tmp_path / "photos", 300)
    with session_de_base(base) as session:
        cree = creer_inventaire(session, "Maison Test", CONFIG_TEST, photos, "Trois cents", tmp_path / "stockage")
        extraire_inventaire(session, cree.inventaire_id, ExtracteurFactice(charger_config(CONFIG_TEST)), tmp_path / "stockage")
    processus, url = demarrer(tmp_path, base)
    try:
        yield url, cree.inventaire_id
    finally:
        processus.kill()
        processus.wait(30)


def test_passer_a_la_suivante_est_immediat_sur_300_bouteilles(trois_cents, ordinateur):
    url, inventaire_id = trois_cents
    page = ordinateur.new_page()
    demandes = []
    page.on("request", lambda requete: demandes.append(requete.url))
    page.goto(f"{url}/app/inventaires/{inventaire_id}/relecture")
    page.wait_for_function("document.getElementById('photo-active').complete")
    assert "/ 300" in page.inner_text(".position")

    durees = []
    for _ in range(12):
        suivante = page.get_attribute("[data-relecture]", "data-suivante")
        photo_suivante = page.get_attribute("link[rel=prefetch]", "href")
        page.wait_for_function(  # préchargée pendant la relecture de la bouteille courante
            "u => performance.getEntriesByType('resource').some(e => e.name.endsWith(u))", arg=photo_suivante)
        debut = time.perf_counter()
        page.keyboard.press("Enter")
        page.wait_for_url(f"{url}{suivante}", timeout=10_000)
        page.wait_for_function("document.getElementById('photo-active').complete"
                               " && document.getElementById('photo-active').naturalWidth > 0")
        durees.append(time.perf_counter() - debut)
    mediane = statistics.median(durees)
    print(f"\nPassage à la suivante (300 bouteilles) : médiane {mediane * 1000:.0f} ms, "
          f"max {max(durees) * 1000:.0f} ms")
    assert mediane < 0.5, durees  # perçu comme immédiat
    assert sum(1 for d in demandes if "taille=reduite" in d) >= 12


def test_une_bouteille_plus_disponible_n_est_jamais_dite_enregistree(application, ordinateur, tmp_path):
    """T4-B4 : une réponse 404 (bouteille mise à la corbeille, inventaire clos
    ailleurs) : ni la validation ni la saisie ne sont dites faites (contrainte 5)."""
    inventaire_id = inventaire_extrait(application, tmp_path, 2)
    premiere = ids(application, inventaire_id)[0]
    page = ordinateur.new_page()

    def disparue(route):
        if route.request.method == "POST":
            route.fulfill(status=404, content_type="text/html", body="<p>Introuvable</p>")
        else:
            route.continue_()

    page.route("**/valider", disparue)
    page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture/{premiere}")
    sur_la_bouteille(page, premiere)
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#messages .message.alerte", timeout=5_000)
    assert "pas validée" in page.inner_text("#messages")

    page.route("**/champ/*", disparue)
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.keyboard.type("Domaine disparu")
    page.keyboard.press("Escape")
    page.wait_for_function("document.getElementById('messages').textContent.includes('pas enregistrée')",
                           timeout=10_000)
    page.wait_for_timeout(300)
    assert page.inner_text("#indicateur") != "Tout est enregistré"
    assert page.url.endswith(f"/relecture/{premiere}")
    fiche = httpx.get(f"{application}/inventaires/{inventaire_id}/bouteilles/{premiere}").json()
    assert fiche["statut"] == "extraite" and fiche["valeurs_courantes"]["domaine"] != "Domaine disparu"


def test_un_double_appui_sur_valider_ne_valide_qu_une_bouteille(application, ordinateur, tmp_path):
    """T4-B2 : deux appuis à 250 ms ne valident jamais la bouteille suivante sans l'avoir vue."""
    inventaire_id = inventaire_extrait(application, tmp_path, 3)
    b = ids(application, inventaire_id)
    page = ordinateur.new_page()
    page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture/{b[0]}")
    sur_la_bouteille(page, b[0])
    page.wait_for_timeout(600)  # passé le délai de garde de l'affichage
    page.click("#valider")
    page.wait_for_timeout(250)
    try:
        page.click("#valider", timeout=1000)
    except Exception:  # bouton désactivé ou page en train de changer : c'est le but
        pass
    sur_la_bouteille(page, b[1])
    page.wait_for_timeout(800)
    statuts = [httpx.get(f"{application}/inventaires/{inventaire_id}/bouteilles/{x}").json()["statut"] for x in b]
    assert statuts == ["validee", "extraite", "extraite"]


def test_au_telephone_le_premier_champ_se_voit_sans_defiler(application, ordinateur, tmp_path):
    """T4-D4 : navigation sur une ligne, photo plus basse, vignettes sur une rangée :
    le premier champ est dans le premier écran d'un téléphone."""
    inventaire_id = inventaire_extrait(application, tmp_path, 2)
    premiere = ids(application, inventaire_id)[0]
    telephone = ordinateur.browser.new_context(viewport={"width": 412, "height": 839}, is_mobile=True, has_touch=True)
    try:
        page = telephone.new_page()
        page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture/{premiere}")
        sur_la_bouteille(page, premiere)
        haut = page.evaluate("document.querySelector('.saisie').getBoundingClientRect().top")
        assert haut < 839 - 80, haut  # au-dessus de la barre « Valider »
        hauteur_nav = page.evaluate("document.querySelector('.navigation-relecture').getBoundingClientRect().height")
        assert hauteur_nav < 60, hauteur_nav  # une seule ligne
    finally:
        telephone.close()


def test_au_telephone_un_seul_appui_valide_meme_depuis_un_champ(application, ordinateur, tmp_path):
    """T6-B1 : champ actif, un seul appui sur « Valider » valide et passe à la
    suivante (la mise en page ne bouge plus à la perte du focus). T6-B2 : un
    refus de validation corrigé disparaît. T6-B4 : la barre garde sa forme sur la
    première bouteille."""
    inventaire_id = inventaire_extrait(application, tmp_path, 3)
    b = ids(application, inventaire_id)
    telephone = ordinateur.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    try:
        page = telephone.new_page()
        page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture/{b[0]}")
        sur_la_bouteille(page, b[0])
        hauteur_nav = page.evaluate("document.querySelector('.navigation-relecture').getBoundingClientRect().height")
        assert hauteur_nav < 60, hauteur_nav  # première bouteille : « ← » inactif court aussi

        page.wait_for_timeout(700)  # passé le délai de garde de l'affichage
        page.locator("#saisie-domaine").tap()
        page.locator("#saisie-domaine").fill("Domaine du doigt")
        page.tap("#valider")  # UN appui, le champ ayant encore le focus
        sur_la_bouteille(page, b[1])
        statut = httpx.get(f"{application}/inventaires/{inventaire_id}/bouteilles/{b[0]}").json()["statut"]
        assert statut == "validee"
    finally:
        telephone.close()


def test_un_refus_de_validation_corrige_disparait(application, ordinateur, tmp_path):
    """T6-B2 : quantité 0 puis Ctrl+Entrée : refus ; la quantité corrigée et
    enregistrée, le refus devenu faux disparaît."""
    inventaire_id = inventaire_extrait(application, tmp_path, 2)
    premiere = ids(application, inventaire_id)[0]
    page = ordinateur.new_page()
    page.goto(f"{application}/app/inventaires/{inventaire_id}/relecture/{premiere}")
    sur_la_bouteille(page, premiere)
    page.locator("#saisie-quantite").fill("0")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#messages [data-refus-validation]", timeout=10_000)
    page.locator("#saisie-quantite").fill("2")
    page.keyboard.press("Escape")  # quitte le champ : il s'enregistre
    page.wait_for_function("!document.querySelector('#messages [data-refus-validation]')", timeout=10_000)
