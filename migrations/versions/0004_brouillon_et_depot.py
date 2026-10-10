"""Inventaire en brouillon et dépôt des photos (decisions.md 0126-0128).

Révision : 0004
Précédente : 0003
Créée le : 2026-10-10

Les inventaires existants gardent leur statut ; seuls les nouveaux peuvent
être des brouillons.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('inventaire', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_inventaire_statut'), type_='check')
        batch_op.create_check_constraint('statut', "statut IN ('brouillon', 'ouvert', 'valide')")
        batch_op.add_column(sa.Column('sans_contre', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('ordre_manuel', sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table('photo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('signature_envoi', sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('photo', schema=None) as batch_op:
        batch_op.drop_column('signature_envoi')

    with op.batch_alter_table('inventaire', schema=None) as batch_op:
        batch_op.drop_column('ordre_manuel')
        batch_op.drop_column('sans_contre')
        batch_op.drop_constraint(op.f('ck_inventaire_statut'), type_='check')
        batch_op.create_check_constraint('statut', "statut IN ('ouvert', 'valide')")
