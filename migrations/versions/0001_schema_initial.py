"""Schéma initial : maisons, versions de config, inventaires, photos, bouteilles,
extractions et corrections (guide de session 2 ; decisions.md 0072-0075).

Crée la base de zéro. Toute évolution ultérieure passe par une nouvelle
migration, jamais par la modification de celle-ci : une base déjà créée ne
perd jamais ses inventaires.

Révision : 0001
Précédente : aucune
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('maison',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=200), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_maison')),
    sa.UniqueConstraint('nom', name=op.f('uq_maison_nom'))
    )
    op.create_table('config_version',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('maison_id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('version_declaree', sa.Integer(), nullable=False),
    sa.Column('contenu', sa.Text(), nullable=False),
    sa.Column('empreinte', sa.String(length=64), nullable=False),
    sa.Column('fichier_source', sa.String(length=255), nullable=False),
    sa.Column('cree_le', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['maison_id'], ['maison.id'], name=op.f('fk_config_version_maison_id_maison')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_config_version')),
    sa.UniqueConstraint('maison_id', 'empreinte', name=op.f('uq_config_version_maison_id_empreinte')),
    sa.UniqueConstraint('maison_id', 'numero', name=op.f('uq_config_version_maison_id_numero'))
    )
    op.create_table('inventaire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('maison_id', sa.Integer(), nullable=False),
    sa.Column('config_version_id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=200), nullable=False),
    sa.Column('cree_le', sa.DateTime(), nullable=False),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('dossier_source', sa.Text(), nullable=True),
    sa.CheckConstraint("statut IN ('ouvert', 'valide')", name=op.f('ck_inventaire_statut')),
    sa.ForeignKeyConstraint(['config_version_id'], ['config_version.id'], name=op.f('fk_inventaire_config_version_id_config_version')),
    sa.ForeignKeyConstraint(['maison_id'], ['maison.id'], name=op.f('fk_inventaire_maison_id_maison')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventaire'))
    )
    op.create_table('photo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('inventaire_id', sa.Integer(), nullable=False),
    sa.Column('chemin', sa.String(length=255), nullable=False),
    sa.Column('empreinte', sa.String(length=64), nullable=False),
    sa.Column('nom_origine', sa.String(length=255), nullable=False),
    sa.Column('prise_de_vue', sa.DateTime(), nullable=True),
    sa.Column('ordre', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['inventaire_id'], ['inventaire.id'], name=op.f('fk_photo_inventaire_id_inventaire')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_photo')),
    sa.UniqueConstraint('inventaire_id', 'empreinte', name=op.f('uq_photo_inventaire_id_empreinte')),
    sa.UniqueConstraint('inventaire_id', 'ordre', name=op.f('uq_photo_inventaire_id_ordre'))
    )
    op.create_table('bouteille',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('inventaire_id', sa.Integer(), nullable=False),
    sa.Column('identifiant', sa.String(length=20), nullable=False),
    sa.Column('photo_etiquette_id', sa.Integer(), nullable=False),
    sa.Column('photo_contre_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('quantite', sa.Integer(), nullable=False),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.CheckConstraint("statut IN ('a_extraire', 'en_cours', 'extraite', 'erreur', 'validee')", name=op.f('ck_bouteille_statut')),
    sa.CheckConstraint('quantite >= 1', name=op.f('ck_bouteille_quantite')),
    sa.ForeignKeyConstraint(['inventaire_id'], ['inventaire.id'], name=op.f('fk_bouteille_inventaire_id_inventaire')),
    sa.ForeignKeyConstraint(['photo_contre_id'], ['photo.id'], name=op.f('fk_bouteille_photo_contre_id_photo')),
    sa.ForeignKeyConstraint(['photo_etiquette_id'], ['photo.id'], name=op.f('fk_bouteille_photo_etiquette_id_photo')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bouteille')),
    sa.UniqueConstraint('inventaire_id', 'identifiant', name=op.f('uq_bouteille_inventaire_id_identifiant')),
    sa.UniqueConstraint('inventaire_id', 'position', name=op.f('uq_bouteille_inventaire_id_position'))
    )
    op.create_table('correction',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bouteille_id', sa.Integer(), nullable=False),
    sa.Column('champ', sa.String(length=100), nullable=False),
    sa.Column('ancienne_valeur', sa.JSON(none_as_null=True), nullable=True),
    sa.Column('nouvelle_valeur', sa.JSON(none_as_null=True), nullable=True),
    sa.Column('auteur', sa.String(length=200), nullable=False),
    sa.Column('cree_le', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['bouteille_id'], ['bouteille.id'], name=op.f('fk_correction_bouteille_id_bouteille')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_correction'))
    )
    op.create_table('extraction',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bouteille_id', sa.Integer(), nullable=False),
    sa.Column('sortie_brute', sa.JSON(none_as_null=True), nullable=True),
    sa.Column('modele', sa.String(length=100), nullable=False),
    sa.Column('version_prompt', sa.String(length=32), nullable=False),
    sa.Column('tokens_entree', sa.Integer(), nullable=True),
    sa.Column('tokens_sortie', sa.Integer(), nullable=True),
    sa.Column('duree_ms', sa.Integer(), nullable=False),
    sa.Column('cree_le', sa.DateTime(), nullable=False),
    sa.Column('erreur', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['bouteille_id'], ['bouteille.id'], name=op.f('fk_extraction_bouteille_id_bouteille')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_extraction'))
    )


def downgrade() -> None:
    op.drop_table('extraction')
    op.drop_table('correction')
    op.drop_table('bouteille')
    op.drop_table('photo')
    op.drop_table('inventaire')
    op.drop_table('config_version')
    op.drop_table('maison')
