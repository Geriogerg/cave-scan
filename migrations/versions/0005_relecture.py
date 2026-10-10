"""Écran de relecture : événements, paire signalée, séparation, temps de relecture
(decisions.md 0139).

Révision : 0005
Précédente : 0004
Créée le : 2026-10-10

Les bouteilles existantes : paire non signalée, née d'aucune séparation, temps
de relecture nul. Aucun événement n'est inventé pour le passé. Le contrat
`Bouteille` (les valeurs lues) ne change pas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES = "'reanalyse', 'inversion_photos', 'signalement_paire', 'signalement_leve', 'separation'"


def upgrade() -> None:
    op.create_table('evenement_bouteille',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bouteille_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=30), nullable=False),
    sa.Column('auteur', sa.String(length=200), nullable=False),
    sa.Column('cree_le', sa.DateTime(), nullable=False),
    sa.Column('detail', sa.JSON(none_as_null=True), nullable=True),
    sa.CheckConstraint(f"type IN ({TYPES})", name=op.f('ck_evenement_bouteille_type')),
    sa.ForeignKeyConstraint(['bouteille_id'], ['bouteille.id'], name=op.f('fk_evenement_bouteille_bouteille_id_bouteille')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evenement_bouteille'))
    )
    with op.batch_alter_table('bouteille', schema=None) as batch_op:
        batch_op.add_column(sa.Column('paire_signalee', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('separee_de_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('temps_relecture_ms', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_foreign_key(
            batch_op.f('fk_bouteille_separee_de_id_bouteille'), 'bouteille', ['separee_de_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('bouteille', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_bouteille_separee_de_id_bouteille'), type_='foreignkey')
        batch_op.drop_column('temps_relecture_ms')
        batch_op.drop_column('separee_de_id')
        batch_op.drop_column('paire_signalee')

    op.drop_table('evenement_bouteille')
