"""File d'attente en base et limite de débit partagée (decisions.md 0109-0114, 0121).

Révision : 0003
Précédente : 0002
Créée le : 2026-10-09

Les inventaires existants passent à l'état d'extraction « non_lancee » ; leurs
bouteilles et extractions sont conservées telles quelles.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ETATS = "'non_lancee', 'lancee', 'annulee', 'arretee'"


def upgrade() -> None:
    op.create_table('limite_debit',
    sa.Column('modele', sa.String(length=100), nullable=False),
    sa.Column('prochain_appel', sa.DateTime(), nullable=True),
    sa.Column('pause_jusqu_a', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('modele', name=op.f('pk_limite_debit'))
    )
    with op.batch_alter_table('bouteille', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reservee_par', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('reservee_le', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('vu_le', sa.DateTime(), nullable=True))

    with op.batch_alter_table('inventaire', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'extraction', sa.String(length=20), nullable=False, server_default='non_lancee'
        ))
        batch_op.add_column(sa.Column('extraction_lancee_le', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('motif_arret', sa.Text(), nullable=True))
        batch_op.create_check_constraint('extraction', f"extraction IN ({ETATS})")


def downgrade() -> None:
    with op.batch_alter_table('inventaire', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_inventaire_extraction'), type_='check')
        batch_op.drop_column('motif_arret')
        batch_op.drop_column('extraction_lancee_le')
        batch_op.drop_column('extraction')

    with op.batch_alter_table('bouteille', schema=None) as batch_op:
        batch_op.drop_column('vu_le')
        batch_op.drop_column('reservee_le')
        batch_op.drop_column('reservee_par')

    op.drop_table('limite_debit')
