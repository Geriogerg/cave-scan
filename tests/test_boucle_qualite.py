"""Points relevés par l'agent testeur-web (boucle qualité, docs/tests/journal.md),
vérifiés ici pour qu'ils ne reviennent pas."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from src.config.maison import charger_config
from src.donnees.modeles import Extraction
from src.extract.fixture_extract import FixtureExtractor
from src.services.extraction import extraire_inventaire
from src.services.inventaires import charger_inventaire, creer_inventaire
from src.services.pilotage import avancement
from tests.conftest import CONFIG_TEST
from tests.test_api import api, charges, envoyer, extraire_en_arriere_plan  # noqa: F401
from tests.test_extraction import ExtracteurScenario

AUTEUR = {"X-Auteur": "Expert test"}


def test_la_duree_d_une_analyse_terminee_ne_grandit_plus(session, nom_maison, dossier_photos, stockage):
    """T1-m1 : « Analyse terminée en X s » s'arrête à la dernière lecture."""
    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario(), stockage)
    inventaire = charger_inventaire(session, cree.inventaire_id)
    premiere = session.scalar(select(func.min(Extraction.cree_le)))
    derniere = session.scalar(select(func.max(Extraction.cree_le)))
    inventaire.extraction_lancee_le = premiere - timedelta(seconds=5)
    session.commit()
    etat = avancement(session, cree.inventaire_id)
    assert etat.terminee
    assert etat.ecoule_s == (derniere - inventaire.extraction_lancee_le).total_seconds()
    assert avancement(session, cree.inventaire_id).ecoule_s == etat.ecoule_s


def test_inventaire_clos_la_relecture_propose_la_suivante_au_lieu_de_valider(api, dossier_photos):
    """T1-m9 : en lecture seule, le bouton passe à la suivante, sans requête refusée."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    ids = [b["id"] for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]]
    api.post(f"/app/inventaires/{inventaire_id}/clore")
    page = api.get(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}").text
    assert "data-lecture-seule" in page and "Bouteille suivante" in page
    assert 'type="submit" class="bouton principal" id="valider"' not in page


def test_remettre_une_bouteille_le_dit(api, dossier_photos):
    """T1-m11 : la remise dans l'inventaire affiche ce qui s'est passé."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    premiere = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"][0]["id"]
    api.post(f"/app/inventaires/{inventaire_id}/relecture/{premiere}/retirer", headers=AUTEUR)
    page = api.post(f"/app/inventaires/{inventaire_id}/bouteilles/{premiere}/remettre", headers=AUTEUR).text
    assert "Bouteille remise dans l&#39;inventaire" in page


def test_une_adresse_mal_formee_ou_inconnue_donne_une_page_en_francais(api):
    """T1-m12 : ni « inventaire_id », ni JSON brut dans le navigateur."""
    mal_formee = api.get("/app/inventaires/abc/suivi")
    assert mal_formee.status_code == 404 and "Cette adresse n&#39;existe pas" in mal_formee.text
    assert "inventaire_id" not in mal_formee.text
    inconnue = api.get("/nimportequoi", headers={"Accept": "text/html"})
    assert inconnue.status_code == 404 and inconnue.text.lstrip().startswith("<!doctype html>")
    assert api.get("/nimportequoi").json()["code"] == "introuvable"  # l'API garde son JSON


def test_une_quantite_demesuree_est_refusee_en_clair_partout(api, dossier_photos):
    """T2-B1 : 99999999999999999999 faisait une erreur 500 (SQLite)."""
    from src.services.relecture import CorrectionRefusee, quantite_valide

    enorme = "99999999999999999999"
    try:
        quantite_valide(enorme)
    except CorrectionRefusee as refus:
        assert "Quantité trop grande" in str(refus)
    else:
        raise AssertionError("quantité démesurée acceptée")

    from src.services.depot import _quantite
    from src.services.envoi import EnvoiRefuse

    try:
        _quantite(int(enorme))
    except EnvoiRefuse as refus:
        assert "Quantité trop grande" in str(refus)
    else:
        raise AssertionError("quantité démesurée acceptée au dépôt")

    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    premiere = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"][0]["id"]
    reponse = api.post(f"/app/inventaires/{inventaire_id}/relecture/{premiere}/champ/quantite",
                       data={"quantite": enorme}, headers={"HX-Request": "true", **AUTEUR})
    assert reponse.status_code == 422 and "Quantité trop grande" in reponse.text


def test_un_texte_trop_long_est_refuse(session, nom_maison, dossier_photos, stockage):
    """T2-B5 : un collage accidentel de 5 000 caractères."""
    import pytest

    from src.services.relecture import CorrectionRefusee, corriger

    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario(), stockage)
    premiere = charger_inventaire(session, cree.inventaire_id).bouteilles[0]
    with pytest.raises(CorrectionRefusee, match="1000 au plus"):
        corriger(session, premiere.id, "cuvee", "x" * 5000, "expert")


def test_les_consignes_d_origine_legerement_modifiees_ne_declenchent_pas_l_alerte_few_shot(tmp_path):
    """T3-R8 : les citations du texte d'origine (« observee »…) ne sont pas un exemple ;
    une citation AJOUTÉE par la maison, si."""
    import json

    from src.config.maison import charger_config
    from src.extract.consignes import CONSIGNES_MODIFIABLES

    def avertissements(consignes):
        brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
        brut["consignes"] = consignes
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
        return [a for a in charger_config(chemin).avertissements if a.startswith("Consignes générales")]

    ajout_sans_exemple = "\nPrécise toujours le climat s'il est écrit."
    ajout_avec_exemple = "\nPar exemple, réponds « Château Margaux 1990 »."
    assert avertissements(CONSIGNES_MODIFIABLES + ajout_sans_exemple) == []
    assert avertissements(CONSIGNES_MODIFIABLES + ajout_avec_exemple) != []


def test_le_score_signale_des_consignes_modifiees(tmp_path, capsys):
    """R5 : avec des consignes modifiées, le rapport de score le dit ; avec celles
    d'origine, rien."""
    import json

    import run_v0
    from src.compare.compare_listings import AVERTISSEMENT_CONSIGNES

    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["consignes"] = "Lis les étiquettes avec soin ; précise toujours le climat s'il est écrit."
    modifiee = tmp_path / "modifiee.json"
    modifiee.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")

    assert run_v0.main(["--dry-run", "--maison", str(CONFIG_TEST), "--sortie", str(tmp_path / "a.xlsx")]) == 0
    assert AVERTISSEMENT_CONSIGNES not in capsys.readouterr().out
    assert run_v0.main(["--dry-run", "--maison", str(modifiee), "--sortie", str(tmp_path / "b.xlsx")]) == 0
    sortie = capsys.readouterr().out
    assert AVERTISSEMENT_CONSIGNES in sortie and "Comparaison auto vs manuel" in sortie


def test_des_consignes_recopiees_a_l_identique_ne_sont_pas_des_consignes_modifiees(tmp_path, capsys):
    """T5-R5 : une config qui recopie le texte d'origine (fins de ligne Windows
    comprises) envoie le texte d'origine au caractère près, et le score ne la dit
    pas modifiée."""
    import json

    import run_v0
    from src.compare.compare_listings import AVERTISSEMENT_CONSIGNES
    from src.extract.consignes import CONSIGNES_MODIFIABLES, SYSTEM_PROMPT, consignes_systeme

    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["consignes"] = CONSIGNES_MODIFIABLES.replace("\n", "\r\n") + "\n"
    recopiee = tmp_path / "recopiee.json"
    recopiee.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")

    config = charger_config(recopiee)
    assert config.consignes is None and consignes_systeme(config) == SYSTEM_PROMPT
    assert run_v0.main(["--dry-run", "--maison", str(recopiee), "--sortie", str(tmp_path / "a.xlsx")]) == 0
    assert AVERTISSEMENT_CONSIGNES not in capsys.readouterr().out


def test_sans_listing_le_rapport_signale_aussi_des_consignes_modifiees(tmp_path, capsys):
    """T5-R5 : la reprise d'un inventaire sans listing manuel (signaux du modèle
    seuls) avertit aussi quand ses consignes ont été modifiées."""
    import json

    import run_v0
    from src.compare.compare_listings import AVERTISSEMENT_CONSIGNES

    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["consignes"] = "Lis les étiquettes avec soin ; précise toujours le climat s'il est écrit."
    modifiee = tmp_path / "modifiee.json"
    modifiee.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    base = tmp_path / "base.db"

    assert run_v0.main(["--dry-run", "--maison", str(modifiee), "--base", str(base),
                        "--sortie", str(tmp_path / "a.xlsx")]) == 0
    capsys.readouterr()
    assert run_v0.main(["--inventaire", "1", "--base", str(base), "--sortie", str(tmp_path / "b.xlsx")]) == 0
    sortie = capsys.readouterr().out
    assert "PAS DE SCORE" in sortie and AVERTISSEMENT_CONSIGNES in sortie


def test_l_excel_refuse_depuis_un_ecran_revient_au_suivi_avec_la_raison(api, dossier_photos):
    """T3-D4 : un Excel refusé (bouteille sans ligne) ne laisse ni téléchargement
    annulé en silence, ni JSON brut : retour au suivi, avec la raison."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]  # pas encore analysé
    refus = api.get(f"/app/inventaires/{inventaire_id}/excel", follow_redirects=False)
    assert refus.status_code == 303 and refus.headers["location"].endswith("/suivi?fait=excel_refuse")
    assert "pas encore disponible" in api.get(refus.headers["location"]).text
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    fichier = api.get(f"/app/inventaires/{inventaire_id}/excel")
    assert fichier.status_code == 200 and "attachment" in fichier.headers["content-disposition"]


def test_suggestions_du_tour_3(api, dossier_photos):
    """T3-DS2 : l'Excel porte le nom de la vente ; T3-DS3 : bouteille signalée, Valider
    désactivé avec la raison ; T3-DS6 : relecture finie, « Clore » sur place."""
    inventaire_id = envoyer(api, dossier_photos, nom="Cave Dupont").json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    entete = api.get(f"/app/inventaires/{inventaire_id}/excel").headers["content-disposition"]
    assert "filename*=UTF-8''Cave%20Dupont" in entete and "%E2%80%94" in entete and entete.endswith(".xlsx")

    ids = [b["id"] for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]]
    api.post(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}/signaler", headers=AUTEUR)
    page = api.get(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}").text
    assert 'id="valider" disabled' in page and "problème de photos signalé" in page

    api.post(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}/lever-signalement", headers=AUTEUR)
    for bouteille_id in ids:
        api.post(f"/inventaires/{inventaire_id}/bouteilles/{bouteille_id}/valider", json={}, headers=AUTEUR)
    recap = api.get(f"/app/inventaires/{inventaire_id}/recapitulatif").text
    assert f'href="/app/inventaires/{inventaire_id}/clore"' in recap


def test_restaurer_un_inventaire_analyse_laisse_reanalyser(session, nom_maison, dossier_photos, stockage):
    """T4-D1 : corbeille puis restauration d'un inventaire fini : « Réanalyser »
    marche (plus d'impasse « analyse annulée »)."""
    from src.services.cas_particuliers import reanalyser
    from src.services.cycle_de_vie import restaurer, supprimer
    from src.services.pilotage import lancer

    cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage)
    lancer(session, cree.inventaire_id)
    extraire_inventaire(session, cree.inventaire_id, ExtracteurScenario(), stockage)
    supprimer(session, cree.inventaire_id, "Expert test")
    restaurer(session, cree.inventaire_id, "Expert test")
    inventaire = charger_inventaire(session, cree.inventaire_id)
    assert inventaire.extraction == "lancee"
    assert reanalyser(session, inventaire.bouteilles[0].id, "Expert test") is True


def test_une_citation_dans_les_consignes_n_est_pas_un_exemple(tmp_path):
    """T3-D2 : « Grand Cru » à recopier tel quel est une précision, pas un exemple."""
    import json

    from src.config.maison import charger_config
    from src.extract.consignes import CONSIGNES_MODIFIABLES

    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["consignes"] = CONSIGNES_MODIFIABLES + "\nPRÉCISION : la mention « Grand Cru » se recopie telle quelle."
    chemin = tmp_path / "c.json"
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    alertes = [a for a in charger_config(chemin).avertissements if a.startswith("Consignes")]
    assert alertes == [] and not any("few-shot" in a for a in charger_config(chemin).avertissements)


def test_une_photo_abimee_ou_demesuree_est_refusee_en_clair(session, nom_maison, dossier_photos, stockage, monkeypatch, tmp_path):
    """T4-B1 (bloquant) : une photo tronquée ou de trop de pixels donnait une 500
    et bloquait le dépôt ; elle est refusée avec la raison."""
    import io

    import pytest
    from PIL import Image

    from src.services.depot import ajouter_photo, creer_brouillon
    from src.services.envoi import EnvoiRefuse

    brouillon = creer_brouillon(session, nom_maison, CONFIG_TEST, "Vente")
    tampon = io.BytesIO()
    Image.new("RGB", (1600, 1200), (120, 40, 60)).save(tampon, "JPEG", quality=95)
    tronquee = tampon.getvalue()[: len(tampon.getvalue()) // 2]
    with pytest.raises(EnvoiRefuse, match="abîmée"):
        ajouter_photo(session, brouillon.inventaire_id, io.BytesIO(tronquee), "tronque.jpg", stockage, bouteille="b1", numero=1)

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # 100 × 100 = 10 000 : plus de 2 × la limite
    petite = io.BytesIO()
    Image.new("RGB", (100, 100)).save(petite, "PNG")
    with pytest.raises(EnvoiRefuse, match="trop de pixels"):
        ajouter_photo(session, brouillon.inventaire_id, io.BytesIO(petite.getvalue()), "enorme.png", stockage, bouteille="b1", numero=1)


def test_les_ecrans_ne_sont_jamais_servis_depuis_le_cache(api, dossier_photos):
    """T4-B3 : « retour arrière » = page rechargée, à jour."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    assert api.get(f"/app/inventaires/{inventaire_id}/suivi").headers["cache-control"] == "no-store"


def test_relecture_position_et_bouton_apres_remise_a_relire(api, dossier_photos):
    """T4-B8 : après un retrait, « 2 / 5 » et non « 3 / 5 » ; T4-B9 : une bouteille
    validée puis corrigée retrouve « Valider et passer à la suivante »."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    ids = [b["id"] for b in api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"]]
    api.post(f"/app/inventaires/{inventaire_id}/relecture/{ids[1]}/retirer", headers=AUTEUR)
    page = api.get(f"/app/inventaires/{inventaire_id}/relecture/{ids[2]}").text
    assert "<strong>2</strong> / 5" in page

    api.post(f"/inventaires/{inventaire_id}/bouteilles/{ids[0]}/valider", json={}, headers=AUTEUR)
    reponse = api.post(f"/app/inventaires/{inventaire_id}/relecture/{ids[0]}/champ/millesime",
                       data={"millesime": "1999"}, headers={"HX-Request": "true", **AUTEUR})
    assert 'id="valider" hx-swap-oob="true"' in reponse.text and "Valider et passer à la suivante" in reponse.text


def test_un_numero_demesure_dans_l_adresse_est_une_page_introuvable(api):
    """T4-B14 : plus de 19 chiffres : 404 en français, pas une erreur 500."""
    reponse = api.get("/app/inventaires/99999999999999999999/suivi")
    assert reponse.status_code == 404 and "n&#39;existe pas" in reponse.text


def test_suggestions_du_tour_4(api, dossier_photos):
    """T4-DS4 : un millésime inhabituel est accepté mais signalé ; T4-DS3 : le suivi
    distingue bouteilles et exemplaires."""
    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    premiere = api.get(f"/inventaires/{inventaire_id}/bouteilles").json()["bouteilles"][0]["id"]
    reponse = api.post(f"/app/inventaires/{inventaire_id}/relecture/{premiere}/champ/millesime",
                       data={"millesime": "20152009"}, headers={"HX-Request": "true", **AUTEUR})
    assert reponse.status_code == 200 and "Inhabituel" in reponse.text
    normal = api.post(f"/app/inventaires/{inventaire_id}/relecture/{premiere}/champ/millesime",
                      data={"millesime": "2015"}, headers={"HX-Request": "true", **AUTEUR})
    assert "Inhabituel" not in normal.text

    api.put(f"/inventaires/{inventaire_id}/bouteilles/{premiere}/quantite", json={"quantite": 3}, headers=AUTEUR)
    assert "8 exemplaires" in api.get(f"/app/inventaires/{inventaire_id}/suivi").text


def test_une_quantite_demesuree_ou_exotique_est_refusee_en_clair(api):
    """T5-B4 : plus de 4 300 chiffres (Python refuse de les convertir) ou « ² »
    (un chiffre pour `isdigit`, pas pour `int`) : un refus en clair, jamais une 500 ;
    la saisie citée est coupée."""
    import pytest

    from src.services.relecture import CorrectionRefusee, quantite_valide
    from tests.test_pages import HX, attente, creer, deposer

    for saisie, raison in (("9" * 4400, "trop grande"), ("0" * 4400, "invalide"), ("²", "invalide"), ("007", None)):
        if raison is None:
            assert quantite_valide(saisie) == 7
            continue
        with pytest.raises(CorrectionRefusee, match=raison) as refus:
            quantite_valide(saisie)
        assert len(str(refus.value)) < 120

    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=1, photos=1)
    groupe = attente(api, inventaire_id)[0]["groupe_id"]
    refus = api.post(f"/app/inventaires/{inventaire_id}/verifier/quantite/{groupe}", data={"quantite": "9" * 4400}, headers=HX)
    assert refus.status_code < 500 and "trop grande" in refus.text
    lancement = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX,
                         data={"groupe": [str(groupe)], "quantite": ["9" * 4400]})
    assert "trop grande" in lancement.text and "Bouteille 1 :" in lancement.text


def test_le_refus_de_quantite_dans_sa_carte_ne_redit_pas_son_numero(api):
    """T5-B12 : la carte porte déjà « Bouteille 1 » : le refus dit seulement quoi faire."""
    from tests.test_pages import HX, attente, creer, deposer

    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=1, photos=1)
    groupe = attente(api, inventaire_id)[0]["groupe_id"]
    refus = api.post(f"/app/inventaires/{inventaire_id}/verifier/quantite/{groupe}", data={"quantite": "2,5"}, headers=HX).text
    message = refus.split('id="refus-quantite">')[1].split("</span>")[0]
    assert message.startswith("Quantité invalide") and "Bouteille" not in message


def test_le_nom_de_la_vente_est_borne_aussi_cote_serveur(api):
    """T5-B10 : 5 000 caractères ou un caractère NUL envoyés sans passer par le
    navigateur : refus « 200 caractères au plus » ; caractères de contrôle retirés."""
    trop_long = api.post("/app/nouveau", data={"nom": "x" * 5000}, follow_redirects=False)
    assert trop_long.status_code == 422 and "200 caractères au plus" in trop_long.text
    cree = api.post("/app/nouveau", data={"nom": "Vente\x00 de\tprintemps"}, follow_redirects=False)
    assert cree.status_code == 303
    noms = [i["nom"] for i in api.get("/inventaires").json()]
    assert "Vente  de printemps" in noms


def test_verifier_une_vente_deja_lancee_renvoie_au_suivi_avec_la_raison(api):
    """T5-B5 : retour arrière après « Lancer » : plus rien à vérifier ; le suivi le
    dit au lieu d'une page vide et muette."""
    from tests.test_pages import HX, attente, creer, deposer

    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=1, photos=1)
    groupe = attente(api, inventaire_id)[0]["groupe_id"]
    lance = api.post(f"/app/inventaires/{inventaire_id}/lancer", headers=HX, data={"groupe": [str(groupe)], "quantite": ["1"]})
    assert lance.status_code == 204
    retour = api.get(f"/app/inventaires/{inventaire_id}/verifier", follow_redirects=False)
    assert retour.status_code == 303 and retour.headers["location"].endswith("/suivi?fait=deja_lancee")
    assert "Analyse déjà lancée" in api.get(retour.headers["location"]).text


def test_une_quantite_refusee_reste_dans_son_champ(api):
    """T5-D1 : « 0 » refusé : le champ montre « 0 », pas l'ancienne quantité, à côté
    du refus qui le cite."""
    from tests.test_pages import HX, attente, creer, deposer

    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=1, photos=1)
    groupe = attente(api, inventaire_id)[0]["groupe_id"]
    api.post(f"/app/inventaires/{inventaire_id}/verifier/quantite/{groupe}", data={"quantite": "3"}, headers=HX)
    refus = api.post(f"/app/inventaires/{inventaire_id}/verifier/quantite/{groupe}", data={"quantite": "0"}, headers=HX).text
    carte = refus.split(f'id="groupe-{groupe}"')[1]
    assert 'value="0"' in carte and 'value="3"' not in carte and 'id="refus-quantite"' in carte
    assert api.get(f"/inventaires/{inventaire_id}/apercu").json()["bouteilles"][0]["quantite"] == 3


def test_lancer_une_seule_bouteille_dit_ses_photos(api):
    """T6-B7 : « Lancer l'analyse de 1 bouteille ? Ses photos… », pas « Leurs »."""
    from tests.test_pages import attente, creer, deposer

    inventaire_id = creer(api)
    deposer(api, inventaire_id, bouteilles=1, photos=1)
    assert attente(api, inventaire_id)
    page = api.get(f"/app/inventaires/{inventaire_id}/verifier").text
    assert "Ses photos ne pourront plus" in page and "Leurs photos" not in page


def test_finitions_du_tour_6(api, dossier_photos):
    """T6-S1, T6-S2, T6-S4, T6-D12 : libellés et ordre des champs."""
    from tests.test_api import charges, extraire_en_arriere_plan
    from tests.test_extraction import ExtracteurScenario  # noqa: F401
    from src.extract.fixture_extract import FixtureExtractor
    from src.config.maison import charger_config

    inventaire_id = envoyer(api, dossier_photos).json()["id"]
    extraire_en_arriere_plan(api, inventaire_id, FixtureExtractor(charges(), charger_config(CONFIG_TEST)))
    page = api.get(f"/app/inventaires/{inventaire_id}/relecture").text
    assert "Exemplaires à séparer" in page and "> ex.<" not in page
    signaler = page.split('/signaler"')[1].split("</form>")[0]
    assert signaler.index('name="motif"') < signaler.index("<button")
    assert "(bouteilles identiques)" in api.get(f"/app/inventaires/{inventaire_id}/depot").text


def test_une_quantite_vide_le_dit_sans_guillemets_vides():
    """T7-B4 : quantité effacée : « Quantité vide », pas « Quantité invalide («  ») »."""
    import pytest

    from src.services.relecture import CorrectionRefusee, quantite_valide

    with pytest.raises(CorrectionRefusee, match="Quantité vide"):
        quantite_valide("  ")

