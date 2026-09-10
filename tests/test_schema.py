"""Le contrat de données doit s'abstenir par défaut et ne jamais deviner."""

from __future__ import annotations

from src.extract.schema import (
    CHAMPS,
    CHAMPS_COMPARABLES,
    NON_DETERMINABLE,
    NON_LISIBLE,
    Bouteille,
    Couleur,
    CouleurSource,
    Format,
    est_abstention,
    from_tool_input,
    tool_schema,
)


def test_bouteille_vide_n_affirme_rien():
    """Une `Bouteille()` par défaut s'abstient sur TOUS les champs comparables."""
    bouteille = Bouteille()
    for champ in CHAMPS_COMPARABLES:
        assert est_abstention(getattr(bouteille, champ)), champ


def test_format_par_defaut_est_non_determinable():
    """decisions.md 0003 : le format n'est jamais deviné."""
    assert Bouteille().format is Format.NON_DETERMINABLE


def test_est_abstention_reconnait_les_trois_conventions():
    assert est_abstention(None)
    assert est_abstention(NON_LISIBLE)
    assert est_abstention(NON_DETERMINABLE)
    assert est_abstention("")
    assert est_abstention("  ")
    assert est_abstention(Couleur.NON_DETERMINABLE)
    assert est_abstention(CouleurSource.NON_LISIBLE)

    assert not est_abstention("2018")
    assert not est_abstention(Couleur.ROUGE)
    assert not est_abstention(0)
    assert not est_abstention(75)


def test_enums_fermes_offrent_une_sortie_d_abstention():
    assert Couleur.NON_DETERMINABLE.value == NON_DETERMINABLE
    assert Format.NON_DETERMINABLE.value == NON_DETERMINABLE
    assert CouleurSource.NON_LISIBLE.value == NON_LISIBLE


def test_from_tool_input_retombe_sur_l_abstention():
    """Un modèle qui répond de travers doit s'abstenir, pas inventer ni planter."""
    bouteille = from_tool_input(
        {
            "appellation": "Pommard",
            "couleur": "grenat",  # hors enum
            "millesime": "   ",  # blanc
            "contenance_cl": "pas un nombre",
            # tous les autres champs sont absents
        }
    )
    assert bouteille.appellation == "Pommard"
    assert bouteille.couleur is Couleur.NON_DETERMINABLE
    assert bouteille.millesime == NON_LISIBLE
    assert bouteille.contenance_cl is None
    assert bouteille.domaine == NON_LISIBLE
    assert bouteille.champs_a_verifier == []


def test_from_tool_input_lit_les_valeurs_normales():
    bouteille = from_tool_input(
        {
            "appellation": "Meursault",
            "domaine": "Domaine Coche-Dury",
            "couleur": "blanc",
            "couleur_source": "observee",
            "millesime": "2017",
            "format": "magnum",
            "contenance_cl": 150,
            "degre": 13.5,
            "champs_a_verifier": ["degre"],
        }
    )
    assert bouteille.couleur is Couleur.BLANC
    assert bouteille.couleur_source is CouleurSource.OBSERVEE
    assert bouteille.format is Format.MAGNUM
    assert bouteille.contenance_cl == 150
    assert bouteille.degre == 13.5
    assert bouteille.champs_a_verifier == ["degre"]


def test_tool_schema_exige_tous_les_champs():
    """Tous les champs sont requis : le modèle doit se prononcer, quitte à s'abstenir."""
    schema = tool_schema()
    proprietes = schema["input_schema"]["properties"]
    assert set(proprietes) == set(CHAMPS)
    assert set(schema["input_schema"]["required"]) == set(CHAMPS)


def test_tool_schema_ferme_les_enums():
    proprietes = tool_schema()["input_schema"]["properties"]
    assert proprietes["couleur"]["enum"] == [c.value for c in Couleur]
    assert proprietes["format"]["enum"] == [f.value for f in Format]
    assert proprietes["couleur_source"]["enum"] == [c.value for c in CouleurSource]


def test_tool_schema_autorise_null_sur_les_numeriques():
    """L'abstention numérique doit être exprimable dans le schéma."""
    proprietes = tool_schema()["input_schema"]["properties"]
    assert "null" in proprietes["contenance_cl"]["type"]
    assert "null" in proprietes["degre"]["type"]


def test_tool_schema_ne_contient_aucun_exemple_de_vin():
    """decisions.md 0006 : zero-shot, aucun exemple ne doit fuiter dans le prompt."""
    texte = str(tool_schema()).casefold()
    for exemple_interdit in ("bordeaux", "bourgogne", "chateau ", "château ", "1985", "2015"):
        assert exemple_interdit not in texte, exemple_interdit


def test_as_dict_reduit_les_enums_a_du_texte():
    donnees = Bouteille(couleur=Couleur.ROUGE, format=Format.MAGNUM).as_dict()
    assert donnees["couleur"] == "rouge"
    assert donnees["format"] == "magnum"
    assert set(donnees) == set(CHAMPS)
