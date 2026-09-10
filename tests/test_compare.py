"""Le harnais de comparaison — le livrable de la v0.

Les attentes chiffrées ci-dessous sont calculées à la main sur les fixtures ;
si elles changent, c'est que la sémantique des métriques a bougé, ce qui doit
être un acte délibéré.
"""

from __future__ import annotations

import json

import pytest

from src.compare.compare_listings import (
    comparer,
    formater_rapport,
    plier,
)
from src.extract.schema import Bouteille, Couleur, Effervescence, from_tool_input
from src.io.manual_listing import load_manual
from tests.conftest import FIXTURES


def charger_auto() -> list[Bouteille]:
    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))
    return [from_tool_input(charge) for charge in charges]


@pytest.fixture
def rapport():
    return comparer(charger_auto(), load_manual(FIXTURES / "manuel.json"))


def score(rapport, champ):
    return next(s for s in rapport.scores if s.champ == champ)


# --- pliage (decisions.md 0008) -----------------------------------------


def test_pliage_insensible_casse_et_accents():
    assert plier("GEVREY-CHAMBERTIN") == plier("Gevrey-Chambertin")
    assert plier("Domaine William Fèvre") == plier("Domaine William Fevre")
    assert plier("  Vallée   du Rhône ") == plier("vallee du rhone")


def test_pliage_ne_normalise_pas_les_conventions():
    """Le pliage s'arrête aux accents/casse : les écarts de convention restent VISIBLES."""
    assert plier("Domaine du Vieux Télégraphe") != plier("Vieux Télégraphe")
    assert plier("Château Margaux") != plier("Margaux")


def test_couleur_enum_se_plie_comme_du_texte():
    assert plier(Couleur.ROUGE) == plier("Rouge")


# --- métriques par champ ------------------------------------------------


def test_toutes_les_lignes_sont_comparees(rapport):
    assert rapport.n_lignes == 6


def test_ecart_de_casse_ou_accent_ne_compte_pas_comme_erreur(rapport):
    """Ligne 0 en capitales, ligne 2 sans accent, ligne 5 « rosé » : des accords."""
    assert score(rapport, "appellation").exact == 6
    assert score(rapport, "appellation").accuracy == 1.0
    assert score(rapport, "region").accuracy == 1.0
    assert score(rapport, "pays").accuracy == 1.0
    assert score(rapport, "couleur").accuracy == 1.0


def test_abstention_n_est_jamais_comptee_comme_desaccord(rapport):
    """Ligne 1 : millésime non lisible côté modèle, 2015 côté expert."""
    millesime = score(rapport, "millesime")
    assert millesime.abstention == 1
    assert millesime.desaccord == 1  # ligne 3 seulement (2004 vs 2001)
    assert millesime.comparables == 4
    assert millesime.exact == 3
    assert millesime.accuracy == 0.75
    assert millesime.taux_abstention == pytest.approx(0.2)


def test_format_abstient_massivement_sans_bouteille_entiere(rapport):
    """CLAUDE.md : format non_determinable presque partout est normal, pas un bug."""
    format_ = score(rapport, "format")
    assert format_.manuel_vide == 1
    assert format_.abstention == 4
    assert format_.desaccord == 0
    assert format_.exact == 1  # le magnum, lisible
    assert format_.accuracy == 1.0
    assert format_.taux_abstention == 0.8


def test_manuel_vide_n_est_pas_evaluable(rapport):
    """L'expert n'a renseigné l'importateur que sur une ligne."""
    importateur = score(rapport, "importateur")
    assert importateur.manuel_vide == 5
    assert importateur.evaluables == 1
    assert importateur.exact == 1
    assert importateur.accuracy == 1.0


def test_ecart_de_convention_apparait_en_desaccord(rapport):
    """« Domaine du Vieux Télégraphe » vs « Vieux Télégraphe » : à voir, pas à masquer."""
    domaine = score(rapport, "domaine")
    assert domaine.desaccord == 1
    assert domaine.exact == 5
    assert domaine.accuracy == pytest.approx(5 / 6)


def test_effervescence_est_independante_de_la_couleur(rapport):
    """Ligne 5 : un effervescent rosé garde SES DEUX dimensions (0031).

    C'est tout l'intérêt du champ séparé — dans un enum `couleur` fusionné,
    cette bouteille aurait dû choisir entre « rose » et « effervescent ».
    """
    effervescence = score(rapport, "effervescence")
    assert effervescence.exact == 6
    assert effervescence.accuracy == 1.0
    assert effervescence.abstention == 0

    auto = charger_auto()[5]
    assert auto.couleur is Couleur.ROSE
    assert auto.effervescence is Effervescence.EFFERVESCENT


def test_abstention_numerique_est_une_abstention(rapport):
    """contenance_cl / degre à None côté modèle."""
    assert score(rapport, "contenance_cl").abstention == 1
    assert score(rapport, "contenance_cl").accuracy == 1.0
    assert score(rapport, "degre").abstention == 1
    assert score(rapport, "degre").accuracy == 1.0


# --- file d'inspection --------------------------------------------------


def test_les_desaccords_sont_listes_en_detail(rapport):
    assert len(rapport.desaccords) == 3
    reperes = {(d.ligne, d.champ) for d in rapport.desaccords}
    assert reperes == {(4, "domaine"), (2, "cuvee"), (3, "millesime")}

    millesime = next(d for d in rapport.desaccords if d.champ == "millesime")
    assert millesime.auto == "2004"
    assert millesime.manuel == "2001"


def test_rapport_formate_montre_scores_et_desaccords(rapport):
    texte = formater_rapport(rapport)
    assert "accuracy" in texte
    assert "millesime" in texte
    assert "Désaccords à inspecter (3)" in texte
    assert "2004" in texte and "2001" in texte


# --- garde-fous ---------------------------------------------------------


def test_alignement_rompu_leve_une_erreur():
    """Mieux vaut s'arrêter que produire un score faux et crédible (0010)."""
    with pytest.raises(ValueError, match="Alignement ligne à ligne rompu"):
        comparer([Bouteille()], [])


def test_aucun_desaccord_sur_deux_listings_identiques():
    auto = charger_auto()
    manuel = [
        {champ: valeur for champ, valeur in b.as_dict().items()} for b in auto
    ]
    rapport = comparer(auto, manuel)
    assert rapport.desaccords == []
    assert "Aucun désaccord." in formater_rapport(rapport)
