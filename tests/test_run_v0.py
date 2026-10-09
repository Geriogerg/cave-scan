"""Le pipeline doit tourner de bout en bout sans clé API ni réseau (0012)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import run_v0
from src.compare.compare_listings import formater_signaux, relever_signaux
from src.extract.base import Extractor
from src.extract.fixture_extract import FixtureExtractor
from src.extract.schema import Bouteille, Couleur, Format
from src.io.photos import PhotosBouteille, grouper_photos
from src.normalize.normalize import REGLES, normalize
from tests.conftest import FIXTURES, RACINE


# --- la couture Extractor -----------------------------------------------


def test_fixture_extractor_respecte_le_protocol():
    """run_v0 dépend du Protocol, pas d'une implémentation (decisions.md 0014)."""
    extracteur = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")
    assert isinstance(extracteur, Extractor)


def test_fixture_extractor_rejoue_dans_l_ordre():
    extracteur = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")
    assert len(extracteur) == 6
    premiere = extracteur.extract("photo.jpg")
    deuxieme = extracteur.extract("photo.jpg")
    assert premiere.domaine == "Domaine Rossignol-Trapet"
    assert deuxieme.domaine == "Château Margaux"


def test_fixture_extractor_signale_l_epuisement():
    extracteur = FixtureExtractor([{"appellation": "Pommard"}])
    extracteur.extract("photo.jpg")
    with pytest.raises(IndexError, match="Fixtures épuisées"):
        extracteur.extract("photo.jpg")


# --- normalisation identité (decisions.md 0007) -------------------------


def test_normalize_est_l_identite_en_v0():
    assert REGLES == [], "La v0 ne doit contenir AUCUNE règle de normalisation."
    bouteille = Bouteille(
        domaine="Domaine du Vieux Télégraphe",
        appellation="CHÂTEAUNEUF-DU-PAPE",
        couleur=Couleur.ROUGE,
        format=Format.MAGNUM,
        contenance_cl=150,
    )
    assert normalize(bouteille) == bouteille


# --- regroupement des photos --------------------------------------------


def test_un_sous_dossier_par_bouteille(tmp_path):
    for nom in ("b02", "b01"):
        dossier = tmp_path / nom
        dossier.mkdir()
        (dossier / "01_etiquette.jpg").touch()
        (dossier / "02_contre_etiquette.jpg").touch()
        (dossier / "03_capsule.jpg").touch()

    bouteilles = grouper_photos(tmp_path)
    assert [b.nom for b in bouteilles] == ["b01", "b02"]

    premiere = bouteilles[0]
    assert premiere.etiquette.name == "01_etiquette.jpg"
    assert premiere.contre_etiquette.name == "02_contre_etiquette.jpg"
    assert [a.name for a in premiere.autres] == ["03_capsule.jpg"]


def test_dossier_plat_une_image_par_bouteille(tmp_path):
    (tmp_path / "a.jpg").touch()
    (tmp_path / "b.png").touch()
    (tmp_path / "notes.txt").touch()

    bouteilles = grouper_photos(tmp_path)
    assert len(bouteilles) == 2
    assert all(b.contre_etiquette is None for b in bouteilles)


def test_dossier_sans_image_leve_une_erreur(tmp_path):
    (tmp_path / "notes.txt").touch()
    with pytest.raises(ValueError, match="Aucune photo exploitable"):
        grouper_photos(tmp_path)


# --- bout en bout --------------------------------------------------------


def test_dry_run_produit_excel_et_rapport(tmp_path, capsys):
    sortie = tmp_path / "listing.xlsx"
    code = run_v0.main(["--dry-run", "--sortie", str(sortie)])
    sortie_texte = capsys.readouterr().out

    assert code == 0
    assert sortie.exists() and sortie.stat().st_size > 0
    assert "DRY-RUN" in sortie_texte
    assert "Comparaison auto vs manuel — 6 bouteille(s)" in sortie_texte
    assert "accuracy" in sortie_texte
    assert "Désaccords à inspecter (3)" in sortie_texte


def test_dry_run_n_importe_pas_le_sdk_anthropic(tmp_path):
    """Aucune dépendance API sur le chemin hors ligne."""
    sys.modules.pop("src.extract.vision_extract", None)
    run_v0.main(["--dry-run", "--sortie", str(tmp_path / "l.xlsx")])
    assert "src.extract.vision_extract" not in sys.modules


# --- journal et reprise (decisions.md 0046) -----------------------------


class ExtracteurQuiTombe:
    """Extrait normalement puis échoue à la n-ième bouteille."""

    def __init__(self, source: FixtureExtractor, tombe_a: int):
        self.source = source
        self.tombe_a = tombe_a
        self.appels = 0

    def extract(self, etiquette, contre_etiquette=None, autres=None):
        self.appels += 1
        if self.appels == self.tombe_a:
            raise ConnectionError("réseau coupé")
        return self.source.extract(etiquette, contre_etiquette, autres)


def _photos(nombre):
    return [
        PhotosBouteille(etiquette=Path(f"(fixture)/b{i}/etiquette.jpg"))
        for i in range(nombre)
    ]


def test_le_journal_est_ecrit_au_fil_de_l_eau(tmp_path):
    journal = tmp_path / "extraction.jsonl"
    extracteur = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")

    run_v0.extraire(extracteur, _photos(6), journal)

    lignes = journal.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 6
    assert json.loads(lignes[0])["domaine"] == "Domaine Rossignol-Trapet"


def test_une_interruption_ne_perd_pas_les_appels_deja_payes(tmp_path):
    """Le vrai enjeu : 180 appels API facturés ne doivent pas partir en fumée."""
    journal = tmp_path / "extraction.jsonl"
    source = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")

    with pytest.raises(ConnectionError):
        run_v0.extraire(ExtracteurQuiTombe(source, tombe_a=4), _photos(6), journal)

    rescapees = run_v0.charger_journal(journal)
    assert len(rescapees) == 3
    assert rescapees[0].domaine == "Domaine Rossignol-Trapet"


def test_reprendre_repart_du_journal(tmp_path, capsys):
    journal = tmp_path / "extraction.jsonl"
    source = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")

    with pytest.raises(ConnectionError):
        run_v0.extraire(ExtracteurQuiTombe(source, tombe_a=4), _photos(6), journal)

    # Nouvel extracteur, positionné sur les 3 bouteilles restantes.
    reste = FixtureExtractor(
        json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))[3:]
    )
    bouteilles = run_v0.extraire(reste, _photos(6), journal, reprendre=True)

    assert "reprise : 3 bouteille(s)" in capsys.readouterr().out
    assert len(bouteilles) == 6
    assert bouteilles[0].domaine == "Domaine Rossignol-Trapet"
    assert bouteilles[5].domaine == "Champagne Deutz"


def test_sans_reprendre_le_journal_est_reinitialise(tmp_path):
    journal = tmp_path / "extraction.jsonl"
    journal.write_text('{"domaine": "vieille execution"}\n', encoding="utf-8")

    extracteur = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")
    bouteilles = run_v0.extraire(extracteur, _photos(6), journal)

    assert len(bouteilles) == 6
    assert "vieille execution" not in journal.read_text(encoding="utf-8")


def test_dry_run_ecrit_aussi_un_journal(tmp_path):
    sortie = tmp_path / "listing.xlsx"
    run_v0.main(["--dry-run", "--sortie", str(sortie)])
    assert sortie.with_suffix(".jsonl").exists()


def test_mode_reel_exige_des_photos(tmp_path):
    """--manual, lui, est facultatif : son fichier n'existe pas encore."""
    with pytest.raises(SystemExit):
        run_v0.main(["--sortie", str(tmp_path / "l.xlsx")])


def test_les_signaux_se_lisent_sans_listing_expert():
    """Le mode d'attente : pas de score, mais on voit ce que le modèle produit."""
    auto = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")
    bouteilles = [auto.extract("p.jpg") for _ in range(len(auto))]

    texte = formater_signaux(relever_signaux(bouteilles))

    assert "observee 5/6" in texte
    assert "inferee 1/6" in texte
    assert "relecture 2/6" in texte


# --- identifiant stable (decisions.md 0065) ------------------------------------


def test_identifiant_stable_et_insensible_au_renommage(tmp_path):
    etiquette, contre = tmp_path / "a.jpg", tmp_path / "b.jpg"
    etiquette.write_bytes(b"photo etiquette")
    contre.write_bytes(b"photo contre")
    premier = PhotosBouteille(etiquette=etiquette, contre_etiquette=contre).identifiant

    assert PhotosBouteille(etiquette=etiquette, contre_etiquette=contre).identifiant == premier
    renommee = etiquette.rename(tmp_path / "IMG_9999.jpg")
    assert PhotosBouteille(etiquette=renommee, contre_etiquette=contre).identifiant == premier
    contre.write_bytes(b"autre photo")
    assert PhotosBouteille(etiquette=renommee, contre_etiquette=contre).identifiant != premier


def test_chaque_bouteille_recoit_l_identifiant_de_ses_photos(tmp_path):
    journal = tmp_path / "extraction.jsonl"
    photos = _photos(6)
    extracteur = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")

    bouteilles = run_v0.extraire(extracteur, photos, journal)

    assert [b.id for b in bouteilles] == [vues.identifiant for vues in photos]
    premiere = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
    assert premiere["id"] == photos[0].identifiant


def test_photos_en_double_arretent_avant_tout_appel(tmp_path):
    """Une photo copiée deux fois : on s'arrête avant de payer deux fois."""
    (tmp_path / "x.jpg").write_bytes(b"meme photo")
    (tmp_path / "y.jpg").write_bytes(b"meme photo")
    appels = []

    class Espion:
        def extract(self, *arguments, **options):
            appels.append(1)
            return Bouteille()

    photos = [PhotosBouteille(etiquette=tmp_path / "x.jpg"), PhotosBouteille(etiquette=tmp_path / "y.jpg")]
    with pytest.raises(ValueError, match="Photos identiques"):
        run_v0.extraire(Espion(), photos)
    assert appels == []


def test_reprise_sur_un_dossier_modifie_est_refusee(tmp_path):
    """Sinon chaque bouteille reprise serait décalée d'une ligne, en silence."""
    journal = tmp_path / "extraction.jsonl"
    source = FixtureExtractor.depuis_json(FIXTURES / "bouteilles_auto.json")
    with pytest.raises(ConnectionError):
        run_v0.extraire(ExtracteurQuiTombe(source, tombe_a=4), _photos(6), journal)

    autres = [PhotosBouteille(etiquette=Path(f"(autre)/b{i}/etiquette.jpg")) for i in range(6)]
    with pytest.raises(ValueError, match="ne correspond plus aux photos"):
        run_v0.extraire(FixtureExtractor([]), autres, journal, reprendre=True)


def test_quantite_modifiee_au_journal_est_respectee_au_rejeu(tmp_path):
    """« Modifiable par l'expert » : sans interface, via le journal puis --auto.
    Deux bouteilles identiques de quantités 2 et 1 donnent une ligne de 3."""
    from openpyxl import load_workbook

    from src.config.maison import charger_config
    from src.extract.schema import from_tool_input

    config = charger_config(RACINE / "config" / "maisons" / "maison_test.json")
    charge = {}
    for colonne in config.colonnes_modele:
        if colonne.type == "liste":
            charge[colonne.cle] = colonne.codes[0]
        elif colonne.type == "nombre":
            charge[colonne.cle] = 1
        else:
            charge[colonne.cle] = "Texte lu"

    journal = tmp_path / "extraction.jsonl"
    lignes = []
    for identifiant, quantite in (("B-1", 2), ("B-2", 1)):
        bouteille = from_tool_input(charge, config)
        bouteille.id, bouteille.quantite = identifiant, quantite
        lignes.append(json.dumps(bouteille.as_dict(), ensure_ascii=False))
    journal.write_text("\n".join(lignes) + "\n", encoding="utf-8")

    sortie = tmp_path / "listing.xlsx"
    assert run_v0.main(["--auto", str(journal), "--sortie", str(sortie)]) == 0

    feuille = load_workbook(sortie).active
    index = [c.cle for c in config.colonnes].index("quantite") + 1
    assert [feuille.cell(row=r, column=index).value for r in range(2, feuille.max_row + 1)] == [3]
