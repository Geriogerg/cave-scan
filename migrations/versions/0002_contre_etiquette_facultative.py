"""Contre-étiquette facultative : inventaires d'étiquettes seules (decisions.md 0108).

Révision : 0002
Précédente : 0001
Créée le : 2026-10-09 15:56:04.698519
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('bouteille', schema=None) as batch_op:
        batch_op.alter_column('photo_contre_id',
               existing_type=sa.INTEGER(),
               nullable=True)



def downgrade() -> None:
    with op.batch_alter_table('bouteille', schema=None) as batch_op:
        batch_op.alter_column('photo_contre_id',
               existing_type=sa.INTEGER(),
               nullable=False)

