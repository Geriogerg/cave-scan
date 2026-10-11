"""La base : créée par les migrations, et gardienne de la sortie du modèle.

Critère d'acceptation : la migration initiale crée la base de zéro. Et ce qui
ne doit jamais bouger — sortie brute d'une extraction, historique des
corrections — est refusé par le modèle de données lui-même (decisions.md 0072).
"""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from src.donnees.base import creer_moteur, dossier_stockage, migrer, url_de_base
from src.donnees.modeles import (
    Base,
    ConfigVersion,
    Correction,
    EnregistrementImmuable,
    Extraction,
    FicheBouteille,
    GroupePhotos,
    Inventaire,
    Maison,
    Photo,
)

TABLES = {"maison", "config_version", "inventaire", "photo", "bouteille", "extraction", "correction"}


# --- migrations (decisions.md 0075) ----------------------------------------------


def test_la_migration_initiale_cree_la_base_de_zero(tmp_path):
    """Critère d'acceptation du guide."""
    chemin = tmp_path / "neuve.db"
    assert not chemin.exists()

    migrer(url_de_base(chemin))

    tables = set(inspect(create_engine(url_de_base(chemin))).get_table_names())
    assert TABLES <= tables
    assert "alembic_version" in tables


def test_les_migrations_decrivent_exactement_les_modeles(base_modele):
    """Une colonne ajoutée au modèle sans migration ferait échouer ce test : le
    schéma ne dérive jamais en silence."""
    moteur = create_engine(url_de_base(base_modele))
    with moteur.connect() as connexion:
        ecarts = compare_metadata(MigrationContext.configure(connexion), Base.metadata)
    moteur.dispose()
    assert ecarts == []


def test_migrer_une_base_a_jour_ne_change_rien(tmp_path):
    url = url_de_base(tmp_path / "base.db")
    migrer(url)
    migrer(url)  # deuxième passage : rien à faire, aucune erreur
    assert TABLES <= set(inspect(create_engine(url)).get_table_names())


def test_la_base_et_le_stockage_viennent_des_variables_d_environnement(tmp_path, monkeypatch):
    monkeypatch.setenv("CAVE_SCAN_DB", str(tmp_path / "ailleurs.db"))
    monkeypatch.setenv("CAVE_SCAN_STOCKAGE", str(tmp_path / "photos"))
    assert url_de_base().endswith("ailleurs.db")
    assert dossier_stockage() == (tmp_path / "photos").resolve()


def test_une_url_complete_est_prise_telle_quelle():
    """Le passage à PostgreSQL ne demande que de changer CAVE_SCAN_DB."""
    assert url_de_base("postgresql://cave@serveur/scan") == "postgresql://cave@serveur/scan"


def test_les_tests_n_atteignent_jamais_la_vraie_base():
    """Garde-fou de conftest.py : la base par défaut est redirigée."""
    from src.donnees.base import BASE_DEFAUT, STOCKAGE_DEFAUT

    assert url_de_base() != url_de_base(BASE_DEFAUT)
    assert "isolee" in url_de_base()
    assert dossier_stockage() != STOCKAGE_DEFAUT.resolve()


# --- intégrité --------------------------------------------------------------------


def peupler(session):
    """Le minimum pour poser une bouteille et une extraction."""
    maison = Maison(nom="Maison Test")
    config = ConfigVersion(
        maison=maison, numero=1, version_declaree=1, contenu="{}",
        empreinte="e" * 64, fichier_source="maison.json",
    )
    inventaire = Inventaire(maison=maison, config_version=config, nom="Cave A")
    session.add(inventaire)
    session.flush()
    groupe = GroupePhotos(inventaire_id=inventaire.id, numero=1)  # une bouteille = ses photos (0166)
    photos = [
        Photo(inventaire_id=inventaire.id, chemin=f"{i}.jpg", empreinte=str(i) * 64,
              nom_origine=f"IMG_{i}.jpg", ordre=i, groupe=groupe, rang=i + 1)
        for i in range(2)
    ]
    session.add_all(photos)
    session.flush()
    bouteille = FicheBouteille(
        inventaire_id=inventaire.id, identifiant="B-0000000001", groupe=groupe, position=1,
    )
    session.add(bouteille)
    session.flush()
    extraction = Extraction(
        bouteille_id=bouteille.id, sortie_brute={"appellation": "Pommard"},
        modele="fixture", version_prompt="abc", duree_ms=12,
    )
    session.add(extraction)
    session.commit()
    return bouteille, extraction


def test_les_cles_etrangeres_sont_verifiees(session):
    """SQLite ne les vérifie pas par défaut : une bouteille orpheline passerait."""
    session.add(FicheBouteille(inventaire_id=999, identifiant="B-X", groupe_id=998, position=1))
    with pytest.raises(IntegrityError):
        session.commit()


def test_la_quantite_ne_descend_jamais_sous_un(session):
    bouteille, _ = peupler(session)
    bouteille.quantite = 0
    with pytest.raises(IntegrityError):
        session.commit()


def test_un_statut_inconnu_est_refuse(session):
    bouteille, _ = peupler(session)
    bouteille.statut = "presque_finie"
    with pytest.raises(IntegrityError):
        session.commit()


def test_la_meme_photo_deux_fois_dans_un_inventaire_est_refusee(session):
    bouteille, _ = peupler(session)
    session.add(Photo(
        inventaire_id=bouteille.inventaire_id, chemin="x.jpg",
        empreinte="0" * 64, nom_origine="copie.jpg", ordre=9,
    ))
    with pytest.raises(IntegrityError):
        session.commit()


def test_valeurs_par_defaut(session):
    bouteille, extraction = peupler(session)
    assert bouteille.quantite == 1
    assert bouteille.statut == "a_extraire"
    assert bouteille.inventaire.statut == "ouvert"
    assert extraction.cree_le is not None


# --- la sortie du modèle ne bouge jamais (decisions.md 0072) ----------------------------


def test_la_sortie_brute_ne_peut_pas_etre_modifiee(session):
    """L'erreur la plus grave de la session : un écrasement de l'extraction."""
    _, extraction = peupler(session)
    extraction.sortie_brute = {"appellation": "Volnay"}
    with pytest.raises(EnregistrementImmuable, match="immuable"):
        session.commit()
    session.rollback()
    assert session.get(Extraction, extraction.id).sortie_brute == {"appellation": "Pommard"}


@pytest.mark.parametrize("champ, valeur", [("modele", "autre"), ("tokens_sortie", 9999)])
def test_la_trace_d_une_extraction_ne_peut_pas_etre_modifiee(session, champ, valeur):
    _, extraction = peupler(session)
    setattr(extraction, champ, valeur)
    with pytest.raises(EnregistrementImmuable):
        session.commit()


def test_seule_l_erreur_d_une_extraction_peut_etre_completee(session):
    """Une interprétation impossible se note APRÈS l'enregistrement (decisions.md 0078)."""
    _, extraction = peupler(session)
    extraction.erreur = "réponse inexploitable"
    session.commit()
    assert session.get(Extraction, extraction.id).erreur == "réponse inexploitable"


def test_une_extraction_ne_peut_pas_etre_supprimee(session):
    _, extraction = peupler(session)
    session.delete(extraction)
    with pytest.raises(EnregistrementImmuable, match="ne se supprime jamais"):
        session.commit()


def test_une_correction_ne_peut_etre_ni_modifiee_ni_supprimee(session):
    bouteille, _ = peupler(session)
    correction = Correction(
        bouteille_id=bouteille.id, champ="millesime", ancienne_valeur="non_lisible",
        nouvelle_valeur="2015", auteur="expert",
    )
    session.add(correction)
    session.commit()

    correction.nouvelle_valeur = "2016"
    with pytest.raises(EnregistrementImmuable, match="ne se réécrit pas"):
        session.commit()
    session.rollback()

    session.delete(session.get(Correction, correction.id))
    with pytest.raises(EnregistrementImmuable, match="ne se supprime pas"):
        session.commit()


def test_une_valeur_absente_est_stockee_comme_absente(session):
    """Ni « null » texte, ni chaîne vide : une vraie absence (NULL)."""
    bouteille, _ = peupler(session)
    vide = Extraction(bouteille_id=bouteille.id, sortie_brute=None, modele="m",
                      version_prompt="v", duree_ms=1, erreur="rien reçu")
    session.add(vide)
    session.commit()
    moteur = creer_moteur(str(session.get_bind().url))
    with moteur.connect() as connexion:
        brut = connexion.exec_driver_sql(
            "SELECT sortie_brute FROM extraction WHERE id = ?", (vide.id,)
        ).scalar()
    moteur.dispose()
    assert brut is None


def test_la_migration_0002_garde_les_donnees_d_une_base_existante(tmp_path):
    """Une base créée avant la contre-étiquette facultative (0108) passe à 0002
    sans rien perdre, et accepte ensuite une bouteille sans contre-étiquette."""
    from alembic import command
    from alembic.config import Config as ConfigAlembic

    from src.donnees.base import RACINE

    url = url_de_base(tmp_path / "ancienne.db")
    configuration = ConfigAlembic(str(RACINE / "alembic.ini"))
    configuration.set_main_option("script_location", str(RACINE / "migrations"))
    configuration.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    configuration.attributes["depuis_le_code"] = True
    command.upgrade(configuration, "0001")

    moteur = create_engine(url)
    with moteur.begin() as connexion:
        connexion.exec_driver_sql("INSERT INTO maison (id, nom) VALUES (1, 'Maison')")
        connexion.exec_driver_sql(
            "INSERT INTO config_version (id, maison_id, numero, version_declaree, contenu, "
            "empreinte, fichier_source, cree_le) VALUES (1, 1, 1, 1, '{}', 'e', 'c.json', '2026-01-01')"
        )
        connexion.exec_driver_sql(
            "INSERT INTO inventaire (id, maison_id, config_version_id, nom, cree_le, statut, "
            "dossier_source) VALUES (1, 1, 1, 'Cave', '2026-01-01', 'ouvert', 'x')"
        )
        for numero in (1, 2):
            connexion.exec_driver_sql(
                f"INSERT INTO photo (id, inventaire_id, chemin, empreinte, nom_origine, ordre) "
                f"VALUES ({numero}, 1, 'p{numero}.jpg', 'h{numero}', 'p{numero}.jpg', {numero})"
            )
        connexion.exec_driver_sql(
            "INSERT INTO bouteille (id, inventaire_id, identifiant, photo_etiquette_id, "
            "photo_contre_id, position, quantite, statut) VALUES (1, 1, 'B-1', 1, 2, 1, 1, 'a_extraire')"
        )
    moteur.dispose()

    migrer(url)

    moteur = create_engine(url)
    with moteur.begin() as connexion:
        # 0006 : la paire étiquette / contre-étiquette devient le groupe de photos de
        # la bouteille, dans le même ordre ; l'identifiant ne bouge pas.
        assert connexion.exec_driver_sql(
            "SELECT b.identifiant, p.id, p.rang FROM bouteille b JOIN photo p ON p.groupe_id = b.groupe_id "
            "ORDER BY p.rang"
        ).fetchall() == [("B-1", 1, 1), ("B-1", 2, 2)]
        # 0003 : l'inventaire existant reçoit l'état d'extraction par défaut.
        assert connexion.exec_driver_sql("SELECT extraction FROM inventaire").scalar() == "non_lancee"
        # 0002 puis 0006 : une bouteille d'une seule photo est possible.
        connexion.exec_driver_sql(
            "INSERT INTO groupe_photos (id, inventaire_id, numero, quantite, cree_le) VALUES (2, 1, 2, 1, '2026-01-01')"
        )
        connexion.exec_driver_sql(
            "INSERT INTO photo (id, inventaire_id, chemin, empreinte, nom_origine, ordre, groupe_id, rang) "
            "VALUES (3, 1, 'p3.jpg', 'h3', 'p3.jpg', 3, 2, 1)"
        )
        connexion.exec_driver_sql(
            "INSERT INTO bouteille (id, inventaire_id, identifiant, groupe_id, position, quantite, statut) "
            "VALUES (2, 1, 'B-2', 2, 2, 1, 'a_extraire')"
        )
    moteur.dispose()
