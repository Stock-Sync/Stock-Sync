"""add order/item identity and idempotency constraint to stock updates

Revision ID: d3a4b5c6e7f8
Revises: c4d8e2f1a9b3
Create Date: 2026-11-02 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3a4b5c6e7f8'
down_revision: str | None = 'c4d8e2f1a9b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'stockupdatelog',
        sa.Column('marketplace_order_id', sa.String(length=100), nullable=True),
    )
    op.add_column(
        'stockupdatelog',
        sa.Column('marketplace_item_id', sa.String(length=100), nullable=True),
    )
    op.create_index(
        op.f('ix_stockupdatelog_marketplace_order_id'),
        'stockupdatelog',
        ['marketplace_order_id'],
        unique=False,
    )
    op.create_unique_constraint(
        'uq_order_item_stock_adjust',
        'stockupdatelog',
        ['marketplace_order_id', 'marketplace_item_id', 'source_platform'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_order_item_stock_adjust', 'stockupdatelog', type_='unique'
    )
    op.drop_index(
        op.f('ix_stockupdatelog_marketplace_order_id'), table_name='stockupdatelog'
    )
    op.drop_column('stockupdatelog', 'marketplace_item_id')
    op.drop_column('stockupdatelog', 'marketplace_order_id')
