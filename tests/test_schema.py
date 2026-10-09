"""Le contrat de données doit s'abstenir par défaut et ne jamais deviner."""

from __future__ import annotations

from src.extract.schema import (
    CHAMPS,
    CHAMPS_COMPARABLES,
    CHAMPS_HORS_MODELE,
    CHAMPS_MODELE,
    CHAMPS_TECHNIQUES,
    NON_DETERMINABLE,
    NON_LISIBLE,
    Bouteille,
    Couleur,
    CouleurSource,
    Effervescence,
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
    assert Effervescence.NON_DETERMINABLE.value == NON_DETERMINABLE
    assert CouleurSource.NON_LISIBLE.value == NON_LISIBLE


def test_effervescence_et_couleur_sont_deux_dimensions():
    """decisions.md 0041 : un effervescent peut être blanc, rosé ou rouge."""
    assert "effervescent" not in [c.value for c in Couleur]
    assert "rose" not in [e.value for e in Effervescence]

    # Le cas qui justifie la séparation : les deux tiennent ensemble.
    petillant_rose = Bouteille(
        couleur=Couleur.ROSE, effervescence=Effervescence.EFFERVESCENT
    )
    assert petillant_rose.couleur is Couleur.ROSE
    assert petillant_rose.effervescence is Effervescence.EFFERVESCENT


def test_effervescence_par_defaut_est_non_determinable():
    assert Bouteille().effervescence is Effervescence.NON_DETERMINABLE


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


def test_une_contenance_decimale_n_est_plus_perdue():
    """`int("75.5")` levait : le modèle avait lu quelque chose, on l'ignorait."""
    assert from_tool_input({"contenance_cl": "75.5"}).contenance_cl == 76
    assert from_tool_input({"contenance_cl": 75.0}).contenance_cl == 75
    assert from_tool_input({"contenance_cl": "75"}).contenance_cl == 75
    assert from_tool_input({"contenance_cl": "trois quarts"}).contenance_cl is None


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
    """Tous les champs du modèle sont requis : il doit se prononcer, quitte à s'abstenir.

    Adapté au contrat pilote : l'identifiant, la quantité et les valeurs propres
    à la maison existent sur `Bouteille` mais ne sont JAMAIS demandés au modèle.
    Et le modèle répond aussi à des questions techniques (la paire de photos
    est-elle cohérente ?) qui ne sont pas des champs de `Bouteille` : elles sont
    exigées elles aussi.
    """
    schema = tool_schema()
    proprietes = schema["input_schema"]["properties"]
    attendus = set(CHAMPS_MODELE) | set(CHAMPS_TECHNIQUES)
    assert set(proprietes) == attendus
    assert set(schema["input_schema"]["required"]) == attendus
    for champ in CHAMPS_HORS_MODELE:
        assert champ not in proprietes, champ


# --- contrat pilote : id, quantité, valeurs de maison (decisions.md 0054) ---


def test_id_quantite_et_valeurs_maison_par_defaut():
    bouteille = Bouteille()
    assert bouteille.id == ""
    assert bouteille.quantite == 1
    assert bouteille.valeurs_maison == {}


def test_le_modele_ne_peut_pas_poser_id_quantite_ni_estimation():
    """Même s'il les renvoie, le modèle ne décide jamais de ce que posent
    l'outil ou l'expert (decisions.md 0059)."""
    bouteille = from_tool_input(
        {"appellation": "Pommard", "id": "X", "quantite": 99, "estimation": "800-1000"}
    )
    assert bouteille.id == ""
    assert bouteille.quantite == 1
    assert "estimation" not in bouteille.as_dict()
    assert bouteille.valeurs_maison == {}


# « Le journal se relit sans rien perdre » et « quantité invalide au journal » :
# le journal a disparu avec la base (decisions.md 0079). Leurs successeurs :
# tests/test_relecture.py (un code de la maison n'est jamais perdu à la relecture
# depuis la base) et la quantité validée par `corriger` (test_relecture.py) et
# par la base elle-même (test_base.py).


def test_tool_schema_ferme_les_enums():
    proprietes = tool_schema()["input_schema"]["properties"]
    assert proprietes["couleur"]["enum"] == [c.value for c in Couleur]
    assert proprietes["format"]["enum"] == [f.value for f in Format]
    assert proprietes["couleur_source"]["enum"] == [c.value for c in CouleurSource]
    assert proprietes["effervescence"]["enum"] == [e.value for e in Effervescence]


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
