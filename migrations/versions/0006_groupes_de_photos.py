"""Une bouteille = un groupe de photos (decisions.md 0166).

Révision : 0006
Précédente : 0005
Créée le : 2026-10-11

On abandonne l'appariement étiquette / contre-étiquette : chaque bouteille
pointe vers un GROUPE de photos ordonnées (1 à N). Reprise des données, sans
toucher à une seule extraction, correction, ni à un seul événement ou
identifiant :

- chaque bouteille devient un groupe : étiquette = photo 1, contre-étiquette =
  photo 2 ;
- une bouteille née d'une séparation partage le groupe de sa source (elles
  partageaient déjà les mêmes photos) ;
- les photos d'un brouillon (pas encore de bouteilles) sont regroupées comme
  l'ancien lancement l'aurait fait : par paires dans l'ordre, ou une par
  bouteille pour un inventaire « étiquettes seules » ; une photo restée seule
  forme un groupe d'une photo.

Tout est vérifié AVANT d'écrire : une incohérence arrête la migration avec un
message clair, la base reste telle quelle. Retour arrière possible tant
qu'aucun groupe n'a plus de deux photos.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class ReprisePhotosImpossible(RuntimeError):
    pass


def _plan_de_reprise(connexion) -> list[dict]:
    """Les groupes à créer, inventaire par inventaire : numéro, photos dans
    l'ordre, bouteilles qui y pointent. Ne lit que ; lève si c'est incohérent."""
    inventaires = connexion.execute(sa.text("SELECT id, sans_contre FROM inventaire ORDER BY id")).all()
    groupes: list[dict] = []
    for inventaire_id, sans_contre in inventaires:
        bouteilles = connexion.execute(
            sa.text(
                "SELECT id, position, photo_etiquette_id, photo_contre_id, separee_de_id "
                "FROM bouteille WHERE inventaire_id = :i ORDER BY position"
            ),
            {"i": inventaire_id},
        ).all()
        photos = [ligne[0] for ligne in connexion.execute(
            sa.text("SELECT id FROM photo WHERE inventaire_id = :i ORDER BY ordre"), {"i": inventaire_id}
        )]
        prises: set[int] = set()
        du_groupe: dict[int, dict] = {}  # bouteille -> son groupe
        for bouteille_id, position, etiquette, contre, separee_de in bouteilles:
            if separee_de is not None:
                continue
            membres = [p for p in (etiquette, contre) if p is not None]
            deja = prises.intersection(membres)
            if deja:
                raise ReprisePhotosImpossible(
                    f"Inventaire n°{inventaire_id} : la photo n°{min(deja)} appartient à deux bouteilles "
                    f"qui ne sont pas nées d'une séparation. Base laissée telle quelle."
                )
            prises.update(membres)
            groupe = {"inventaire_id": inventaire_id, "numero": position, "photos": membres, "bouteilles": [bouteille_id]}
            groupes.append(groupe)
            du_groupe[bouteille_id] = groupe

        separees = {b[0]: b[4] for b in bouteilles if b[4] is not None}
        for bouteille_id in separees:
            source, vues = separees[bouteille_id], {bouteille_id}
            while source in separees and source not in vues:
                vues.add(source)
                source = separees[source]
            if source not in du_groupe:
                raise ReprisePhotosImpossible(
                    f"Inventaire n°{inventaire_id} : la bouteille n°{bouteille_id} est née d'une séparation "
                    f"dont la source est introuvable. Base laissée telle quelle."
                )
            du_groupe[source]["bouteilles"].append(bouteille_id)

        restantes = [p for p in photos if p not in prises]  # brouillon : pas encore de bouteilles
        pas = 1 if sans_contre else 2
        numero = max((g["numero"] for g in groupes if g["inventaire_id"] == inventaire_id), default=0)
        for rang in range(0, len(restantes), pas):
            numero += 1
            groupes.append(
                {"inventaire_id": inventaire_id, "numero": numero, "photos": restantes[rang : rang + pas], "bouteilles": []}
            )
    return groupes


def upgrade() -> None:
    connexion = op.get_bind()
    plan = _plan_de_reprise(connexion)  # tout est vérifié avant d'écrire

    groupe_photos = op.create_table(
        "groupe_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inventaire_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("cle", sa.String(length=64), nullable=True),
        sa.Column("quantite", sa.Integer(), nullable=False),
        sa.Column("cree_le", sa.DateTime(), nullable=False),
        sa.CheckConstraint("quantite >= 1", name=op.f("ck_groupe_photos_quantite")),
        sa.ForeignKeyConstraint(
            ["inventaire_id"], ["inventaire.id"], name=op.f("fk_groupe_photos_inventaire_id_inventaire")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groupe_photos")),
        sa.UniqueConstraint("inventaire_id", "cle", name=op.f("uq_groupe_photos_inventaire_id_cle")),
    )
    with op.batch_alter_table("photo", schema=None) as batch_op:
        batch_op.add_column(sa.Column("groupe_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("rang", sa.Integer(), nullable=True))
    with op.batch_alter_table("bouteille", schema=None) as batch_op:
        batch_op.add_column(sa.Column("groupe_id", sa.Integer(), nullable=True))

    maintenant = datetime.now(UTC).replace(tzinfo=None)
    for groupe in plan:
        groupe_id = connexion.execute(
            groupe_photos.insert().values(
                inventaire_id=groupe["inventaire_id"], numero=groupe["numero"], cle=None, quantite=1, cree_le=maintenant
            )
        ).inserted_primary_key[0]
        for rang, photo_id in enumerate(groupe["photos"], start=1):
            connexion.execute(
                sa.text("UPDATE photo SET groupe_id = :g, rang = :r WHERE id = :p"),
                {"g": groupe_id, "r": rang, "p": photo_id},
            )
        for bouteille_id in groupe["bouteilles"]:
            connexion.execute(
                sa.text("UPDATE bouteille SET groupe_id = :g WHERE id = :b"), {"g": groupe_id, "b": bouteille_id}
            )

    with op.batch_alter_table("photo", schema=None) as batch_op:
        batch_op.alter_column("groupe_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("rang", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_photo_groupe_id_groupe_photos"), "groupe_photos", ["groupe_id"], ["id"]
        )
        batch_op.create_unique_constraint(batch_op.f("uq_photo_groupe_id_rang"), ["groupe_id", "rang"])
    with op.batch_alter_table("bouteille", schema=None) as batch_op:
        batch_op.alter_column("groupe_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_bouteille_groupe_id_groupe_photos"), "groupe_photos", ["groupe_id"], ["id"]
        )
        batch_op.drop_constraint(batch_op.f("fk_bouteille_photo_etiquette_id_photo"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_bouteille_photo_contre_id_photo"), type_="foreignkey")
        batch_op.drop_column("photo_etiquette_id")
        batch_op.drop_column("photo_contre_id")
    with op.batch_alter_table("inventaire", schema=None) as batch_op:
        batch_op.drop_column("ordre_manuel")
        batch_op.drop_column("sans_contre")


def downgrade() -> None:
    connexion = op.get_bind()
    trop = connexion.execute(
        sa.text("SELECT groupe_id, count(*) FROM photo GROUP BY groupe_id HAVING count(*) > 2")
    ).first()
    if trop is not None:
        raise ReprisePhotosImpossible(
            f"Retour arrière impossible : le groupe n°{trop[0]} a {trop[1]} photos, l'ancien schéma n'en "
            f"connaît que deux par bouteille (étiquette, contre-étiquette). Base laissée telle quelle."
        )
    vide = connexion.execute(
        sa.text("SELECT b.id FROM bouteille b WHERE NOT EXISTS (SELECT 1 FROM photo p WHERE p.groupe_id = b.groupe_id)")
    ).first()
    if vide is not None:
        raise ReprisePhotosImpossible(
            f"Retour arrière impossible : la bouteille n°{vide[0]} n'a aucune photo. Base laissée telle quelle."
        )

    with op.batch_alter_table("inventaire", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sans_contre", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("ordre_manuel", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("bouteille", schema=None) as batch_op:
        batch_op.add_column(sa.Column("photo_etiquette_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("photo_contre_id", sa.Integer(), nullable=True))

    bouteilles = connexion.execute(sa.text("SELECT id, groupe_id FROM bouteille")).all()
    for bouteille_id, groupe_id in bouteilles:
        photos = [ligne[0] for ligne in connexion.execute(
            sa.text("SELECT id FROM photo WHERE groupe_id = :g ORDER BY rang"), {"g": groupe_id}
        )]
        connexion.execute(
            sa.text("UPDATE bouteille SET photo_etiquette_id = :e, photo_contre_id = :c WHERE id = :b"),
            {"e": photos[0], "c": photos[1] if len(photos) > 1 else None, "b": bouteille_id},
        )
    # « Étiquettes seules » : un inventaire dont tous les groupes ont une seule photo.
    connexion.execute(sa.text(
        "UPDATE inventaire SET sans_contre = 1 WHERE EXISTS (SELECT 1 FROM groupe_photos g WHERE g.inventaire_id = inventaire.id) "
        "AND NOT EXISTS (SELECT 1 FROM photo p WHERE p.inventaire_id = inventaire.id AND p.rang > 1)"
    ))

    with op.batch_alter_table("bouteille", schema=None) as batch_op:
        batch_op.alter_column("photo_etiquette_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_bouteille_photo_etiquette_id_photo"), "photo", ["photo_etiquette_id"], ["id"]
        )
        batch_op.create_foreign_key(batch_op.f("fk_bouteille_photo_contre_id_photo"), "photo", ["photo_contre_id"], ["id"])
        batch_op.drop_constraint(batch_op.f("fk_bouteille_groupe_id_groupe_photos"), type_="foreignkey")
        batch_op.drop_column("groupe_id")
    with op.batch_alter_table("photo", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_photo_groupe_id_rang"), type_="unique")
        batch_op.drop_constraint(batch_op.f("fk_photo_groupe_id_groupe_photos"), type_="foreignkey")
        batch_op.drop_column("rang")
        batch_op.drop_column("groupe_id")
    op.drop_table("groupe_photos")
