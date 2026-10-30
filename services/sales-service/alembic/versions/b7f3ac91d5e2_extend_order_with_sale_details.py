"""extend order with sale details

Revision ID: b7f3ac91d5e2
Revises: 602c6bd513aa
Create Date: 2026-10-23 19:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7f3ac91d5e2'
down_revision: str | None = '602c6bd513aa'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('order', sa.Column('marketplace_item_id', sa.String(length=100), nullable=False, server_default=''))
    op.add_column('order', sa.Column('sku_id', sa.Integer(), nullable=True))
    op.add_column('order', sa.Column('item_title', sa.String(length=300), nullable=True))
    op.add_column('order', sa.Column('thumbnail_url', sa.String(length=1000), nullable=True))
    op.add_column('order', sa.Column('buyer_nickname', sa.String(length=100), nullable=True))
    op.add_column('order', sa.Column('unit_price', sa.Float(), nullable=True))
    op.add_column('order', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    # internal_sku becomes nullable so unmapped marketplace items can be recorded
    op.alter_column('order', 'internal_sku', existing_type=sa.String(length=50), nullable=True)
    op.create_unique_constraint(
        'uq_order_marketplace_item',
        'order',
        ['marketplace', 'marketplace_order_id', 'marketplace_item_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_order_marketplace_item', 'order', type_='unique')
    op.alter_column('order', 'internal_sku', existing_type=sa.String(length=50), nullable=False)
    op.drop_column('order', 'updated_at')
    op.drop_column('order', 'unit_price')
    op.drop_column('order', 'buyer_nickname')
    op.drop_column('order', 'thumbnail_url')
    op.drop_column('order', 'item_title')
    op.drop_column('order', 'sku_id')
    op.drop_column('order', 'marketplace_item_id')
