"""Le backend gratuit, vérifié hors ligne.

Le palier gratuit de Gemini tourne autour de 15 requêtes/minute : le 429 y est
le régime NORMAL, pas un incident. C'est le comportement le plus testé ici.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from google.genai import errors

from src.extract import consignes
from src.extract.base import Extractor
from src.extract.gemini_extract import (
    MODELE_DEFAUT,
    VARIABLE_MODELE,
    GeminiExtractor,
    bouteille_depuis_reponse,
    construire_contenu,
)
from src.extract.schema import NON_LISIBLE, Couleur, Effervescence, Format


@pytest.fixture
def photos(tmp_path):
    etiquette = tmp_path / "01_etiquette.jpg"
    contre = tmp_path / "02_contre.png"
    capsule = tmp_path / "03_capsule.jpg"
    for chemin in (etiquette, contre, capsule):
        chemin.write_bytes(b"\xff\xd8\xff\xe0 faux binaire")
    return etiquette, contre, capsule


class ClientFactice:
    """Rejoue des réponses ou lève des erreurs, sans réseau."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels = 0
        self.dernier_appel: dict = {}
        self.models = self

    def generate_content(self, **arguments):
        self.appels += 1
        self.dernier_appel = arguments
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse


def _extracteur(*reponses, **options):
    """Extracteur sans pause : les tests ne doivent pas dormir."""
    options.setdefault("pause_s", 0)
    return GeminiExtractor(client=ClientFactice(*reponses), **options)


def _reponse(charge: dict):
    return SimpleNamespace(text=json.dumps(charge), candidates=[], prompt_feedback=None)


# --- consignes partagées (decisions.md 0049) ----------------------------


def test_les_deux_backends_partagent_les_memes_consignes():
    """Si les prompts divergeaient, les scores ne seraient plus comparables."""
    from src.extract import vision_extract

    assert vision_extract.SYSTEM_PROMPT is consignes.SYSTEM_PROMPT
    assert vision_extract.LIBELLE_ETIQUETTE is consignes.LIBELLE_ETIQUETTE


def test_les_deux_backends_construisent_les_memes_libelles(photos):
    from src.extract import vision_extract

    etiquette, contre, capsule = photos

    textes_gemini = [b for b in construire_contenu(etiquette, contre, [capsule]) if isinstance(b, str)]
    blocs = vision_extract.construire_contenu(etiquette, contre, [capsule])
    textes_anthropic = [b["text"] for b in blocs if b["type"] == "text"]

    assert textes_gemini == textes_anthropic


def test_le_schema_vient_de_schema_py():
    """Source unique : pas de schéma recopié pour Gemini."""
    from src.extract.schema import tool_schema

    extracteur = _extracteur()
    assert extracteur._config.response_json_schema == tool_schema()["input_schema"]
    assert extracteur._config.response_mime_type == "application/json"


# --- construction du message --------------------------------------------


def test_toutes_les_vues_dans_le_meme_appel(photos):
    etiquette, contre, capsule = photos
    contenu = construire_contenu(etiquette, contre, [capsule])
    images = [b for b in contenu if not isinstance(b, str)]
    assert len(images) == 3


def test_photo_absente_leve_une_erreur(tmp_path):
    with pytest.raises(FileNotFoundError, match="Photo introuvable"):
        construire_contenu(tmp_path / "fantome.jpg")


def test_format_non_pris_en_charge(tmp_path):
    fichier = tmp_path / "etiquette.tiff"
    fichier.write_bytes(b"x")
    with pytest.raises(ValueError, match="Format d'image non pris en charge"):
        construire_contenu(fichier)


# --- lecture de la réponse ----------------------------------------------


def test_lecture_d_une_reponse_json():
    bouteille = bouteille_depuis_reponse(
        _reponse(
            {
                "appellation": "Pommard",
                "couleur": "rouge",
                "effervescence": "tranquille",
                "format": "magnum",
                "millesime": "non_lisible",
                "contenance_cl": 150,
            }
        )
    )
    assert bouteille.appellation == "Pommard"
    assert bouteille.couleur is Couleur.ROUGE
    assert bouteille.effervescence is Effervescence.TRANQUILLE
    assert bouteille.format is Format.MAGNUM
    assert bouteille.millesime == NON_LISIBLE
    assert bouteille.contenance_cl == 150


def test_reponse_vide_s_abstient():
    reponse = SimpleNamespace(text=None, candidates=[], prompt_feedback=None)
    bouteille = bouteille_depuis_reponse(reponse)
    assert bouteille.appellation == NON_LISIBLE
    assert bouteille.champs_a_verifier == ["tous"]
    assert "réponse vide" in bouteille.notes


def test_requete_bloquee_est_tracee():
    reponse = SimpleNamespace(
        text=None, candidates=[], prompt_feedback=SimpleNamespace(block_reason="SAFETY")
    )
    assert "bloquée (SAFETY)" in bouteille_depuis_reponse(reponse).notes


def test_generation_interrompue_est_tracee():
    reponse = SimpleNamespace(
        text=None,
        candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
        prompt_feedback=None,
    )
    assert "interrompue (MAX_TOKENS)" in bouteille_depuis_reponse(reponse).notes


def test_json_invalide_ne_casse_pas_la_campagne():
    reponse = SimpleNamespace(text="{ pas du json", candidates=[], prompt_feedback=None)
    bouteille = bouteille_depuis_reponse(reponse)
    assert bouteille.champs_a_verifier == ["tous"]
    assert "non lisible en JSON" in bouteille.notes


# --- quota du palier gratuit --------------------------------------------


def test_un_429_est_reessaye_puis_reussit(photos):
    """15 req/min : le 429 est le régime nominal, pas une panne."""
    etiquette, _, _ = photos
    quota = errors.ClientError(429, {"error": {"message": "quota"}}, None)
    extracteur = _extracteur(quota, quota, _reponse({"appellation": "Pommard"}))

    bouteille = extracteur.extract(etiquette)

    assert bouteille.appellation == "Pommard"
    assert extracteur.client.appels == 3


def test_un_429_persistant_finit_en_abstention(photos):
    etiquette, _, _ = photos
    quota = errors.ClientError(429, {"error": {"message": "quota"}}, None)
    extracteur = _extracteur(quota, quota, quota, quota, tentatives_max=4)

    bouteille = extracteur.extract(etiquette)

    assert bouteille.champs_a_verifier == ["tous"]
    assert "ClientError" in bouteille.notes
    assert extracteur.client.appels == 4


def test_une_panne_serveur_est_reessayee(photos):
    etiquette, _, _ = photos
    panne = errors.ServerError(503, {"error": {"message": "indisponible"}}, None)
    extracteur = _extracteur(panne, _reponse({"appellation": "Volnay"}))

    assert extracteur.extract(etiquette).appellation == "Volnay"
    assert extracteur.client.appels == 2


def test_une_cle_invalide_arrete_tout_sans_reessayer(photos):
    """Répéter une clé invalide 200 fois ne produirait que 200 lignes vides."""
    etiquette, _, _ = photos
    refus = errors.ClientError(401, {"error": {"message": "clé invalide"}}, None)
    extracteur = _extracteur(refus, refus, refus)

    with pytest.raises(errors.ClientError):
        extracteur.extract(etiquette)

    assert extracteur.client.appels == 1


def test_un_modele_inexistant_arrete_tout(photos):
    etiquette, _, _ = photos
    absent = errors.ClientError(404, {"error": {"message": "model not found"}}, None)
    extracteur = _extracteur(absent)

    with pytest.raises(errors.ClientError):
        extracteur.extract(etiquette)


# --- configuration -------------------------------------------------------


def test_modele_par_defaut_et_surcharge_par_env(monkeypatch):
    monkeypatch.delenv(VARIABLE_MODELE, raising=False)
    assert _extracteur().modele == MODELE_DEFAUT
    assert MODELE_DEFAUT.startswith("gemini-"), "le palier gratuit est Flash uniquement"

    monkeypatch.setenv(VARIABLE_MODELE, "gemini-3.5-flash-lite")
    assert _extracteur().modele == "gemini-3.5-flash-lite"


def test_gemini_extractor_respecte_le_protocol():
    assert isinstance(_extracteur(), Extractor)


def test_le_modele_choisi_part_bien_dans_l_appel(photos):
    etiquette, _, _ = photos
    extracteur = _extracteur(_reponse({"appellation": "Pommard"}), modele="gemini-3.6-flash")
    extracteur.extract(etiquette)
    assert extracteur.client.dernier_appel["model"] == "gemini-3.6-flash"


# --- ce qui part réellement au modèle (guide, étape 4.2) --------------------------


def test_colonnes_expert_et_systeme_jamais_envoyees(photos):
    """Vérifié sur la requête ENVOYÉE, pas seulement sur le générateur de schéma."""
    from src.config.maison import charger_config
    from tests.conftest import RACINE

    config = charger_config(RACINE / "config" / "maisons" / "maison_test.json")
    extracteur = _extracteur(_reponse({"appellation": "Pommard"}), config=config)
    extracteur.extract(photos[0])

    envoye = extracteur.client.dernier_appel["config"].response_json_schema
    for colonne in config.colonnes:
        if not colonne.envoyee_au_modele:
            assert colonne.cle not in envoye["properties"], colonne.cle
    for colonne in config.colonnes_modele:
        assert colonne.cle in envoye["properties"], colonne.cle


def test_les_deux_backends_envoient_le_meme_schema_pour_une_maison():
    """Même maison, même schéma : sinon leurs scores ne seraient pas comparables."""
    from src.config.maison import charger_config
    from src.extract.vision_extract import VisionExtractor
    from tests.conftest import RACINE

    config = charger_config(RACINE / "config" / "maisons" / "maison_test.json")
    anthropic_ = VisionExtractor(client=object(), config=config)._outil["input_schema"]
    gemini = _extracteur(config=config)._config.response_json_schema
    assert anthropic_ == gemini
