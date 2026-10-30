"""add soft delete to product and sku

Revision ID: a1b2c3d4e5f6
Revises: 56526b3d784c
Create Date: 2026-10-30 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '56526b3d784c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'product',
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(op.f('ix_product_is_deleted'), 'product', ['is_deleted'], unique=False)

    op.add_column(
        'sku',
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(op.f('ix_sku_is_deleted'), 'sku', ['is_deleted'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sku_is_deleted'), table_name='sku')
    op.drop_column('sku', 'is_deleted')

    op.drop_index(op.f('ix_product_is_deleted'), table_name='product')
    op.drop_column('product', 'is_deleted')
