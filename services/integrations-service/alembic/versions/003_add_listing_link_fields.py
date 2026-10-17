"""add listing link fields to marketplace_items

Links each Mercado Livre item to the local catalog (sku_id/product_id) and
stores the marketplace context used by the listing hub (category, condition,
description).

Revision ID: 003
Revises: d38fa5caf6b4
Create Date: 2026-10-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = 'd38fa5caf6b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('marketplace_items', sa.Column('sku_id', sa.Integer(), nullable=True))
    op.add_column('marketplace_items', sa.Column('product_id', sa.Integer(), nullable=True))
    op.add_column('marketplace_items', sa.Column('category_id', sa.String(length=50), nullable=True))
    op.add_column('marketplace_items', sa.Column('condition', sa.String(length=10), nullable=True))
    op.add_column('marketplace_items', sa.Column('description', sa.Text(), nullable=True))
    op.create_index(op.f('ix_marketplace_items_sku_id'), 'marketplace_items', ['sku_id'], unique=False)
    op.create_index(op.f('ix_marketplace_items_product_id'), 'marketplace_items', ['product_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_marketplace_items_product_id'), table_name='marketplace_items')
    op.drop_index(op.f('ix_marketplace_items_sku_id'), table_name='marketplace_items')
    op.drop_column('marketplace_items', 'description')
    op.drop_column('marketplace_items', 'condition')
    op.drop_column('marketplace_items', 'category_id')
    op.drop_column('marketplace_items', 'product_id')
    op.drop_column('marketplace_items', 'sku_id')
