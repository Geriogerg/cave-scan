"""inventaire.py : relire, corriger, valider, exporter en ligne de commande.

Le script n'a pas de logique propre (decisions.md 0080) : ces tests vérifient
qu'il appelle les bons services, affiche ce qu'il faut, et que ses refus
sortent en code 2 sans rien écrire.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

import inventaire
from src.config.maison import charger_config
from src.donnees.base import session_de_base, url_de_base
from src.extract.fixture_extract import FixtureExtractor, generer_photos_fictives
from src.services.extraction import extraire_inventaire
from src.services.inventaires import creer_inventaire
from tests.conftest import CONFIG_TEST, FIXTURES
from tests.test_run_v0 import colonne_excel


@pytest.fixture
def base(tmp_path, dossier_photos, nom_maison):
    """Un inventaire n°1 de 6 bouteilles extraites sur les fixtures."""
    chemin = tmp_path / "cave.db"
    stockage = tmp_path / "stockage"
    with session_de_base(chemin) as session:
        cree = creer_inventaire(session, nom_maison, CONFIG_TEST, dossier_photos, "Cave de test", stockage)
        extracteur = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json", charger_config(CONFIG_TEST))
        extraire_inventaire(session, cree.inventaire_id, extracteur, stockage)
    return chemin


def lancer(capsys, base, *arguments):
    code = inventaire.main([*(str(argument) for argument in arguments), "--base", str(base)])
    sortie = capsys.readouterr()
    return code, sortie.out, sortie.err


def lignes(base, sql):
    moteur = create_engine(url_de_base(base))
    with moteur.connect() as connexion:
        resultat = [tuple(ligne) for ligne in connexion.exec_driver_sql(sql)]
    moteur.dispose()
    return resultat


def test_lister(base, capsys):
    code, sortie, _ = lancer(capsys, base, "lister")
    assert code == 0
    assert "Maison Test — Cave de test" in sortie


def test_base_avant_ou_apres_la_commande(base, capsys):
    assert inventaire.main(["--base", str(base), "lister"]) == 0
    assert "Cave de test" in capsys.readouterr().out
    assert inventaire.main(["lister", "--base", str(base)]) == 0
    assert "Cave de test" in capsys.readouterr().out


def test_bouteilles_montre_les_valeurs_courantes(base, capsys):
    lancer(capsys, base, "corriger", 1, 1, "domaine", "Rossignol-Trapet", "--auteur", "expert")
    code, sortie, _ = lancer(capsys, base, "bouteilles", 1)
    premiere = next(ligne for ligne in sortie.splitlines() if ligne.startswith("   1  B-"))
    assert code == 0
    assert "Rossignol-Trapet · Gevrey-Chambertin 1er Cru · 2018" in premiere
    assert "Domaine Rossignol-Trapet" not in premiere


def test_corriger_trace_sans_toucher_l_extraction_et_se_voit_a_l_export(base, capsys, tmp_path):
    extractions = lignes(base, "SELECT * FROM extraction ORDER BY id")

    code, sortie, _ = lancer(capsys, base, "corriger", 1, 1, "millesime", "2001", "--auteur", "expert")

    assert code == 0
    assert "« 2018 » -> « 2001 », par expert" in sortie
    assert lignes(base, "SELECT * FROM extraction ORDER BY id") == extractions
    assert lancer(capsys, base, "exporter", 1, "--sortie", tmp_path / "l.xlsx")[0] == 0
    assert str(colonne_excel(tmp_path / "l.xlsx", "millesime")[0]) == "2001"


def test_corriger_refuse_un_champ_inconnu_ou_une_valeur_hors_liste_sans_rien_ecrire(base, capsys):
    code, _, erreur = lancer(capsys, base, "corriger", 1, 1, "cepage", "Pinot noir", "--auteur", "expert")
    assert code == 2
    assert "Champ inconnu : « cepage »" in erreur

    code, _, erreur = lancer(capsys, base, "corriger", 1, 1, "couleur", "violet", "--auteur", "expert")
    assert code == 2
    assert "pas une valeur de la liste « Couleur »" in erreur
    assert lignes(base, "SELECT count(*) FROM correction") == [(0,)]


def test_l_auteur_est_obligatoire(base):
    with pytest.raises(SystemExit):
        inventaire.main(["corriger", "1", "1", "millesime", "2001", "--base", str(base)])


def test_valider_puis_corriger_rouvre_la_bouteille(base, capsys):
    code, sortie, _ = lancer(capsys, base, "valider", 1, 1, "--auteur", "expert")
    assert code == 0
    assert "1/6 bouteille(s) validée(s)" in sortie

    _, sortie, _ = lancer(capsys, base, "corriger", 1, 1, "millesime", "2001", "--auteur", "expert")
    assert "Bouteille extraite, inventaire ouvert" in sortie


def test_valider_refuse_une_bouteille_pas_encore_extraite(base, capsys, tmp_path, nom_maison):
    with session_de_base(base) as session:
        creer_inventaire(
            session, nom_maison, CONFIG_TEST, generer_photos_fictives(tmp_path / "autres", 1),
            "Pas extrait", tmp_path / "stockage",
        )
    code, _, erreur = lancer(capsys, base, "valider", 2, 1, "--auteur", "expert")
    assert code == 2
    assert "pas encore extraite" in erreur


def test_fiche_montre_le_modele_la_correction_et_l_extraction_d_origine(base, capsys):
    lancer(capsys, base, "corriger", 1, 1, "millesime", "2001", "--auteur", "expert")

    code, sortie, _ = lancer(capsys, base, "fiche", 1, 1)

    millesime = next(ligne for ligne in sortie.splitlines() if ligne.strip().startswith("millesime "))
    assert code == 0
    assert "2018" in millesime and "2001   ← corrigé" in millesime
    assert "« 2018 » -> « 2001 » — expert" in sortie
    assert "réussie   ← fait foi" in sortie


def test_une_bouteille_se_designe_par_position_ou_identifiant(base, capsys):
    identifiant = lignes(base, "SELECT identifiant FROM bouteille WHERE position = 2")[0][0]
    code, sortie, _ = lancer(capsys, base, "fiche", 1, identifiant.lower())
    assert code == 0
    assert sortie.startswith(f"Bouteille n°2 — {identifiant}")


def test_stats_cout_et_corrections(base, capsys):
    lancer(capsys, base, "corriger", 1, 1, "millesime", "2001", "--auteur", "expert")
    code, sortie, _ = lancer(capsys, base, "stats", 1)
    assert code == 0
    assert all(morceau in sortie for morceau in ("Bouteilles   : 6", "extraite 6", "erreur 0", "validee 0"))
    assert "Tokens       : non mesurés" in sortie  # fixtures : aucun faux coût (0098)
    assert all(morceau in sortie for morceau in ("Corrections  : 1 sur 1", "millesime 1"))


def test_stats_de_relecture(base, capsys):
    """Les chiffres de la relecture à l'écran (guide de session 5, §6)."""
    from src.services.cas_particuliers import signaler_paire
    from src.services.relecture import valider

    with session_de_base(base) as session:
        valider(session, 1, "expert", temps_ms=12_000)
        signaler_paire(session, 2, "expert")
    code, sortie, _ = lancer(capsys, base, "stats", 1)
    assert code == 0
    assert all(morceau in sortie for morceau in ("12 s au total", "12.0 s par bouteille", "1 chronométrée(s)"))
    assert all(morceau in sortie for morceau in ("0 réanalysée(s)", "0 née(s) d'une séparation", "1 problème(s) de photos"))


def test_inventaire_ou_bouteille_introuvable(base, capsys):
    code, _, erreur = lancer(capsys, base, "bouteilles", 99)
    assert code == 2 and "Aucun inventaire n°99" in erreur
    code, _, erreur = lancer(capsys, base, "fiche", 1, 42)
    assert code == 2 and "Aucune bouteille « 42 »" in erreur


def test_un_export_vers_un_fichier_ouvert_dans_excel_le_dit(base, capsys, monkeypatch, tmp_path):
    def fichier_verrouille(session, inventaire_id, chemin):
        raise PermissionError(13, "Permission denied", str(chemin))

    monkeypatch.setattr(inventaire, "exporter", fichier_verrouille)
    code, _, erreur = lancer(capsys, base, "exporter", 1, "--sortie", tmp_path / "ouvert.xlsx")
    assert code == 2
    assert "ouvert dans Excel" in erreur
