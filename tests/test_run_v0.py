"""Le pipeline doit tourner de bout en bout sans clé API ni réseau (0012).

Session 2 : la ligne de commande passe par les services et la base. Les tests
du journal ont été adaptés un à un (decisions.md 0079, 0084, 0085) : chacun
garde l'exigence qu'il protégeait — ne jamais perdre un appel payé, reprendre
sans rien refaire, ne jamais décaler une bouteille — vérifiée sur la base.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine

import inventaire
import run_v0
from src.compare.compare_listings import formater_signaux, relever_signaux
from src.config.maison import charger_config
from src.donnees.base import dossier_stockage, session_de_base, url_de_base
from src.donnees.stockage import chemin_stocke
from src.extract.base import Extractor
from src.extract.fixture_extract import FixtureExtractor, generer_photos_fictives
from src.extract.schema import Bouteille, Couleur, Format
from src.io.photos import PhotosBouteille, grouper_photos
from src.normalize.normalize import REGLES, normalize
from src.services.inventaires import charger_inventaire, lister_inventaires
from src.services.relecture import valeurs_modele
from src.services.restitution import lister_bouteilles
from tests.conftest import CONFIG_TEST, FIXTURES, RACINE


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


# --- photos ---------------------------------------------------------------
# Une bouteille = un groupe de photos : une photo à la racine, ou un
# sous-dossier (decisions.md 0166). Le détail est dans tests/test_photos.py.


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


# --- outillage : la ligne de commande sans jamais appeler un vrai modèle -------------


def fixtures(depuis: int = 0) -> FixtureExtractor:
    """Les réponses enregistrées, à partir de la bouteille n° `depuis` + 1."""
    charges = json.loads((FIXTURES / "bouteilles_auto.json").read_text(encoding="utf-8"))
    return FixtureExtractor(charges[depuis:], charger_config(CONFIG_TEST))


class ExtracteurQuiTombe(FixtureExtractor):
    """Rejoue les fixtures, puis tombe à la n-ième bouteille : interruption
    (Ctrl-C, coupure) ou panne systématique (clé refusée…)."""

    def __init__(self, tombe_a: int, panne: BaseException | None = None):
        source = fixtures()
        super().__init__(source._charges, source.config)
        self.tombe_a = tombe_a
        self.panne = panne if panne is not None else KeyboardInterrupt()
        self.appels = 0

    def extraire_brut(self, photos):
        self.appels += 1
        if self.appels == self.tombe_a:
            raise self.panne
        return super().extraire_brut(photos)


def brancher(monkeypatch, *extracteurs) -> None:
    """Les extracteurs que run_v0 utilisera, un par lancement, dans l'ordre."""
    file = list(extracteurs)
    monkeypatch.setattr(run_v0, "_extracteur", lambda backend, config, inventaire_id: file.pop(0))


def lancer(*arguments) -> int:
    return run_v0.main([str(argument) for argument in arguments])


def requete(base: Path, sql: str) -> list[tuple]:
    """Lu en SQL brut par une AUTRE connexion que celle de la ligne de commande."""
    moteur = create_engine(url_de_base(base))
    with moteur.connect() as connexion:
        lignes = [tuple(ligne) for ligne in connexion.exec_driver_sql(sql)]
    moteur.dispose()
    return lignes


def statuts(base: Path) -> list[str]:
    return [statut for (statut,) in requete(base, "SELECT statut FROM bouteille ORDER BY position")]


def colonne_excel(chemin: Path, cle: str) -> list:
    config = charger_config(CONFIG_TEST)
    index = [colonne.cle for colonne in config.colonnes].index(cle) + 1
    feuille = load_workbook(chemin).active
    return [feuille.cell(row=rang, column=index).value for rang in range(2, feuille.max_row + 1)]


# --- chaque appel payé est en base dès son retour (remplace le journal, 0079) -------------


def test_chaque_extraction_est_en_base_des_son_retour(tmp_path, dossier_photos, monkeypatch):
    """Successeur de « le journal est écrit au fil de l'eau » : quand le modèle est
    appelé pour la bouteille n, les n-1 réponses précédentes sont déjà en base —
    vues depuis une autre connexion."""
    base = tmp_path / "cave.db"
    deja_en_base = []

    class Espion(FixtureExtractor):
        def extraire_brut(self, photos):
            deja_en_base.append(requete(base, "SELECT count(*) FROM extraction")[0][0])
            return super().extraire_brut(photos)

    source = fixtures()
    brancher(monkeypatch, Espion(source._charges, source.config))

    assert lancer("--photos", dossier_photos, "--base", base, "--sortie", tmp_path / "l.xlsx") == 0
    assert deja_en_base == [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    "panne, statut_de_la_quatrieme",
    [
        # Session 3 : un Ctrl-C rend la bouteille à la file (decisions.md 0112).
        pytest.param(KeyboardInterrupt(), "a_extraire", id="interruption"),
        pytest.param(PermissionError("clé API invalide"), "erreur", id="panne-systematique"),
    ],
)
def test_une_interruption_ne_perd_pas_les_appels_deja_payes(
    tmp_path, dossier_photos, monkeypatch, capsys, panne, statut_de_la_quatrieme
):
    """Le vrai enjeu : 180 appels API facturés ne doivent pas partir en fumée."""
    base = tmp_path / "cave.db"
    brancher(monkeypatch, ExtracteurQuiTombe(tombe_a=4, panne=panne))

    code = lancer("--photos", dossier_photos, "--base", base, "--sortie", tmp_path / "l.xlsx")

    assert code == 2
    assert "python run_v0.py --inventaire 1" in capsys.readouterr().err
    assert statuts(base) == ["extraite"] * 3 + [statut_de_la_quatrieme, "a_extraire", "a_extraire"]
    with session_de_base(base) as session:
        premiere = lister_bouteilles(session, 1)[0]
        assert valeurs_modele(session, premiere.id).domaine == "Domaine Rossignol-Trapet"


def test_inventaire_id_reprend_la_ou_l_extraction_s_est_arretee(
    tmp_path, dossier_photos, monkeypatch, capsys
):
    """Successeur de « reprendre repart du journal » : seules les bouteilles
    restantes sont extraites, dans l'ordre — un extracteur de 3 fixtures
    s'épuiserait (et l'inventaire s'arrêterait) au moindre appel de trop."""
    base, sortie = tmp_path / "cave.db", tmp_path / "listing.xlsx"
    brancher(monkeypatch, ExtracteurQuiTombe(tombe_a=4), fixtures(depuis=3))
    assert lancer("--photos", dossier_photos, "--base", base, "--sortie", sortie) == 2
    capsys.readouterr()

    code = lancer("--inventaire", 1, "--base", base, "--sortie", sortie)

    texte = capsys.readouterr().out
    assert code == 0
    assert "3 bouteille(s) à extraire" in texte
    assert "3 extraite(s), 0 en erreur, 3 déjà faite(s)" in texte
    assert statuts(base) == ["extraite"] * 6
    domaines = colonne_excel(sortie, "domaine")
    assert domaines[0] == "Domaine Rossignol-Trapet"
    assert domaines[-1] == "Champagne Deutz"

    # Tout est extrait : réexporter et rescorer sans créer de client (successeur de --auto).
    assert lancer("--inventaire", 1, "--base", base, "--sortie", sortie) == 0
    assert "aucun appel au modèle" in capsys.readouterr().out


def test_un_nouveau_lancement_repart_de_zero_sans_toucher_l_ancien(
    tmp_path, dossier_photos, monkeypatch
):
    """Successeur de « sans reprendre, le journal est réinitialisé » : relancer sur
    les mêmes photos crée un NOUVEL inventaire, et l'ancien reste intact."""
    base = tmp_path / "cave.db"
    brancher(monkeypatch, fixtures(), fixtures())
    assert lancer("--photos", dossier_photos, "--base", base, "--sortie", tmp_path / "l.xlsx") == 0
    premieres = requete(base, "SELECT * FROM extraction ORDER BY id")

    assert lancer("--photos", dossier_photos, "--base", base, "--sortie", tmp_path / "l.xlsx") == 0

    assert requete(base, "SELECT * FROM extraction ORDER BY id")[: len(premieres)] == premieres
    par_inventaire = requete(
        base,
        "SELECT b.inventaire_id, count(e.id) FROM bouteille b JOIN extraction e "
        "ON e.bouteille_id = b.id GROUP BY b.inventaire_id ORDER BY b.inventaire_id",
    )
    assert par_inventaire == [(1, 6), (2, 6)]


def test_le_dry_run_n_ecrit_jamais_dans_la_base_de_l_utilisateur(tmp_path):
    """Successeur de « le dry-run écrit aussi un journal » : base et stockage du
    dry-run sont temporaires (decisions.md 0085)."""
    base_utilisateur = Path(os.environ["CAVE_SCAN_DB"])
    stockage_utilisateur = Path(os.environ["CAVE_SCAN_STOCKAGE"])

    assert lancer("--dry-run", "--sortie", tmp_path / "l.xlsx") == 0

    assert not base_utilisateur.exists()
    assert not stockage_utilisateur.exists()


def test_le_dry_run_avec_base_garde_l_inventaire_de_demonstration(tmp_path):
    """Pour essayer inventaire.py sans clé ; ses photos restent lisibles."""
    base = tmp_path / "demo.db"
    assert lancer("--dry-run", "--base", base, "--sortie", tmp_path / "l.xlsx") == 0

    with session_de_base(base) as session:
        demo = charger_inventaire(session, 1)
        assert [b.statut for b in demo.bouteilles] == ["extraite"] * 6
        assert all(chemin_stocke(dossier_stockage(), photo.chemin).is_file() for photo in demo.photos)


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
    premier = PhotosBouteille(photos=(etiquette, contre), nom="a").identifiant

    assert PhotosBouteille(photos=(etiquette, contre), nom="a").identifiant == premier
    renommee = etiquette.rename(tmp_path / "IMG_9999.jpg")
    assert PhotosBouteille(photos=(renommee, contre), nom="b").identifiant == premier
    contre.write_bytes(b"autre photo")
    assert PhotosBouteille(photos=(renommee, contre), nom="b").identifiant != premier


def test_chaque_bouteille_recoit_l_identifiant_de_ses_photos(tmp_path, dossier_photos, monkeypatch):
    """En base et à l'export, posé par l'outil, jamais par le modèle."""
    base, sortie = tmp_path / "cave.db", tmp_path / "listing.xlsx"
    attendus = [vues.identifiant for vues in grouper_photos(dossier_photos).bouteilles]
    brancher(monkeypatch, fixtures())

    assert lancer("--photos", dossier_photos, "--base", base, "--sortie", sortie) == 0

    assert [identifiant for (identifiant,) in requete(base, "SELECT identifiant FROM bouteille ORDER BY position")] == attendus
    assert colonne_excel(sortie, "id") == attendus


def test_photos_en_double_arretent_avant_tout_appel(tmp_path, dossier_photos, monkeypatch, capsys):
    """Une photo copiée deux fois : on s'arrête avant de payer deux fois — et
    avant même de créer le client du modèle ou l'inventaire."""
    shutil.copy(dossier_photos / "bouteille_02" / "1_etiquette.jpg", dossier_photos / "copie_etiquette.jpg")
    shutil.copy(dossier_photos / "bouteille_02" / "2_contre.jpg", dossier_photos / "copie_contre.jpg")
    base = tmp_path / "cave.db"
    clients = []
    monkeypatch.setattr(run_v0, "_extracteur", lambda *arguments: clients.append(1) or fixtures())

    code = lancer("--photos", dossier_photos, "--base", base, "--sortie", tmp_path / "l.xlsx")

    assert code == 2
    assert "La même photo est déposée deux fois" in capsys.readouterr().err
    assert clients == []
    assert requete(base, "SELECT count(*) FROM inventaire") == [(0,)]


def test_la_reprise_ne_relit_jamais_le_dossier_d_origine(tmp_path, dossier_photos, monkeypatch):
    """Successeur de « reprise sur un dossier modifié refusée » : les photos sont
    copiées dans le stockage de l'outil à la création. Le dossier d'origine peut
    changer ou disparaître, la reprise extrait les MÊMES photos, sans décalage."""
    base = tmp_path / "cave.db"
    recues = []

    class Espion(FixtureExtractor):
        def extraire_brut(self, photos):
            recues.extend(Path(photo) for photo in photos)
            return super().extraire_brut(photos)

    reste = fixtures(depuis=3)
    brancher(monkeypatch, ExtracteurQuiTombe(tombe_a=4), Espion(reste._charges, reste.config))
    assert lancer("--photos", dossier_photos, "--base", base, "--sortie", tmp_path / "l.xlsx") == 2
    identifiants = requete(base, "SELECT identifiant FROM bouteille ORDER BY position")

    shutil.rmtree(dossier_photos)
    assert lancer("--inventaire", 1, "--base", base, "--sortie", tmp_path / "l.xlsx") == 0

    assert len(recues) == 6
    assert all(photo.parent == dossier_stockage() and photo.is_file() for photo in recues)
    assert requete(base, "SELECT identifiant FROM bouteille ORDER BY position") == identifiants
    assert statuts(base) == ["extraite"] * 6


def test_la_quantite_corrigee_par_l_expert_s_additionne_a_l_export(tmp_path, monkeypatch):
    """Successeur du rejeu d'un journal modifié à la main : la quantité se corrige
    par inventaire.py. Deux bouteilles identiques de quantités 2 et 1 donnent une
    ligne de 3."""
    config = charger_config(CONFIG_TEST)
    charge = {}
    for colonne in config.colonnes_modele:
        if colonne.type == "liste":
            charge[colonne.cle] = colonne.codes[0]
        elif colonne.type == "nombre":
            charge[colonne.cle] = 1
        else:
            charge[colonne.cle] = "Texte lu"
    photos = generer_photos_fictives(tmp_path / "photos", 2)
    base, sortie = tmp_path / "cave.db", tmp_path / "corrige.xlsx"
    brancher(monkeypatch, FixtureExtractor([charge, charge], config))
    assert lancer("--photos", photos, "--base", base, "--sortie", tmp_path / "l.xlsx") == 0

    assert inventaire.main(["corriger", "1", "1", "quantite", "2", "--auteur", "expert", "--base", str(base)]) == 0
    assert inventaire.main(["exporter", "1", "--sortie", str(sortie), "--base", str(base)]) == 0

    assert colonne_excel(sortie, "quantite") == [3]


# --- photos vérifiées avant tout appel (decisions.md 0159, 0166) ------------------


def test_photos_invalides_signalees_sans_cle_ni_appel(tmp_path, capsys, monkeypatch):
    """Le refus arrive AVANT la création du client du modèle : aucune clé
    n'est nécessaire pour apprendre qu'une bouteille a trop de photos."""
    from PIL import Image

    for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    dossier = tmp_path / "photos" / "bouteille_01"
    dossier.mkdir(parents=True)
    for rang in range(5):  # plafond de la maison : 4
        Image.new("RGB", (8, 8), (rang, 0, 0)).save(dossier / f"IMG_000{rang}.jpg", "JPEG")

    code = run_v0.main(["--photos", str(tmp_path / "photos"), "--sortie", str(tmp_path / "l.xlsx")])

    assert code == 2
    assert "plafond de 4 photos" in capsys.readouterr().err
    assert not (tmp_path / "l.xlsx").exists()


def test_cle_absente_l_inventaire_est_garde_et_la_reprise_indiquee(
    tmp_path, dossier_photos, monkeypatch, capsys
):
    """Les photos sont vérifiées et stockées avant que la clé soit nécessaire : il
    suffit de reprendre l'inventaire une fois la clé renseignée."""
    import google.genai

    def client_sans_cle(*arguments, **options):
        raise ValueError("Missing key inputs argument!")  # ce que répond le SDK

    monkeypatch.setattr(google.genai, "Client", client_sans_cle)
    base = tmp_path / "cave.db"

    code = lancer("--photos", dossier_photos, "--base", base, "--sortie", tmp_path / "l.xlsx")

    erreur = capsys.readouterr().err
    assert code == 2
    assert "Clé Gemini absente" in erreur
    assert "python run_v0.py --inventaire 1" in erreur
    assert statuts(base) == ["a_extraire"] * 6


def test_listing_manuel_introuvable_signale_avant_tout_appel(tmp_path, dossier_photos, monkeypatch, capsys):
    base = tmp_path / "cave.db"
    clients = []
    monkeypatch.setattr(run_v0, "_extracteur", lambda *arguments: clients.append(1) or fixtures())

    code = lancer("--photos", dossier_photos, "--manual", tmp_path / "absent.xlsx", "--base", base)

    assert code == 2
    assert "Listing manuel introuvable" in capsys.readouterr().err
    assert clients == []


def test_inventaire_inconnu(tmp_path, capsys):
    assert lancer("--inventaire", 99, "--base", tmp_path / "cave.db") == 2
    assert "Aucun inventaire n°99" in capsys.readouterr().err


def test_photos_et_inventaire_sont_exclusifs(tmp_path):
    with pytest.raises(SystemExit):
        lancer("--photos", tmp_path, "--inventaire", 1)


# --- options remplacées : un message qui nomme la remplaçante (decisions.md 0084) ---------


@pytest.mark.parametrize(
    "options",
    [
        ["--journal", "out/listing_auto.jsonl"],
        ["--journal"],
        ["--photos", "data/photos", "--reprendre"],
        ["--auto", "out/listing_auto.jsonl"],
        ["--auto", "out/listing_auto.jsonl", "--manual", "listing.xlsx"],
    ],
)
def test_une_option_remplacee_dit_par_quoi_la_remplacer(options, capsys):
    code = run_v0.main(options)

    erreur = capsys.readouterr().err
    assert code == 2
    assert "--inventaire ID" in erreur
    assert "unrecognized arguments" not in erreur


# --- une photo à la racine = une bouteille (decisions.md 0166, qui remplace 0108) -----------


def test_une_photo_a_la_racine_une_bouteille_de_bout_en_bout(tmp_path, monkeypatch, capsys):
    """Un dossier d'étiquettes seules, à plat, en nombre impair : une bouteille par
    photo, le modèle reçoit une photo par bouteille, l'export a une ligne par photo."""
    from PIL import Image

    photos = tmp_path / "photos"
    photos.mkdir()
    for rang in range(3):
        Image.new("RGB", (8, 8), (rang * 60, 10, 10)).save(photos / f"etiquette_{rang + 1}.jpg", "JPEG")
    base, sortie = tmp_path / "cave.db", tmp_path / "l.xlsx"
    recues = []

    class Espion(FixtureExtractor):
        def extraire_brut(self, photos):
            recues.append(len(photos))
            return super().extraire_brut(photos)

    source = fixtures()
    brancher(monkeypatch, Espion(source._charges, source.config))

    code = lancer("--photos", photos, "--base", base, "--sortie", sortie)

    assert code == 0
    assert "1. B-" in capsys.readouterr().out
    assert recues == [1, 1, 1]  # une photo par bouteille, rien d'autre
    assert requete(base, "SELECT count(*) FROM photo GROUP BY groupe_id") == [(1,), (1,), (1,)]
    assert len(colonne_excel(sortie, "id")) == 3
    assert inventaire.main(["fiche", "1", "1", "--base", str(base)]) == 0
    assert "Photos : etiquette_1.jpg" in capsys.readouterr().out


def test_l_option_sans_contre_dit_par_quoi_elle_est_remplacee(capsys):
    code = run_v0.main(["--photos", "data/photos", "--sans-contre"])
    erreur = capsys.readouterr().err
    assert code == 2 and "sous-dossier" in erreur and "unrecognized arguments" not in erreur
