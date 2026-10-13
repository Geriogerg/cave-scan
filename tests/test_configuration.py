"""Configuration d'une maison par la page ou par import (decisions.md 0161) :
chaque enregistrement est validé comme un fichier et devient une NOUVELLE
version ; un inventaire garde celle de sa création."""

from __future__ import annotations

import json
import shutil

import pytest
from sqlalchemy import func, select

from src.config.maison import ConfigInvalide, charger_config
from src.donnees.modeles import ConfigVersion
from src.services.configuration import (
    ConfigInchangee,
    ConfigModifieeAilleurs,
    apercu_modele,
    config_active,
    enregistrer_version,
    exporter_version,
    importer,
    versions_de,
)
from src.services.depot import creer_brouillon
from src.services.inventaires import charger_inventaire, config_figee
from tests.conftest import CONFIG_TEST


@pytest.fixture
def dossier(tmp_path):
    """Un dossier de configs à part : la vraie config de test n'est jamais réécrite."""
    configs = tmp_path / "configs"
    configs.mkdir()
    shutil.copy(CONFIG_TEST, configs / CONFIG_TEST.name)
    return configs


@pytest.fixture
def maison(dossier):
    return charger_config(dossier / CONFIG_TEST.name).maison


def nombre_de_versions(session) -> int:
    return session.scalar(select(func.count()).select_from(ConfigVersion))


def test_un_enregistrement_cree_une_nouvelle_version_du_fichier(session, dossier, maison):
    active = config_active(dossier, maison)
    brut = active.brut
    brut["colonnes"][1]["nom"] = "Quantité"  # en-tête renommé dans la page
    enregistree = enregistrer_version(session, dossier, maison, brut, version_vue=active.config.version)

    assert enregistree.version == active.config.version + 1 and not enregistree.nouvelle_maison
    relue = charger_config(dossier / CONFIG_TEST.name)  # le fichier EST la config active
    assert relue.version == enregistree.version and relue.colonnes[1].nom == "Quantité"
    assert [v.numero for v in versions_de(session, maison)] == [enregistree.numero]
    assert versions_de(session, maison)[0].contenu == (dossier / CONFIG_TEST.name).read_text(encoding="utf-8")


def test_un_inventaire_garde_la_version_de_sa_creation(session, dossier, maison):
    inventaire_id = creer_brouillon(session, maison, dossier / CONFIG_TEST.name, "Vente").inventaire_id
    avant = config_figee(charger_inventaire(session, inventaire_id))
    brut = config_active(dossier, maison).brut
    brut["colonnes"] = [c for c in brut["colonnes"] if c["cle"] != "estimation"]
    enregistrer_version(session, dossier, maison, brut)

    figee = config_figee(charger_inventaire(session, inventaire_id))
    assert figee.version == avant.version and figee.colonne("estimation") is not None
    assert charger_config(dossier / CONFIG_TEST.name).colonne("estimation") is None


def test_une_config_invalide_n_ecrit_rien_et_dit_chaque_erreur(session, dossier, maison):
    fichier = dossier / CONFIG_TEST.name
    avant = fichier.read_text(encoding="utf-8")
    brut = config_active(dossier, maison).brut
    brut["colonnes"][2]["type"] = "date"  # type inconnu
    brut["colonnes"].append({"cle": "Lot", "nom": "Lot", "type": "texte", "source": "expert"})  # clé invalide
    with pytest.raises(ConfigInvalide) as refus:
        enregistrer_version(session, dossier, maison, brut)
    assert len(refus.value.erreurs) == 2
    assert any("type 'date' inconnu" in e for e in refus.value.erreurs)
    assert fichier.read_text(encoding="utf-8") == avant and nombre_de_versions(session) == 0


def test_une_config_modifiee_ailleurs_n_est_pas_ecrasee(session, dossier, maison):
    ouverte = config_active(dossier, maison)
    autre = ouverte.brut
    autre["colonnes"][1]["nom"] = "Qté (autre onglet)"
    enregistrer_version(session, dossier, maison, autre, version_vue=ouverte.config.version)
    mienne = ouverte.brut
    mienne["colonnes"][1]["nom"] = "Qté (mon onglet)"
    with pytest.raises(ConfigModifieeAilleurs, match="modifiée ailleurs"):
        enregistrer_version(session, dossier, maison, mienne, version_vue=ouverte.config.version)
    assert charger_config(dossier / CONFIG_TEST.name).colonnes[1].nom == "Qté (autre onglet)"


def test_rien_de_change_rien_d_enregistre(session, dossier, maison):
    with pytest.raises(ConfigInchangee):
        enregistrer_version(session, dossier, maison, config_active(dossier, maison).brut)
    assert nombre_de_versions(session) == 0


def test_la_page_ne_renomme_pas_la_maison(session, dossier, maison):
    brut = config_active(dossier, maison).brut
    brut["maison"] = "Une autre maison"
    with pytest.raises(ConfigInvalide, match="ne modifie que la configuration"):
        enregistrer_version(session, dossier, maison, brut)


def test_importer_une_nouvelle_maison_cree_son_fichier(session, dossier):
    brut = json.loads(CONFIG_TEST.read_text(encoding="utf-8"))
    brut["maison"] = "Cave Dupont & Fils"
    brut["version"] = 3
    enregistree = importer(session, dossier, json.dumps(brut, ensure_ascii=False), "dupont.json")
    assert enregistree.nouvelle_maison and enregistree.fichier.name == "cave_dupont_fils.json"
    assert enregistree.version == 3  # une nouvelle maison garde son numéro
    assert config_active(dossier, "Cave Dupont & Fils").config.version == 3


def test_importer_pour_une_maison_connue_numerote_la_suite(session, dossier, maison):
    actuelle = config_active(dossier, maison).config.version
    brut = config_active(dossier, maison).brut
    brut["version"] = 1  # numéro périmé dans le fichier apporté
    brut["colonnes"][1]["nom"] = "Nombre"
    enregistree = importer(session, dossier, json.dumps(brut, ensure_ascii=False), "export.json")
    assert enregistree.version == actuelle + 1 and enregistree.fichier.name == CONFIG_TEST.name
    assert any(f"fixé à {actuelle + 1}" in a for a in enregistree.avertissements)


def test_importer_un_json_illisible_dit_ou(session, dossier):
    with pytest.raises(ConfigInvalide, match=r"JSON illisible.*\(ligne 1"):
        importer(session, dossier, '{"maison": ', "abime.json")


def test_exporter_la_version_active_ou_une_ancienne(session, dossier, maison):
    premiere = config_active(dossier, maison)
    brut = premiere.brut
    brut["colonnes"][1]["nom"] = "Quantité"
    enregistrer_version(session, dossier, maison, brut)
    brut["colonnes"][1]["nom"] = "Nombre"
    deuxieme = enregistrer_version(session, dossier, maison, brut)

    nom, texte = exporter_version(session, dossier, maison)
    assert nom == CONFIG_TEST.name and json.loads(texte)["colonnes"][1]["nom"] == "Nombre"
    nom, texte = exporter_version(session, dossier, maison, deuxieme.numero - 1)
    assert nom.endswith(f"_version_{deuxieme.numero - 1}.json") and json.loads(texte)["colonnes"][1]["nom"] == "Quantité"
    with pytest.raises(LookupError):
        exporter_version(session, dossier, maison, 99)


def test_l_apercu_montre_exactement_ce_que_recoit_le_modele(dossier, maison):
    config = config_active(dossier, maison).config
    niveau = json.loads(apercu_modele(config.colonne("niveau")))
    assert niveau["enum"][-1] == "non_determinable"
    assert "Seulement si une photo montre" in niveau["description"]  # la règle de la maison
    assert "Ne jamais deviner" in niveau["description"]  # la consigne ajoutée par l'outil
    # Colonnes expert et système : jamais envoyées au modèle (CLAUDE.md, contrainte 3).
    for cle in ("estimation", "caisse", "numero_lot", "quantite", "id", "a_verifier"):
        assert apercu_modele(config.colonne(cle)) is None, cle


def test_un_exemple_de_reponse_est_signale_a_l_enregistrement(session, dossier, maison):
    brut = config_active(dossier, maison).brut
    colonne = next(c for c in brut["colonnes"] if c["cle"] == "description_etat")
    colonne["description"] += " Par exemple « Étiquette tachée »."
    enregistree = enregistrer_version(session, dossier, maison, brut)
    nom = next(c for c in brut["colonnes"] if c["cle"] == "description_etat")["nom"]
    assert any("few-shot" in a and f"« {nom} »" in a for a in enregistree.avertissements)


def test_la_config_de_test_n_a_plus_d_exemple_de_reponse():
    """L'exemple de la description d'état était du few-shot (CLAUDE.md, contrainte 7)."""
    assert charger_config(CONFIG_TEST).avertissements == ()


def test_le_plafond_de_photos_est_borne(session, dossier, maison):
    for refuse in (0, 11, "4", True):
        brut = config_active(dossier, maison).brut
        brut["photos_max_par_bouteille"] = refuse
        with pytest.raises(ConfigInvalide, match="photos_max_par_bouteille"):
            enregistrer_version(session, dossier, maison, brut)
    brut = config_active(dossier, maison).brut
    del brut["photos_max_par_bouteille"]
    enregistrer_version(session, dossier, maison, brut)
    assert charger_config(dossier / CONFIG_TEST.name).photos_max_par_bouteille == 4  # par défaut
