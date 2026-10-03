"""add sku column to salemetric

Revision ID: 20261003_add_sku
Revises: 602c6bd513aa
Create Date: 2026-10-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
import sqlalchemy.dialects.postgresql as pg

# revision identifiers, used by Alembic.
revision: str = '20261003_add_sku'
down_revision: str = '602c6bd513aa'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add sku column to salemetric
    op.add_column('salemetric', sa.Column('sku', sa.String(length=50), nullable=True))
    
    # Create index on sku for per-SKU queries
    op.create_index(op.f('ix_salemetric_sku'), 'salemetric', ['sku'], unique=False)
    
    # Drop old unique constraint and create new one with sku
    op.drop_constraint('uq_sale_metric_date_marketplace_type_user', 'salemetric', type_='unique')
    op.create_unique_constraint(
        'uq_sale_metric_date_marketplace_type_user_sku',
        'salemetric',
        ['metric_date', 'marketplace', 'metric_type', 'user_id', 'sku']
    )


def downgrade() -> None:
    # Drop new unique constraint
    op.drop_constraint('uq_sale_metric_date_marketplace_type_user_sku', 'salemetric', type_='unique')
    
    # Drop sku index
    op.drop_index(op.f('ix_salemetric_sku'), table_name='salemetric')
    
    # Recreate old unique constraint
    op.create_unique_constraint(
        'uq_sale_metric_date_marketplace_type_user',
        'salemetric',
        ['metric_date', 'marketplace', 'metric_type', 'user_id']
    )
    
    # Drop sku column
    op.drop_column('salemetric', 'sku')