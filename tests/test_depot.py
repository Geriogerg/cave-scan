"""Dépôt des photos dans un brouillon (decisions.md 0126-0134) — critères du
guide de session 4 vérifiés sur les fonctions de service."""

from __future__ import annotations

import io
import threading
from datetime import datetime

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from src.config.maison import charger_config
from src.donnees.modeles import FicheBouteille, Photo
from src.donnees.stockage import chemin_stocke
from src.io.photos import PhotosBouteille
from src.services.depot import (
    DepotFerme,
    ModificationRefusee,
    ajouter_photo,
    apercu,
    creer_brouillon,
    deplacer_photo,
    finaliser,
    inverser_paire,
    retrier,
    signatures_deja_recues,
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


def envoyer(session, inventaire_id, stockage, contenu, nom="image.jpg", date=None, signature=None):
    return ajouter_photo(session, inventaire_id, io.BytesIO(contenu), nom, stockage, prise_de_vue=date, signature=signature)


def noms(session, inventaire_id):
    return [p.nom_origine for p in apercu(session, inventaire_id).photos]


def d(minute: int) -> datetime:
    return datetime(2026, 9, 17, 15, minute, 0)


# --- créer, recevoir -----------------------------------------------------------------------------


def test_un_brouillon_n_a_ni_bouteille_ni_extraction(session, brouillon):
    inventaire = charger_inventaire(session, brouillon)
    assert (inventaire.statut, inventaire.extraction, inventaire.bouteilles) == ("brouillon", "non_lancee", [])
    assert inventaire.config_version.numero == 1  # config figée dès la création


def test_une_photo_renvoyee_deux_fois_n_est_enregistree_qu_une_fois(session, brouillon, stockage):
    premiere = envoyer(session, brouillon, stockage, jpeg(1), "IMG_1.jpg")
    meme_contenu = envoyer(session, brouillon, stockage, jpeg(1), "copie.jpg")
    assert not premiere.deja_recue and meme_contenu.deja_recue
    assert meme_contenu.photo_id == premiere.photo_id
    assert len(apercu(session, brouillon).photos) == 1


def test_le_meme_fichier_d_origine_n_est_pas_renvoye(session, brouillon, stockage):
    """Après une coupure, le navigateur demande ce qui est déjà arrivé ; et même
    renvoyé (réduit autrement, donc d'un autre contenu), il n'est pas ajouté."""
    envoyer(session, brouillon, stockage, jpeg(1), signature="IMG_1.jpg|4031|1726581413000")
    assert signatures_deja_recues(session, brouillon, ["IMG_1.jpg|4031|1726581413000", "IMG_2.jpg|1|2"]) == [
        "IMG_1.jpg|4031|1726581413000"
    ]
    renvoi = envoyer(session, brouillon, stockage, jpeg(99), signature="IMG_1.jpg|4031|1726581413000")
    assert renvoi.deja_recue and len(apercu(session, brouillon).photos) == 1


def test_le_tri_suit_la_date_fournie_puis_le_nom_puis_l_arrivee(session, brouillon, stockage):
    """Envoyées dans le désordre, comme une sélection de galerie ; iPhone : tous
    les fichiers peuvent s'appeler « image.jpg »."""
    envoyer(session, brouillon, stockage, jpeg(1), "b.jpg", d(3))
    envoyer(session, brouillon, stockage, jpeg(2), "image.jpg", d(2))  # arrivée 2
    envoyer(session, brouillon, stockage, jpeg(3), "a.jpg", d(3))  # même date que b : le nom tranche
    envoyer(session, brouillon, stockage, jpeg(4), "z.jpg", d(1))
    envoyer(session, brouillon, stockage, jpeg(5), "image.jpg", d(2))  # même date, même nom : l'arrivée tranche
    ordre = [(p.nom_origine, p.prise_de_vue.minute) for p in apercu(session, brouillon).photos]
    assert ordre == [("z.jpg", 1), ("image.jpg", 2), ("image.jpg", 2), ("a.jpg", 3), ("b.jpg", 3)]
    jumelles = apercu(session, brouillon).photos[1:3]
    assert jumelles[0].id < jumelles[1].id  # les deux « image.jpg » : dans l'ordre d'arrivée
    assert apercu(session, brouillon).tri == "date de prise de vue"


def test_la_date_vient_du_fichier_si_le_navigateur_ne_l_a_pas_fournie(session, brouillon, stockage):
    envoyer(session, brouillon, stockage, jpeg(1, "2026:09:17 15:56:54"), "x.jpg")
    envoyer(session, brouillon, stockage, jpeg(2, "2026:09:17 15:56:53"), "y.jpg")
    assert noms(session, brouillon) == ["y.jpg", "x.jpg"]


def test_la_date_fournie_prime_sur_un_fichier_sans_exif(session, brouillon, stockage):
    """Le cas de la réduction dans le navigateur : le fichier n'a plus d'EXIF, la
    date lue avant réduction arrive à côté (decisions.md 0129)."""
    envoyer(session, brouillon, stockage, jpeg(1), "IMG_0002.jpg", d(1))
    envoyer(session, brouillon, stockage, jpeg(2), "IMG_0001.jpg", d(2))
    assert noms(session, brouillon) == ["IMG_0002.jpg", "IMG_0001.jpg"]


def test_une_seule_photo_sans_date_fait_trier_toutes_par_nom(session, brouillon, stockage):
    envoyer(session, brouillon, stockage, jpeg(1), "photo 10.jpg", d(1))
    envoyer(session, brouillon, stockage, jpeg(2), "photo 2.jpg")
    vue = apercu(session, brouillon)
    assert noms(session, brouillon) == ["photo 2.jpg", "photo 10.jpg"]
    assert vue.tri == "nom de fichier"
    assert any("sans date de prise de vue" in a for a in vue.anomalies)


@pytest.mark.parametrize(
    "contenu, nom, raison",
    [
        (b"ceci n'est pas une photo", "note.jpg", "n'est pas une image lisible"),
        (b"\x00\x00\x00\x18ftypheic", "IMG_0001.HEIC", "HEIC"),
    ],
)
def test_un_fichier_non_image_ou_heic_est_refuse_avec_sa_raison(session, brouillon, stockage, contenu, nom, raison):
    with pytest.raises(EnvoiRefuse, match=raison):
        envoyer(session, brouillon, stockage, contenu, nom)
    assert apercu(session, brouillon).photos == []


def test_une_miniature_sans_metadonnees_est_preparee_a_la_reception(session, brouillon, stockage):
    recue = envoyer(session, brouillon, stockage, jpeg(1, "2026:09:17 15:56:53"), "x.jpg")
    photo = session.get(Photo, recue.photo_id)
    miniature = stockage / "miniatures" / f"{photo.empreinte}.jpg"
    assert miniature.exists()
    assert dict(Image.open(miniature).getexif()) == {}


def test_des_envois_simultanes_recoivent_des_positions_distinctes(session, brouillon, stockage):
    moteur = session.get_bind()
    erreurs = []

    def envoi(couleur):
        try:
            with Session(moteur, expire_on_commit=False) as propre:
                envoyer(propre, brouillon, stockage, jpeg(couleur), f"p{couleur:02d}.jpg", d(couleur))
        except Exception as erreur:  # pragma: no cover — remonté ci-dessous
            erreurs.append(erreur)

    threads = [threading.Thread(target=envoi, args=(couleur,)) for couleur in range(1, 9)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert erreurs == []
    photos = apercu(session, brouillon).photos
    assert [p.ordre for p in photos] == list(range(1, 9))
    assert [p.nom_origine for p in photos] == [f"p{n:02d}.jpg" for n in range(1, 9)]


# --- corriger l'ordre -------------------------------------------------------------------------


@pytest.fixture
def quatre(session, brouillon, stockage):
    """Quatre photos datées : A B | C D."""
    for rang, nom in enumerate("ABCD", start=1):
        envoyer(session, brouillon, stockage, jpeg(rang), f"{nom}.jpg", d(rang))
    return brouillon


def paires(session, inventaire_id):
    return [
        (p.etiquette.nom_origine, p.contre_etiquette.nom_origine if p.contre_etiquette else None)
        for p in apercu(session, inventaire_id).paires
    ]


def test_inverser_une_paire(session, quatre):
    inverser_paire(session, quatre, 2)
    assert paires(session, quatre) == [("A.jpg", "B.jpg"), ("D.jpg", "C.jpg")]


def test_deplacer_une_photo(session, quatre):
    d_id = apercu(session, quatre).photos[3].id
    deplacer_photo(session, quatre, d_id, 1)
    assert paires(session, quatre) == [("D.jpg", "A.jpg"), ("B.jpg", "C.jpg")]


def test_supprimer_une_photo_decale_les_suivantes(session, quatre):
    supprimer_photo(session, quatre, apercu(session, quatre).photos[0].id)
    assert paires(session, quatre) == [("B.jpg", "C.jpg"), ("D.jpg", None)]
    vue = apercu(session, quatre)
    assert not vue.peut_lancer and any("Nombre impair de photos (3)" in a for a in vue.anomalies)


def test_une_photo_ajoutee_apres_une_correction_va_a_la_fin_puis_retrier(session, quatre, stockage):
    inverser_paire(session, quatre, 1)
    envoyer(session, quatre, stockage, jpeg(9), "Z0.jpg", d(0))  # la plus ancienne…
    assert noms(session, quatre)[-1] == "Z0.jpg"  # … mais à la fin : l'ordre corrigé est gardé
    assert apercu(session, quatre).tri == "ordre corrigé à la main"
    retrier(session, quatre)
    assert noms(session, quatre) == ["Z0.jpg", "A.jpg", "B.jpg", "C.jpg", "D.jpg"]


@pytest.mark.parametrize(
    "action",
    [
        lambda s, i: deplacer_photo(s, i, apercu(s, i).photos[0].id, 9),
        lambda s, i: inverser_paire(s, i, 3),
    ],
    ids=["position-hors-liste", "paire-inexistante"],
)
def test_une_correction_impossible_est_refusee(session, quatre, action):
    with pytest.raises(ModificationRefusee):
        action(session, quatre)
    assert noms(session, quatre) == ["A.jpg", "B.jpg", "C.jpg", "D.jpg"]


# --- finaliser -------------------------------------------------------------------------------


def test_lancement_refuse_si_le_nombre_de_photos_est_impair(session, quatre, stockage):
    supprimer_photo(session, quatre, apercu(session, quatre).photos[3].id)
    with pytest.raises(LancementRefuse, match=r"Nombre impair de photos \(3\).*Supprimez la photo en trop"):
        finaliser(session, quatre, stockage)
    assert charger_inventaire(session, quatre).statut == "brouillon"


def test_lancement_refuse_sans_photo(session, brouillon, stockage):
    with pytest.raises(LancementRefuse, match="Aucune photo"):
        finaliser(session, brouillon, stockage)


def test_finaliser_forme_les_bouteilles_et_lance(session, quatre, stockage):
    inverser_paire(session, quatre, 2)
    assert finaliser(session, quatre, stockage) == 2

    inventaire = charger_inventaire(session, quatre)
    assert (inventaire.statut, inventaire.extraction) == ("ouvert", "lancee")
    bouteilles = inventaire.bouteilles
    assert [(b.photo_etiquette.nom_origine, b.photo_contre.nom_origine) for b in bouteilles] == [
        ("A.jpg", "B.jpg"),
        ("D.jpg", "C.jpg"),
    ]
    # Même identifiant qu'en ligne de commande pour les mêmes photos.
    attendu = PhotosBouteille(
        etiquette=chemin_stocke(stockage, bouteilles[1].photo_etiquette.chemin),
        contre_etiquette=chemin_stocke(stockage, bouteilles[1].photo_contre.chemin),
    ).identifiant
    assert bouteilles[1].identifiant == attendu
    assert reserver_bouteille(session, "worker") == bouteilles[0].id  # le worker la voit


def test_apres_finalisation_plus_aucune_modification_de_photos(session, quatre, stockage):
    premiere = apercu(session, quatre).photos[0].id
    finaliser(session, quatre, stockage)
    for action in (
        lambda: envoyer(session, quatre, stockage, jpeg(42), "tard.jpg"),
        lambda: supprimer_photo(session, quatre, premiere),
        lambda: deplacer_photo(session, quatre, premiere, 2),
        lambda: inverser_paire(session, quatre, 1),
        lambda: retrier(session, quatre),
        lambda: finaliser(session, quatre, stockage),
    ):
        with pytest.raises(DepotFerme, match="ne peuvent plus être modifiées"):
            action()
    assert len(apercu(session, quatre).photos) == 4
    assert session.query(FicheBouteille).filter_by(inventaire_id=quatre).count() == 2


def test_lancer_un_brouillon_sans_le_finaliser_est_refuse(session, quatre):
    with pytest.raises(LancementRefuse, match="brouillon"):
        lancer(session, quatre)


def test_etiquettes_seules_un_nombre_impair_est_accepte(session, nom_maison, stockage):
    inventaire_id = creer_brouillon(session, nom_maison, CONFIG_TEST, "Étiquettes", sans_contre=True).inventaire_id
    for rang in range(1, 4):
        envoyer(session, inventaire_id, stockage, jpeg(rang), f"e{rang}.jpg", d(rang))
    vue = apercu(session, inventaire_id)
    assert vue.peut_lancer and vue.anomalies == []
    assert [p.contre_etiquette for p in vue.paires] == [None, None, None]
    with pytest.raises(ModificationRefusee, match="que des étiquettes"):
        inverser_paire(session, inventaire_id, 1)
    assert finaliser(session, inventaire_id, stockage) == 3
    assert all(b.photo_contre_id is None for b in charger_inventaire(session, inventaire_id).bouteilles)


def test_creer_un_brouillon_demande_un_nom_et_la_bonne_maison(session, nom_maison):
    with pytest.raises(EnvoiRefuse, match="Donner un nom"):
        creer_brouillon(session, nom_maison, CONFIG_TEST, "  ")
    with pytest.raises(EnvoiRefuse, match="décrit"):
        creer_brouillon(session, "Autre maison", CONFIG_TEST, "Vente")
    assert charger_config(CONFIG_TEST).maison == nom_maison
