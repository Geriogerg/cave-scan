"""Dépôt des photos, bouteille par bouteille (decisions.md 0126-0134, 0166, 0167) —
critères des guides de sessions 4 et 6 vérifiés sur les fonctions de service."""

from __future__ import annotations

import io
import threading

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.maison import charger_config
from src.donnees.modeles import FicheBouteille, GroupePhotos, Photo
from src.donnees.stockage import chemin_stocke
from src.io.photos import identifiant_de
from src.services.depot import (
    DepotFerme,
    ModificationRefusee,
    ajouter_photo,
    apercu,
    couper,
    creer_brouillon,
    definir_quantite,
    finaliser,
    rattacher,
    signatures_deja_recues,
    supprimer_groupe,
    supprimer_photo,
)
from src.services.envoi import EnvoiRefuse
from src.services.file_attente import reserver_bouteille
from src.services.inventaires import charger_inventaire
from src.services.pilotage import LancementRefuse, lancer
from tests.conftest import CONFIG_TEST


def jpeg(couleur: int, date: str | None = None) -> bytes:
    """Une petite photo distincte par couleur, avec ou sans date EXIF."""
    image = Image.new("RGB", (32, 24), ((couleur * 37) % 256, (couleur * 91) % 256, (couleur * 53) % 256))
    sortie = io.BytesIO()
    if date:
        exif = Image.Exif()
        exif[0x0132] = date
        image.save(sortie, "JPEG", exif=exif.tobytes())
    else:
        image.save(sortie, "JPEG")
    return sortie.getvalue()


@pytest.fixture
def brouillon(session, nom_maison):
    return creer_brouillon(session, nom_maison, CONFIG_TEST, "Vente de printemps").inventaire_id


def envoyer(session, inventaire_id, stockage, contenu, nom="image.jpg", bouteille="b1", numero=1, quantite=None, signature=None):
    return ajouter_photo(
        session, inventaire_id, io.BytesIO(contenu), nom, stockage,
        bouteille=bouteille, numero=numero, quantite=quantite, signature=signature,
    )


def bouteilles(session, inventaire_id):
    """Les bouteilles en attente : les noms de leurs photos, dans l'ordre."""
    return [[p.nom_origine for p in b.photos] for b in apercu(session, inventaire_id).bouteilles]


# --- créer, recevoir -----------------------------------------------------------------------------


def test_un_brouillon_n_a_ni_bouteille_ni_extraction(session, brouillon):
    inventaire = charger_inventaire(session, brouillon)
    assert (inventaire.statut, inventaire.extraction, inventaire.bouteilles) == ("brouillon", "non_lancee", [])
    assert inventaire.config_version.numero == 1  # config figée dès la création


def test_chaque_photo_va_a_sa_bouteille(session, brouillon, stockage):
    """Mode appareil photo : la bouteille en cours, puis « Bouteille suivante »."""
    envoyer(session, brouillon, stockage, jpeg(1), "etiquette.jpg", "b1", 1)
    envoyer(session, brouillon, stockage, jpeg(2), "contre.jpg", "b1", 1)
    envoyer(session, brouillon, stockage, jpeg(3), "capsule.jpg", "b1", 1)
    envoyer(session, brouillon, stockage, jpeg(4), "etiquette.jpg", "b2", 2)
    assert bouteilles(session, brouillon) == [["etiquette.jpg", "contre.jpg", "capsule.jpg"], ["etiquette.jpg"]]
    assert [p.rang for p in apercu(session, brouillon).bouteilles[0].photos] == [1, 2, 3]


def test_l_ordre_des_bouteilles_est_celui_de_la_prise_de_vue_pas_de_l_arrivee(session, brouillon, stockage):
    """Sur un réseau qui coupe, la photo de la bouteille 3 peut arriver avant
    celle de la bouteille 2 : le numéro donné par l'appareil fait foi."""
    envoyer(session, brouillon, stockage, jpeg(1), "un.jpg", "b1", 1)
    envoyer(session, brouillon, stockage, jpeg(3), "trois.jpg", "b3", 3)
    envoyer(session, brouillon, stockage, jpeg(2), "deux.jpg", "b2", 2)
    assert bouteilles(session, brouillon) == [["un.jpg"], ["deux.jpg"], ["trois.jpg"]]
    assert apercu(session, brouillon).prochain_numero == 4


def test_une_photo_renvoyee_deux_fois_n_est_enregistree_qu_une_fois(session, brouillon, stockage):
    premiere = envoyer(session, brouillon, stockage, jpeg(1), "IMG_1.jpg")
    meme_contenu = envoyer(session, brouillon, stockage, jpeg(1), "copie.jpg", "b2", 2)
    assert not premiere.deja_recue and meme_contenu.deja_recue
    assert meme_contenu.photo_id == premiere.photo_id and meme_contenu.numero == 1  # elle reste dans sa bouteille
    assert apercu(session, brouillon).nb_photos == 1


def test_le_meme_fichier_d_origine_n_est_pas_renvoye(session, brouillon, stockage):
    """Après une coupure, le navigateur demande ce qui est déjà arrivé ; et même
    renvoyé (réduit autrement, donc d'un autre contenu), il n'est pas ajouté."""
    envoyer(session, brouillon, stockage, jpeg(1), signature="IMG_1.jpg|4031|1726581413000")
    assert signatures_deja_recues(session, brouillon, ["IMG_1.jpg|4031|1726581413000", "IMG_2.jpg|1|2"]) == [
        "IMG_1.jpg|4031|1726581413000"
    ]
    renvoi = envoyer(session, brouillon, stockage, jpeg(99), signature="IMG_1.jpg|4031|1726581413000")
    assert renvoi.deja_recue and apercu(session, brouillon).nb_photos == 1


def test_la_quantite_se_saisit_a_la_capture(session, brouillon, stockage):
    """« × N » : 12 bouteilles identiques photographiées une fois."""
    envoyer(session, brouillon, stockage, jpeg(1), bouteille="b1", quantite=12)
    assert apercu(session, brouillon).bouteilles[0].groupe.quantite == 12
    definir_quantite(session, brouillon, "b1", 6)  # corrigée avant la photo suivante
    envoyer(session, brouillon, stockage, jpeg(2), bouteille="b1")
    assert apercu(session, brouillon).bouteilles[0].groupe.quantite == 6
    with pytest.raises(EnvoiRefuse, match="Quantité invalide"):
        definir_quantite(session, brouillon, "b1", 0)


def test_le_plafond_de_photos_de_la_maison_est_tenu(session, brouillon, stockage):
    plafond = charger_config(CONFIG_TEST).photos_max_par_bouteille
    for rang in range(plafond):
        envoyer(session, brouillon, stockage, jpeg(rang), f"{rang}.jpg")
    with pytest.raises(EnvoiRefuse, match=f"Bouteille n°1 : {plafond} photos au plus"):
        envoyer(session, brouillon, stockage, jpeg(50), "de_trop.jpg")
    assert len(bouteilles(session, brouillon)[0]) == plafond


@pytest.mark.parametrize(
    "contenu, nom, raison",
    [
        (b"ceci n'est pas une photo", "note.jpg", "n'est pas une image lisible"),
        (b"\x00\x00\x00\x18ftypheic", "IMG_0001.HEIC", "n'est pas une image lisible"),
    ],
)
def test_un_fichier_non_image_ou_heic_illisible_est_refuse_avec_sa_raison(session, brouillon, stockage, contenu, nom, raison):
    with pytest.raises(EnvoiRefuse, match=raison):
        envoyer(session, brouillon, stockage, contenu, nom)
    assert apercu(session, brouillon).bouteilles == []


@pytest.mark.parametrize("cle", ["", "a b", "x" * 65, "<script>"])
def test_une_cle_de_bouteille_invalide_est_refusee(session, brouillon, stockage, cle):
    with pytest.raises(EnvoiRefuse, match="Bouteille non reconnue"):
        envoyer(session, brouillon, stockage, jpeg(1), bouteille=cle)


def test_une_miniature_sans_metadonnees_est_preparee_a_la_reception(session, brouillon, stockage):
    recue = envoyer(session, brouillon, stockage, jpeg(1, "2026:09:17 15:56:53"), "x.jpg")
    photo = session.get(Photo, recue.photo_id)
    miniature = stockage / "miniatures" / f"{photo.empreinte}.jpg"
    assert miniature.exists()
    assert dict(Image.open(miniature).getexif()) == {}


def test_des_envois_simultanes_recoivent_des_places_distinctes(session, brouillon, stockage):
    moteur = session.get_bind()
    erreurs = []

    def envoi(couleur):
        try:
            with Session(moteur, expire_on_commit=False) as propre:
                envoyer(propre, brouillon, stockage, jpeg(couleur), f"p{couleur:02d}.jpg", f"b{couleur % 2}", couleur % 2 + 1)
        except Exception as erreur:  # pragma: no cover — remonté ci-dessous
            erreurs.append(erreur)

    threads = [threading.Thread(target=envoi, args=(couleur,)) for couleur in range(1, 9)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert erreurs == []
    vue = apercu(session, brouillon)
    assert sorted(p.ordre for b in vue.bouteilles for p in b.photos) == list(range(1, 9))
    for bouteille in vue.bouteilles:
        assert [p.rang for p in bouteille.photos] == [1, 2, 3, 4]
    assert session.scalar(select(func.count()).select_from(GroupePhotos)) == 2


# --- corriger les bouteilles en attente --------------------------------------------------------


@pytest.fixture
def trois(session, brouillon, stockage):
    """Bouteille 1 : A B C (la photo C appartient en fait à la suivante) ; bouteille 2 : D."""
    for rang, nom in enumerate("ABC", start=1):
        envoyer(session, brouillon, stockage, jpeg(rang), f"{nom}.jpg", "b1", 1)
    envoyer(session, brouillon, stockage, jpeg(4), "D.jpg", "b2", 2)
    return brouillon


def photo_nommee(session, inventaire_id, nom):
    return next(p for b in apercu(session, inventaire_id).bouteilles for p in b.photos if p.nom_origine == nom)


def test_couper_une_bouteille_en_deux(session, trois):
    """« Bouteille suivante » oublié : C et les suivantes forment une autre bouteille."""
    couper(session, trois, photo_nommee(session, trois, "C.jpg").id)
    assert bouteilles(session, trois) == [["A.jpg", "B.jpg"], ["C.jpg"], ["D.jpg"]]
    assert [b.numero for b in apercu(session, trois).bouteilles] == [1, 2, 3]


def test_rattacher_a_la_bouteille_precedente(session, trois):
    """« Bouteille suivante » appuyé trop tôt : D revient avec A B C."""
    groupe_d = apercu(session, trois).bouteilles[1].groupe.id
    rattacher(session, trois, groupe_d)
    assert bouteilles(session, trois) == [["A.jpg", "B.jpg", "C.jpg", "D.jpg"]]


def test_rattacher_respecte_le_plafond(session, trois, stockage):
    envoyer(session, trois, stockage, jpeg(5), "E.jpg", "b2", 2)
    groupe = apercu(session, trois).bouteilles[1].groupe.id
    with pytest.raises(ModificationRefusee, match="5 photos : 4 au plus"):
        rattacher(session, trois, groupe)
    assert bouteilles(session, trois) == [["A.jpg", "B.jpg", "C.jpg"], ["D.jpg", "E.jpg"]]


def test_retirer_une_photo(session, trois):
    supprimer_photo(session, trois, photo_nommee(session, trois, "B.jpg").id)
    assert bouteilles(session, trois) == [["A.jpg", "C.jpg"], ["D.jpg"]]
    assert [p.rang for p in apercu(session, trois).bouteilles[0].photos] == [1, 2]
    supprimer_photo(session, trois, photo_nommee(session, trois, "D.jpg").id)  # sa dernière photo
    assert bouteilles(session, trois) == [["A.jpg", "C.jpg"]]  # la bouteille vide disparaît


def test_supprimer_une_bouteille_en_attente(session, trois):
    supprimer_groupe(session, trois, apercu(session, trois).bouteilles[0].groupe.id)
    assert bouteilles(session, trois) == [["D.jpg"]]


@pytest.mark.parametrize(
    "action, raison",
    [
        (lambda s, i: couper(s, i, photo_nommee(s, i, "A.jpg").id), "déjà la première photo"),
        (lambda s, i: rattacher(s, i, apercu(s, i).bouteilles[0].groupe.id), "première bouteille en attente"),
        (lambda s, i: rattacher(s, i, 9999), "n'existe pas"),
    ],
    ids=["couper-a-la-premiere", "rattacher-la-premiere", "bouteille-inexistante"],
)
def test_une_correction_impossible_est_refusee(session, trois, action, raison):
    with pytest.raises(ModificationRefusee, match=raison):
        action(session, trois)
    assert bouteilles(session, trois) == [["A.jpg", "B.jpg", "C.jpg"], ["D.jpg"]]


# --- lancer, puis ajouter des bouteilles ------------------------------------------------------


def test_lancement_refuse_sans_photo(session, brouillon, stockage):
    with pytest.raises(LancementRefuse, match="Aucune bouteille en attente"):
        finaliser(session, brouillon, stockage)


def test_finaliser_forme_les_bouteilles_et_lance(session, trois, stockage):
    definir_quantite(session, trois, "b2", 3)
    assert finaliser(session, trois, stockage) == 2

    inventaire = charger_inventaire(session, trois)
    assert (inventaire.statut, inventaire.extraction) == ("ouvert", "lancee")
    formees = inventaire.bouteilles
    assert [[p.nom_origine for p in b.photos] for b in formees] == [["A.jpg", "B.jpg", "C.jpg"], ["D.jpg"]]
    assert [b.quantite for b in formees] == [1, 3]  # la quantité saisie à la capture
    # Même identifiant qu'en ligne de commande pour les mêmes photos.
    attendu = identifiant_de([chemin_stocke(stockage, p.chemin) for p in formees[0].photos])
    assert formees[0].identifiant == attendu
    assert reserver_bouteille(session, "worker") == formees[0].id  # le worker la voit
    assert apercu(session, trois).bouteilles == []


def test_les_photos_d_une_bouteille_formee_ne_bougent_plus(session, trois, stockage):
    premiere = photo_nommee(session, trois, "A.jpg").id
    finaliser(session, trois, stockage)
    groupe = charger_inventaire(session, trois).bouteilles[0].groupe_id
    for action, raison in (
        (lambda: envoyer(session, trois, stockage, jpeg(42), "tard.jpg", "b1", 1), "déjà analysée"),
        (lambda: supprimer_photo(session, trois, premiere), "déjà analysée"),
        (lambda: couper(session, trois, premiere), "déjà analysée"),
        (lambda: supprimer_groupe(session, trois, groupe), "déjà analysée"),
        (lambda: definir_quantite(session, trois, "b1", 4), "déjà analysée"),
    ):
        with pytest.raises(DepotFerme, match=raison):
            action()
    assert len(charger_inventaire(session, trois).bouteilles[0].photos) == 3
    with pytest.raises(LancementRefuse, match="Aucune bouteille en attente"):
        finaliser(session, trois, stockage)


def test_ajouter_des_bouteilles_apres_le_lancement(session, trois, stockage):
    """Elles prennent place à la fin et partent à l'analyse (decisions.md 0167)."""
    finaliser(session, trois, stockage)
    vue = apercu(session, trois)
    assert vue.prochain_numero == 3 and vue.deja_formees == 2
    envoyer(session, trois, stockage, jpeg(7), "E.jpg", "b3", vue.prochain_numero)
    assert apercu(session, trois).bouteilles[0].numero == 3  # sa future position
    assert finaliser(session, trois, stockage) == 1
    formees = charger_inventaire(session, trois).bouteilles
    assert [b.position for b in formees] == [1, 2, 3]
    assert formees[2].statut == "a_extraire" and charger_inventaire(session, trois).extraction == "lancee"


def test_lancer_un_brouillon_sans_le_finaliser_est_refuse(session, trois):
    with pytest.raises(LancementRefuse, match="brouillon"):
        lancer(session, trois)


def test_creer_un_brouillon_demande_un_nom_et_la_bonne_maison(session, nom_maison):
    with pytest.raises(EnvoiRefuse, match="Donnez un nom à la vente"):
        creer_brouillon(session, nom_maison, CONFIG_TEST, "  ")
    with pytest.raises(EnvoiRefuse, match="décrit"):
        creer_brouillon(session, "Autre maison", CONFIG_TEST, "Vente")
    assert charger_config(CONFIG_TEST).maison == nom_maison
    assert session.scalar(select(func.count()).select_from(FicheBouteille)) == 0
