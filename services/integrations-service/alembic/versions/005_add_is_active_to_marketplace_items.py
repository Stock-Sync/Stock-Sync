"""add is_active lifecycle flag to marketplace_items

Revision ID: 005
Revises: 004
Create Date: 2026-11-09 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: str | None = '004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'marketplace_items',
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_index(
        op.f('ix_marketplace_items_is_active'),
        'marketplace_items',
        ['is_active'],
        unique=False,
    )
    # Deterministic owner/lookup by (tenant_id, item_id).
    op.create_index(
        'ix_marketplace_items_tenant_item',
        'marketplace_items',
        ['tenant_id', 'item_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_marketplace_items_tenant_item', table_name='marketplace_items'
    )
    op.drop_index(
        op.f('ix_marketplace_items_is_active'), table_name='marketplace_items'
    )
    op.drop_column('marketplace_items', 'is_active')
