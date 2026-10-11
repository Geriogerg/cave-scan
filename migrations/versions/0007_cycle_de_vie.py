"""Cycle de vie d'un inventaire : archiver, corbeille, clore ; retirer une bouteille
(decisions.md 0168).

Révision : 0007
Précédente : 0006
Créée le : 2026-10-11

Rien ne se supprime : un inventaire « supprimé » va à la corbeille (date), une
bouteille retirée garde toutes ses données. Chaque geste est tracé dans un
historique qui ne se réécrit pas (`evenement_inventaire`, et deux types de plus
pour `evenement_bouteille`). Les inventaires et bouteilles existants : ni
archivés, ni supprimés, ni clos, ni retirés.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES_BOUTEILLE_AVANT = "'reanalyse', 'inversion_photos', 'signalement_paire', 'signalement_leve', 'separation'"
TYPES_BOUTEILLE = TYPES_BOUTEILLE_AVANT + ", 'retrait', 'remise'"
TYPES_INVENTAIRE = (
    "'renommage', 'archivage', 'desarchivage', 'suppression', 'restauration', 'cloture', 'reouverture'"
)


def upgrade() -> None:
    op.create_table(
        "evenement_inventaire",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inventaire_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("auteur", sa.String(length=200), nullable=False),
        sa.Column("cree_le", sa.DateTime(), nullable=False),
        sa.Column("detail", sa.JSON(none_as_null=True), nullable=True),
        sa.CheckConstraint(f"type IN ({TYPES_INVENTAIRE})", name=op.f("ck_evenement_inventaire_type")),
        sa.ForeignKeyConstraint(
            ["inventaire_id"], ["inventaire.id"], name=op.f("fk_evenement_inventaire_inventaire_id_inventaire")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evenement_inventaire")),
    )
    with op.batch_alter_table("inventaire", schema=None) as batch_op:
        batch_op.add_column(sa.Column("archive_le", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("supprime_le", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("clos_le", sa.DateTime(), nullable=True))
    with op.batch_alter_table("bouteille", schema=None) as batch_op:
        batch_op.add_column(sa.Column("retiree", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("evenement_bouteille", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_evenement_bouteille_type"), type_="check")
        batch_op.create_check_constraint("type", f"type IN ({TYPES_BOUTEILLE})")


def downgrade() -> None:
    connexion = op.get_bind()
    if connexion.execute(sa.text("SELECT 1 FROM evenement_bouteille WHERE type IN ('retrait', 'remise')")).first():
        raise RuntimeError(
            "Retour arrière impossible : des bouteilles ont été retirées ou remises ; l'ancien schéma ne "
            "saurait pas le dire. Base laissée telle quelle."
        )
    with op.batch_alter_table("evenement_bouteille", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_evenement_bouteille_type"), type_="check")
        batch_op.create_check_constraint("type", f"type IN ({TYPES_BOUTEILLE_AVANT})")
    with op.batch_alter_table("bouteille", schema=None) as batch_op:
        batch_op.drop_column("retiree")
    with op.batch_alter_table("inventaire", schema=None) as batch_op:
        batch_op.drop_column("clos_le")
        batch_op.drop_column("supprime_le")
        batch_op.drop_column("archive_le")
    op.drop_table("evenement_inventaire")
