"""Tout ce qui se vérifie de l'extracteur VLM SANS appeler l'API.

L'appel réseau lui-même n'est pas mocké dans le chemin réel : `VisionExtractor`
parle à l'API pour de bon. Ces tests couvrent ce qui l'entoure — construction
du message, discipline du prompt, lecture de la réponse.
"""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from src.extract.base import Extractor
from src.extract.schema import Couleur, Format, NON_LISIBLE
from src.extract.vision_extract import (
    MODELE_DEFAUT,
    SYSTEM_PROMPT,
    VARIABLE_MODELE,
    VisionExtractor,
    bouteille_depuis_reponse,
    construire_contenu,
)


@pytest.fixture
def photos(tmp_path):
    etiquette = tmp_path / "01_etiquette.jpg"
    contre = tmp_path / "02_contre.png"
    capsule = tmp_path / "03_capsule.jpg"
    for chemin in (etiquette, contre, capsule):
        chemin.write_bytes(b"\xff\xd8\xff\xe0 faux binaire")
    return etiquette, contre, capsule


# --- le prompt ----------------------------------------------------------


def test_prompt_interdit_de_deviner():
    assert "tu ne devines jamais" in SYSTEM_PROMPT.casefold()
    assert "non_lisible" in SYSTEM_PROMPT
    assert "non_determinable" in SYSTEM_PROMPT


def test_prompt_interdit_toute_estimation():
    """decisions.md 0005 : aucun prix, y compris dans les notes."""
    assert "aucune estimation" in SYSTEM_PROMPT.casefold()
    assert "y compris dans les notes" in SYSTEM_PROMPT.casefold()


def test_prompt_ne_contient_aucun_exemple_resolu():
    """decisions.md 0006 : zero-shot. Aucun nom de vin, aucun millésime concret."""
    prompt = SYSTEM_PROMPT.casefold()
    for exemple_interdit in ("bordeaux", "bourgogne", "château ", "domaine ", "exemple :"):
        assert exemple_interdit not in prompt, exemple_interdit
    assert not any(str(annee) in SYSTEM_PROMPT for annee in range(1900, 2027))


# --- construction du message --------------------------------------------


def test_toutes_les_vues_dans_le_meme_message(photos):
    etiquette, contre, capsule = photos
    contenu = construire_contenu(etiquette, contre, [capsule])

    images = [bloc for bloc in contenu if bloc["type"] == "image"]
    assert len(images) == 3
    assert images[0]["source"]["media_type"] == "image/jpeg"
    assert images[1]["source"]["media_type"] == "image/png"


def test_chaque_image_est_precedee_de_son_role(photos):
    etiquette, contre, _ = photos
    contenu = construire_contenu(etiquette, contre)
    roles = [bloc["text"] for bloc in contenu if bloc["type"] == "text"]
    assert roles[0].startswith("Photo — étiquette")
    assert roles[1].startswith("Photo — contre-étiquette")


def test_etiquette_seule_est_acceptee(photos):
    etiquette, _, _ = photos
    contenu = construire_contenu(etiquette)
    assert len([b for b in contenu if b["type"] == "image"]) == 1


def test_photo_absente_leve_une_erreur(tmp_path):
    with pytest.raises(FileNotFoundError, match="Photo introuvable"):
        construire_contenu(tmp_path / "fantome.jpg")


def test_format_d_image_non_pris_en_charge(tmp_path):
    fichier = tmp_path / "etiquette.tiff"
    fichier.write_bytes(b"x")
    with pytest.raises(ValueError, match="Format d'image non pris en charge"):
        construire_contenu(fichier)


# --- lecture de la réponse ----------------------------------------------


def _reponse(blocs, stop_reason="tool_use", stop_details=None):
    return SimpleNamespace(
        content=blocs, stop_reason=stop_reason, stop_details=stop_details
    )


def test_lecture_d_un_appel_d_outil():
    bloc = SimpleNamespace(
        type="tool_use",
        input={
            "appellation": "Pommard",
            "couleur": "rouge",
            "format": "magnum",
            "millesime": "non_lisible",
        },
    )
    bouteille = bouteille_depuis_reponse(_reponse([bloc]))
    assert bouteille.appellation == "Pommard"
    assert bouteille.couleur is Couleur.ROUGE
    assert bouteille.format is Format.MAGNUM
    assert bouteille.millesime == NON_LISIBLE


def test_reponse_sans_appel_d_outil_s_abstient():
    """Une campagne ne doit pas casser sur une réponse vide."""
    bloc = SimpleNamespace(type="text", text="Je ne peux pas lire cette photo.")
    bouteille = bouteille_depuis_reponse(_reponse([bloc], stop_reason="end_turn"))

    assert bouteille.appellation == NON_LISIBLE
    assert bouteille.champs_a_verifier == ["tous"]
    assert "aucun appel d'outil" in bouteille.notes


def test_refus_du_modele_est_trace_dans_les_notes():
    reponse = _reponse(
        [], stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")
    )
    bouteille = bouteille_depuis_reponse(reponse)
    assert "refus du modèle (cyber)" in bouteille.notes


# --- politique d'erreur (decisions.md 0045) ------------------------------


class ClientQuiEchoue:
    """Client factice : lève l'erreur demandée au lieu d'appeler l'API."""

    def __init__(self, erreur):
        self.erreur = erreur
        self.messages = self

    def create(self, **_):
        raise self.erreur


def _erreur_api(classe, message, code):
    """Construit une erreur du SDK sans passer par le réseau."""
    reponse = httpx.Response(
        code, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    return classe(message, response=reponse, body=None)


def test_panne_passagere_abstient_et_laisse_la_campagne_continuer(photos):
    """Un 429 sur une bouteille ne doit pas coûter les 199 autres."""
    etiquette, _, _ = photos
    erreur = _erreur_api(anthropic.RateLimitError, "rate limited", 429)
    extracteur = VisionExtractor(client=ClientQuiEchoue(erreur))

    bouteille = extracteur.extract(etiquette)

    assert bouteille.appellation == NON_LISIBLE
    assert bouteille.champs_a_verifier == ["tous"]
    assert "RateLimitError" in bouteille.notes


def test_panne_systematique_arrete_tout(photos):
    """Une clé invalide échouerait sur CHAQUE bouteille : inutile de payer 200 fois."""
    etiquette, _, _ = photos
    erreur = _erreur_api(anthropic.AuthenticationError, "bad key", 401)
    extracteur = VisionExtractor(client=ClientQuiEchoue(erreur))

    with pytest.raises(anthropic.AuthenticationError):
        extracteur.extract(etiquette)


def test_un_400_explique_le_risque_connu(photos):
    """decisions.md 0029 : le 400 le plus probable a sa marche à suivre écrite."""
    etiquette, _, _ = photos
    erreur = _erreur_api(anthropic.BadRequestError, "thinking not supported", 400)
    extracteur = VisionExtractor(client=ClientQuiEchoue(erreur))

    with pytest.raises(RuntimeError) as capture:
        extracteur.extract(etiquette)

    message = str(capture.value)
    assert "decisions.md 0029" in message
    assert "tool_choice" in message
    assert "NE PAS désactiver le thinking" in message


# --- configuration -------------------------------------------------------


def test_modele_par_defaut_et_surcharge_par_env(monkeypatch):
    client_factice = object()

    monkeypatch.delenv(VARIABLE_MODELE, raising=False)
    assert VisionExtractor(client=client_factice).modele == MODELE_DEFAUT

    monkeypatch.setenv(VARIABLE_MODELE, "claude-sonnet-5")
    assert VisionExtractor(client=client_factice).modele == "claude-sonnet-5"

    # Un modèle passé explicitement prime sur l'environnement.
    assert (
        VisionExtractor(client=client_factice, modele="claude-haiku-4-5").modele
        == "claude-haiku-4-5"
    )


def test_vision_extractor_respecte_le_protocol():
    assert isinstance(VisionExtractor(client=object()), Extractor)


def test_l_outil_est_force():
    """La sortie est contrainte par construction, pas par parsing (0001)."""
    extracteur = VisionExtractor(client=object())
    assert extracteur._outil["name"] == "enregistrer_bouteille"
