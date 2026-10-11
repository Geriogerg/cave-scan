"""Création d'un inventaire : config figée, photos stockées, bouteilles formées.

Critères d'acceptation couverts : la même photo déposée deux fois est détectée
(empreinte) ; modifier le JSON de config après création ne change pas la version
de cet inventaire, un nouvel inventaire utilise une nouvelle version.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from sqlalchemy import LargeBinary, func, inspect, select

from src.config.maison import ConfigInvalide
from src.donnees.modeles import Base, ConfigVersion, FicheBouteille, GroupePhotos, Inventaire, Photo
from src.io.photos import PhotosInvalides, grouper_photos
from src.services.inventaires import charger_inventaire, config_figee, creer_inventaire
from tests.conftest import CONFIG_TEST


def creer(session, nom_maison, dossier, stockage, config=CONFIG_TEST, **options):
    return creer_inventaire(session, nom_maison, config, dossier, "Cave test", stockage, **options)


def config_modifiee(tmp_path, modifier, nom="maison.json"):
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    modifier(brut)
    chemin = tmp_path / nom
    chemin.write_text(json.dumps(brut, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin


def compter(session, modele):
    return session.scalar(select(func.count()).select_from(modele))


# --- ce que la création enregistre ---------------------------------------------------


def test_creation_complete(session, nom_maison, dossier_photos, stockage):
    cree = creer(session, nom_maison, dossier_photos, stockage)
    inventaire = charger_inventaire(session, cree.inventaire_id)

    assert cree.nb_bouteilles == 6
    assert inventaire.statut == "ouvert"
    assert len(inventaire.photos) == 12
    assert [b.position for b in inventaire.bouteilles] == [1, 2, 3, 4, 5, 6]
    assert all(b.statut == "a_extraire" and b.quantite == 1 for b in inventaire.bouteilles)


def test_l_identifiant_stable_est_celui_des_photos(session, nom_maison, dossier_photos, stockage):
    """Même identifiant qu'en session 1 (decisions.md 0065), désormais en base."""
    cree = creer(session, nom_maison, dossier_photos, stockage)
    attendus = [vues.identifiant for vues in grouper_photos(dossier_photos).bouteilles]
    bouteilles = charger_inventaire(session, cree.inventaire_id).bouteilles
    assert [b.identifiant for b in bouteilles] == attendus


def test_chaque_bouteille_a_ses_photos_dans_l_ordre(session, nom_maison, dossier_photos, stockage):
    """Une bouteille = un groupe de photos (decisions.md 0166) : celles de son sous-dossier."""
    cree = creer(session, nom_maison, dossier_photos, stockage)
    bouteilles = charger_inventaire(session, cree.inventaire_id).bouteilles
    assert [[p.nom_origine for p in b.photos] for b in bouteilles] == [["1_etiquette.jpg", "2_contre.jpg"]] * 6
    assert [b.groupe.numero for b in bouteilles] == [1, 2, 3, 4, 5, 6]
    assert [p.rang for p in bouteilles[0].photos] == [1, 2]
    assert bouteilles[0].photos[0].prise_de_vue is not None  # gardée pour information


# --- photos sur disque, nommées par leur empreinte (decisions.md 0074) ---------------------


def test_les_photos_sont_copiees_et_nommees_par_leur_empreinte(session, nom_maison, dossier_photos, stockage):
    cree = creer(session, nom_maison, dossier_photos, stockage)
    for photo in charger_inventaire(session, cree.inventaire_id).photos:
        stockee = stockage / photo.chemin
        assert stockee.exists()
        assert photo.empreinte == hashlib.sha256(stockee.read_bytes()).hexdigest()
        assert photo.chemin == f"{photo.empreinte}.jpg"  # relatif au stockage


def test_l_inventaire_survit_au_deplacement_des_photos_d_origine(session, nom_maison, dossier_photos, stockage):
    """La base ne pointe jamais vers un fichier que l'utilisateur a pu déplacer."""
    cree = creer(session, nom_maison, dossier_photos, stockage)
    shutil.rmtree(dossier_photos)
    for photo in charger_inventaire(session, cree.inventaire_id).photos:
        assert (stockage / photo.chemin).exists()


def test_aucune_image_n_est_stockee_dans_la_base():
    """Structurel : aucune colonne binaire dans tout le schéma."""
    for table in Base.metadata.tables.values():
        for colonne in table.columns:
            assert not isinstance(colonne.type, LargeBinary), f"{table.name}.{colonne.name}"


def test_une_photo_partagee_par_deux_inventaires_n_est_stockee_qu_une_fois(session, nom_maison, dossier_photos, stockage):
    creer(session, nom_maison, dossier_photos, stockage)
    creer(session, nom_maison, dossier_photos, stockage)
    assert len(list(stockage.iterdir())) == 12
    assert compter(session, Photo) == 24  # chaque inventaire a ses enregistrements


# --- refus : rien n'est écrit ----------------------------------------------------------------


def test_la_meme_photo_deposee_deux_fois_est_detectee(session, nom_maison, dossier_photos, stockage):
    """Critère d'acceptation : par empreinte, quel que soit le nom du fichier."""
    shutil.copy(dossier_photos / "bouteille_02" / "1_etiquette.jpg", dossier_photos / "zz_copie_etiquette.jpg")
    shutil.copy(dossier_photos / "bouteille_03" / "2_contre.jpg", dossier_photos / "zz_copie_contre.jpg")
    with pytest.raises(PhotosInvalides, match="déposée deux fois") as capture:
        creer(session, nom_maison, dossier_photos, stockage)
    assert "1_etiquette.jpg et zz_copie_etiquette.jpg" in str(capture.value)
    assert compter(session, Inventaire) == 0
    assert list(stockage.iterdir()) == []


def test_trop_de_photos_pour_une_bouteille_refuse_sans_rien_ecrire(session, nom_maison, dossier_photos, stockage):
    """Chaque photo se paie : au-delà du plafond de la maison, on s'arrête AVANT
    tout appel (decisions.md 0159)."""
    from PIL import Image

    for rang in range(3):  # 2 + 3 = 5 photos, plafond 4
        Image.new("RGB", (8, 8), (rang, 200, 10)).save(dossier_photos / "bouteille_06" / f"{rang + 3}_vue.jpg")
    with pytest.raises(PhotosInvalides, match="plafond de 4 photos") as capture:
        creer(session, nom_maison, dossier_photos, stockage)
    assert "bouteille_06/ : 5 photos" in str(capture.value)
    assert compter(session, Inventaire) == 0
    assert compter(session, ConfigVersion) == 0
    assert compter(session, GroupePhotos) == 0
    assert list(stockage.iterdir()) == []


def test_une_photo_a_la_racine_est_une_bouteille_d_une_photo(session, nom_maison, dossier_photos, stockage):
    from PIL import Image

    Image.new("RGB", (8, 8), "navy").save(dossier_photos / "zz_seule.jpg")
    cree = creer(session, nom_maison, dossier_photos, stockage)
    derniere = charger_inventaire(session, cree.inventaire_id).bouteilles[-1]
    assert cree.nb_bouteilles == 7 and [p.nom_origine for p in derniere.photos] == ["zz_seule.jpg"]


def test_config_invalide_refusee_sans_rien_ecrire(session, nom_maison, dossier_photos, stockage, tmp_path):
    invalide = config_modifiee(tmp_path, lambda brut: brut.update(version="un"))
    with pytest.raises(ConfigInvalide):
        creer(session, nom_maison, dossier_photos, stockage, config=invalide)
    assert compter(session, Inventaire) == 0


def test_maison_differente_de_la_config_refusee(session, dossier_photos, stockage):
    with pytest.raises(ValueError, match="décrit"):
        creer(session, "Une autre maison", dossier_photos, stockage)


def test_limite_ne_garde_que_les_premieres_bouteilles(session, nom_maison, dossier_photos, stockage):
    cree = creer(session, nom_maison, dossier_photos, stockage, limite=2)
    assert cree.nb_bouteilles == 2
    assert len(charger_inventaire(session, cree.inventaire_id).photos) == 4


# --- config figée par inventaire (decisions.md 0073) ------------------------------------------


def test_meme_contenu_meme_version(session, nom_maison, dossier_photos, stockage):
    a = creer(session, nom_maison, dossier_photos, stockage)
    b = creer(session, nom_maison, dossier_photos, stockage)
    assert (a.config_numero, a.nouvelle_config) == (1, True)
    assert (b.config_numero, b.nouvelle_config) == (1, False)
    assert compter(session, ConfigVersion) == 1


def test_une_simple_remise_en_forme_ne_cree_pas_de_version(session, nom_maison, dossier_photos, stockage, tmp_path):
    creer(session, nom_maison, dossier_photos, stockage)
    reformatee = tmp_path / "maison_test.json"
    reformatee.write_text(
        json.dumps(json.loads(CONFIG_TEST.read_text(encoding="utf-8")), indent=4),
        encoding="utf-8",
    )
    assert creer(session, nom_maison, dossier_photos, stockage, config=reformatee).config_numero == 1


def test_modifier_le_json_ne_change_pas_la_config_d_un_inventaire_existant(session, nom_maison, dossier_photos, stockage, tmp_path):
    """Critère d'acceptation (côté config ; l'export est vérifié avec `exporter`)."""

    def renommer_une_valeur(brut):
        brut["version"] += 1
        couleur = next(c for c in brut["colonnes"] if c["type"] == "liste")
        couleur["valeurs"][0]["libelle"] = "Libellé modifié après coup"

    ancien = creer(session, nom_maison, dossier_photos, stockage)
    modifiee = config_modifiee(tmp_path, renommer_une_valeur)
    nouveau = creer(session, nom_maison, dossier_photos, stockage, config=modifiee)

    assert (nouveau.config_numero, nouveau.nouvelle_config) == (2, True)
    assert not any("pensez à incrémenter" in a for a in nouveau.avertissements)
    figee = config_figee(charger_inventaire(session, ancien.inventaire_id))
    liste = next(c for c in figee.colonnes if c.type == "liste")
    assert liste.valeurs[0].libelle != "Libellé modifié après coup"
    assert "Libellé modifié après coup" in [
        v.libelle for c in config_figee(charger_inventaire(session, nouveau.inventaire_id)).colonnes for v in c.valeurs
    ]


def test_contenu_change_sans_incrementer_la_version_avertit(session, nom_maison, dossier_photos, stockage, tmp_path):
    creer(session, nom_maison, dossier_photos, stockage)
    modifiee = config_modifiee(
        tmp_path, lambda brut: brut["colonnes"][2].update(nom="En-tête modifié")
    )
    cree = creer(session, nom_maison, dossier_photos, stockage, config=modifiee)
    assert cree.config_numero == 2
    assert any("pensez à incrémenter" in a for a in cree.avertissements)


def test_la_config_figee_garde_le_texte_exact(session, nom_maison, dossier_photos, stockage):
    cree = creer(session, nom_maison, dossier_photos, stockage)
    version = charger_inventaire(session, cree.inventaire_id).config_version
    assert version.contenu == CONFIG_TEST.read_text(encoding="utf-8")
    assert version.fichier_source == CONFIG_TEST.name
    assert inspect(version).persistent
