"""Extraction en base : réponse brute conservée, trois classes d'erreurs, reprise.

Point 2 de la validation : `extract()` est construit à partir de
`extraire_brut()`, et la réponse brute est enregistrée AVANT d'être interprétée.
Point 5 : panne systématique enregistrée puis arrêt ; panne passagère réessayée
puis erreur sur la bouteille seule ; réponse inexploitable sur la bouteille
seule ; reprise sans refaire les bouteilles extraites.
"""

from __future__ import annotations

import json
import shutil
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors
from sqlalchemy import create_engine, func, select

from src.config.maison import charger_config
from src.donnees.modeles import Extraction, FicheBouteille, maintenant
from src.extract.base import Extractor, SortieModele, bouteille_depuis_sortie
from src.extract.consignes import version_prompt
from src.extract.fixture_extract import FixtureExtractor
from src.extract.gemini_extract import GeminiExtractor
from src.extract.gemini_extract import sortie_depuis_reponse as sortie_gemini
from src.extract.schema import schema_extraction
from src.extract.vision_extract import VisionExtractor
from src.extract.vision_extract import sortie_depuis_reponse as sortie_anthropic
from src.services import extraction as service
from src.services.extraction import (
    ExtractionArretee,
    derniere_extraction_reussie,
    extraire_bouteille,
    extraire_inventaire,
    reste_a_extraire,
)
from src.services.inventaires import charger_inventaire, creer_inventaire
from tests.conftest import CONFIG_TEST, FIXTURES


class ExtracteurScenario:
    """Faux modèle : succès par défaut, ou la panne prévue pour le n-ième appel."""

    modele = "scenario"
    version_prompt = "v-scenario"

    def __init__(self, scenario=None):
        self.scenario = scenario or {}
        self.appels = 0
        self.photos_recues = []

    def extraire_brut(self, etiquette, contre_etiquette=None, autres=None):
        self.appels += 1
        self.photos_recues.append((etiquette, contre_etiquette))
        cas = self.scenario.get(self.appels)
        if cas == "systematique":
            raise PermissionError("clé API invalide")
        trace = {"modele": self.modele, "version_prompt": self.version_prompt}
        if cas == "passagere":
            return SortieModele(brut=None, erreur="RateLimitError : quota dépassé", **trace)
        if cas == "illisible":
            return SortieModele(brut="{ pas du json", tokens_entree=900, tokens_sortie=10, **trace)
        brut = {"appellation": f"Appellation {self.appels}", "domaine": "Domaine X"}
        return SortieModele(brut=brut, tokens_entree=1000, tokens_sortie=200, **trace)

    def extract(self, etiquette, contre_etiquette=None, autres=None):
        return bouteille_depuis_sortie(self.extraire_brut(etiquette, contre_etiquette, autres))


@pytest.fixture
def inventaire_id(session, nom_maison, dossier_photos, stockage):
    return creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave", stockage).inventaire_id


def bouteilles(session, inventaire_id):
    return charger_inventaire(session, inventaire_id).bouteilles


def statuts(session, inventaire_id):
    return [b.statut for b in bouteilles(session, inventaire_id)]


def nb_extractions(session, bouteille):
    return session.scalar(
        select(func.count()).select_from(Extraction).where(Extraction.bouteille_id == bouteille.id)
    )


# --- point 2 : extract() est construit à partir d'extraire_brut() ---------------------------


@pytest.mark.parametrize(
    "fabrique",
    [
        lambda: FixtureExtractor([]),  # sans fixture : un appel direct lèverait IndexError
        lambda: VisionExtractor(client=object()),  # un vrai appel planterait sur object()
        lambda: GeminiExtractor(client=object(), pause_s=0),
    ],
    ids=["fixtures", "anthropic", "gemini"],
)
def test_extract_est_construit_a_partir_d_extraire_brut(fabrique, monkeypatch):
    extracteur = fabrique()
    sortie = SortieModele(brut={"appellation": "Sentinelle"}, modele="m", version_prompt="v")
    monkeypatch.setattr(extracteur, "extraire_brut", lambda *a, **k: sortie)
    assert extracteur.extract("etiquette.jpg", "contre.jpg").appellation == "Sentinelle"


@pytest.mark.parametrize(
    "fabrique",
    [
        lambda: FixtureExtractor([]),
        lambda: VisionExtractor(client=object()),
        lambda: GeminiExtractor(client=object(), pause_s=0),
    ],
    ids=["fixtures", "anthropic", "gemini"],
)
def test_les_trois_extracteurs_respectent_le_protocol(fabrique):
    assert isinstance(fabrique(), Extractor)


def test_la_reponse_brute_est_enregistree_avant_d_etre_interpretee(session, inventaire_id, stockage, monkeypatch):
    """Au moment même où l'interprétation tourne, la réponse est déjà en base,
    validée — vue par une AUTRE connexion. Et l'interprétation plante : la
    réponse reste."""
    url = str(session.get_bind().url)
    vue_pendant_l_interpretation = []

    def interpretation_qui_plante(brut, config):
        autre = create_engine(url)
        with autre.connect() as connexion:
            vue_pendant_l_interpretation.append(
                connexion.exec_driver_sql("SELECT sortie_brute FROM extraction").scalars().all()
            )
        autre.dispose()
        raise RuntimeError("bogue d'interprétation")

    monkeypatch.setattr(service, "interpreter", interpretation_qui_plante)
    bouteille = bouteilles(session, inventaire_id)[0]
    extraction = extraire_bouteille(session, bouteille.id, ExtracteurScenario(), stockage)

    assert len(vue_pendant_l_interpretation[0]) == 1
    assert json.loads(vue_pendant_l_interpretation[0][0])["appellation"] == "Appellation 1"
    assert extraction.sortie_brute == {"appellation": "Appellation 1", "domaine": "Domaine X"}
    assert "bogue d'interprétation" in extraction.erreur
    assert bouteille.statut == "erreur"


def test_une_reponse_illisible_reste_en_base_telle_quelle(session, inventaire_id, stockage):
    bouteille = bouteilles(session, inventaire_id)[0]
    extraction = extraire_bouteille(session, bouteille.id, ExtracteurScenario({1: "illisible"}), stockage)
    assert extraction.sortie_brute == "{ pas du json"
    assert "inexploitable" in extraction.erreur
    assert extraction.tokens_entree == 900  # l'appel a coûté : on le trace quand même
    assert bouteille.statut == "erreur"


# --- point 5 : trois classes d'erreurs -----------------------------------------------------


def test_panne_systematique_enregistree_puis_arret(session, inventaire_id, stockage):
    extracteur = ExtracteurScenario({3: "systematique"})
    with pytest.raises(ExtractionArretee, match="bouteille n°3") as capture:
        extraire_inventaire(session, inventaire_id, extracteur, stockage)

    assert isinstance(capture.value.cause, PermissionError)
    assert extracteur.appels == 3  # aucun appel après l'arrêt
    assert statuts(session, inventaire_id) == [
        "extraite", "extraite", "erreur", "a_extraire", "a_extraire", "a_extraire"
    ]
    troisieme = bouteilles(session, inventaire_id)[2]
    assert "panne systématique" in troisieme.extractions[-1].erreur
    assert "clé API invalide" in troisieme.extractions[-1].erreur


def test_panne_passagere_erreur_sur_la_bouteille_sans_bloquer_les_autres(session, inventaire_id, stockage):
    extracteur = ExtracteurScenario({3: "passagere"})
    bilan = extraire_inventaire(session, inventaire_id, extracteur, stockage)

    assert (bilan.extraites, bilan.en_erreur) == (5, 1)
    assert extracteur.appels == 6
    assert statuts(session, inventaire_id)[2] == "erreur"
    assert "RateLimitError" in bouteilles(session, inventaire_id)[2].extractions[-1].erreur


def test_reponse_inexploitable_erreur_sur_la_bouteille_seule(session, inventaire_id, stockage):
    bilan = extraire_inventaire(session, inventaire_id, ExtracteurScenario({2: "illisible"}), stockage)
    assert (bilan.extraites, bilan.en_erreur) == (5, 1)
    assert statuts(session, inventaire_id) == [
        "extraite", "erreur", "extraite", "extraite", "extraite", "extraite"
    ]


def test_la_reprise_ne_refait_pas_les_bouteilles_extraites(session, inventaire_id, stockage):
    """`--inventaire ID` après un arrêt : on repart de la bouteille en échec."""
    with pytest.raises(ExtractionArretee):
        extraire_inventaire(session, inventaire_id, ExtracteurScenario({3: "systematique"}), stockage)
    assert reste_a_extraire(session, inventaire_id) == 4

    reprise = ExtracteurScenario()
    bilan = extraire_inventaire(session, inventaire_id, reprise, stockage)

    assert reprise.appels == 4  # bouteilles 3 (en erreur), 4, 5, 6
    assert (bilan.extraites, bilan.deja_faites) == (4, 2)
    premieres = bouteilles(session, inventaire_id)[:3]
    assert [nb_extractions(session, b) for b in premieres] == [1, 1, 2]
    assert set(statuts(session, inventaire_id)) == {"extraite"}
    assert reste_a_extraire(session, inventaire_id) == 0


def test_une_extraction_interrompue_est_reprise(session, inventaire_id, stockage):
    """Coupure en plein appel (arrêt brutal) : la bouteille reste `en_cours` sans
    signe de vie ; passé le délai d'abandon, la reprise la refait — mais jamais
    une bouteille dont le worker est vivant (decisions.md 0110)."""
    abandonnee, vivante = bouteilles(session, inventaire_id)[:2]
    for bouteille, vu_le in ((abandonnee, maintenant() - timedelta(hours=1)), (vivante, maintenant())):
        bouteille.statut, bouteille.reservee_par = "en_cours", "worker-ancien"
        bouteille.reservee_le = bouteille.vu_le = vu_le
    session.commit()
    assert reste_a_extraire(session, inventaire_id) == 6

    reprise = ExtracteurScenario()
    bilan = extraire_inventaire(session, inventaire_id, reprise, stockage)

    assert reprise.appels == 5  # l'abandonnée et les 4 autres ; jamais la vivante
    assert (bilan.extraites, bilan.deja_faites) == (5, 0)
    assert statuts(session, inventaire_id)[:2] == ["extraite", "en_cours"]


def test_gemini_reessaie_a_delai_croissant(monkeypatch, tmp_path):
    """Limite de débit, puis serveur surchargé, puis succès : deux nouvelles
    tentatives, chacune plus espacée que la précédente."""
    attentes = []
    monkeypatch.setattr("src.extract.gemini_extract.time.sleep", attentes.append)
    photo = tmp_path / "e.jpg"
    photo.write_bytes(b"\xff\xd8")

    reponses = [
        errors.ClientError(429, {"error": {"message": "quota"}}, None),
        errors.ServerError(503, {"error": {"message": "surchargé"}}, None),
        SimpleNamespace(text='{"appellation": "Pommard"}', candidates=[], prompt_feedback=None),
    ]

    class Client:
        def __init__(self):
            self.models = self
            self.appels = 0

        def generate_content(self, **_):
            self.appels += 1
            reponse = reponses.pop(0)
            if isinstance(reponse, Exception):
                raise reponse
            return reponse

    client = Client()
    sortie = GeminiExtractor(client=client, pause_s=1).extraire_brut(photo)

    assert client.appels == 3
    assert sortie.erreur is None
    reprises = [attente for attente in attentes if attente > 1]  # hors pauses de quota
    assert reprises == sorted(reprises) and len(set(reprises)) == len(reprises) == 2


@pytest.mark.parametrize(
    "panne",
    [httpx.ReadTimeout("délai dépassé"), httpx.ConnectError("connexion coupée"),
     errors.ClientError(408, {"error": {"message": "délai"}}, None)],
    ids=["delai-lecture", "connexion", "408"],
)
def test_gemini_delai_depasse_et_coupure_sont_passagers(panne, tmp_path):
    """Ils étaient hors de la politique d'erreur : le SDK ne les enveloppe pas.
    Désormais réessayés, puis rendus comme une erreur sur la bouteille, sans
    lever — l'inventaire continue."""
    photo = tmp_path / "e.jpg"
    photo.write_bytes(b"\xff\xd8")

    class Client:
        def __init__(self):
            self.models = self
            self.appels = 0

        def generate_content(self, **_):
            self.appels += 1
            raise panne

    client = Client()
    sortie = GeminiExtractor(client=client, pause_s=0, tentatives_max=3).extraire_brut(photo)
    assert client.appels == 3
    assert sortie.brut is None and type(panne).__name__ in sortie.erreur


def test_anthropic_reessaie_les_pannes_passageres():
    """Le SDK réessaie lui-même, à délai croissant : nombre de tentatives explicite."""
    assert VisionExtractor().client.max_retries == 3


# --- idempotence et trace -----------------------------------------------------------------


def test_extraire_bouteille_est_idempotente(session, inventaire_id, stockage):
    bouteille = bouteilles(session, inventaire_id)[0]
    extracteur = ExtracteurScenario()
    premiere = extraire_bouteille(session, bouteille.id, extracteur, stockage)
    seconde = extraire_bouteille(session, bouteille.id, extracteur, stockage)
    assert seconde.id == premiere.id
    assert extracteur.appels == 1
    assert nb_extractions(session, bouteille) == 1


def test_une_relance_forcee_ajoute_une_extraction_la_derniere_reussie_fait_foi(session, inventaire_id, stockage):
    bouteille = bouteilles(session, inventaire_id)[0]
    extracteur = ExtracteurScenario()
    premiere = extraire_bouteille(session, bouteille.id, extracteur, stockage)
    seconde = extraire_bouteille(session, bouteille.id, extracteur, stockage, forcer=True)

    assert nb_extractions(session, bouteille) == 2
    assert derniere_extraction_reussie(bouteille).id == seconde.id
    assert session.get(Extraction, premiere.id).sortie_brute["appellation"] == "Appellation 1"


def test_une_relance_en_echec_ne_detrone_pas_la_derniere_reussie(session, inventaire_id, stockage):
    bouteille = bouteilles(session, inventaire_id)[0]
    reussie = extraire_bouteille(session, bouteille.id, ExtracteurScenario(), stockage)
    extraire_bouteille(session, bouteille.id, ExtracteurScenario({1: "passagere"}), stockage, forcer=True)
    assert derniere_extraction_reussie(bouteille).id == reussie.id


def test_chaque_extraction_trace_modele_prompt_tokens_et_duree(session, inventaire_id, stockage):
    extraction = extraire_bouteille(session, bouteilles(session, inventaire_id)[0].id, ExtracteurScenario(), stockage)
    assert (extraction.modele, extraction.version_prompt) == ("scenario", "v-scenario")
    assert (extraction.tokens_entree, extraction.tokens_sortie) == (1000, 200)
    assert extraction.duree_ms >= 0
    assert extraction.cree_le is not None


def test_le_modele_recoit_les_photos_du_stockage(session, inventaire_id, stockage, dossier_photos):
    """Les originaux peuvent disparaître : on lit les copies gérées par l'outil."""
    shutil.rmtree(dossier_photos)
    extracteur = ExtracteurScenario()
    extraire_bouteille(session, bouteilles(session, inventaire_id)[0].id, extracteur, stockage)
    etiquette, contre = extracteur.photos_recues[0]
    assert etiquette.parent == stockage and etiquette.exists() and contre.exists()


def test_le_dry_run_ne_consomme_aucun_token(session, inventaire_id, stockage):
    """Fixtures : aucun appel réel, tokens « non mesurés » (None), jamais inventés."""
    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))
    extraire_inventaire(session, inventaire_id, FixtureExtractor(charges), stockage)
    extractions = session.scalars(select(Extraction)).all()
    assert len(extractions) == 6
    assert all(e.tokens_entree is None and e.tokens_sortie is None for e in extractions)
    assert {e.modele for e in extractions} == {"fixtures"}


# --- tokens et version du prompt (decisions.md 0076) -----------------------------------------


def test_tokens_anthropic():
    reponse = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input={"appellation": "Pommard"})],
        usage=SimpleNamespace(input_tokens=1200, output_tokens=340),
        stop_reason="tool_use",
    )
    sortie = sortie_anthropic(reponse, "claude", "v1")
    assert (sortie.tokens_entree, sortie.tokens_sortie) == (1200, 340)
    assert sortie.brut == {"appellation": "Pommard"}


def test_tokens_gemini_la_reflexion_est_comptee_en_sortie():
    """Les tokens de réflexion sont facturés comme la réponse."""
    reponse = SimpleNamespace(
        text='{"appellation": "Pommard"}', candidates=[], prompt_feedback=None,
        usage_metadata=SimpleNamespace(prompt_token_count=1500, candidates_token_count=80, thoughts_token_count=420),
    )
    sortie = sortie_gemini(reponse, "gemini", "v1")
    assert (sortie.tokens_entree, sortie.tokens_sortie) == (1500, 500)
    assert sortie.brut == '{"appellation": "Pommard"}'  # le texte tel quel, pas relu


def test_un_refus_garde_ce_que_le_modele_a_dit():
    reponse = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Je ne peux pas traiter cette image.")],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=12),
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="autre"),
    )
    sortie = sortie_anthropic(reponse)
    assert sortie.brut["texte"] == ["Je ne peux pas traiter cette image."]
    assert "refus du modèle (autre)" in sortie.erreur


def test_meme_maison_meme_version_de_prompt_pour_tous_les_extracteurs():
    config = charger_config(CONFIG_TEST)
    versions = {
        FixtureExtractor([], config).version_prompt,
        VisionExtractor(client=object(), config=config).version_prompt,
        GeminiExtractor(client=object(), pause_s=0, config=config).version_prompt,
    }
    assert len(versions) == 1


def test_la_version_du_prompt_change_avec_la_config():
    config = charger_config(CONFIG_TEST)
    assert version_prompt(schema_extraction(config)) != version_prompt(schema_extraction(None))


def test_les_statuts_de_la_base_sont_ceux_du_service():
    from src.donnees.modeles import STATUTS_BOUTEILLE

    assert set(service.STATUTS_A_EXTRAIRE) <= set(STATUTS_BOUTEILLE)
    assert FicheBouteille.__tablename__ == "bouteille"
