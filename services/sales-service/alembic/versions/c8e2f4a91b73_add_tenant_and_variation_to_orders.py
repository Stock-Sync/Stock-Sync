"""add tenant_id and variation flag to orders

Revision ID: c8e2f4a91b73
Revises: b7f3ac91d5e2
Create Date: 2026-11-02 20:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8e2f4a91b73'
down_revision: str | None = 'b7f3ac91d5e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'order',
        sa.Column(
            'tenant_id',
            sa.String(length=64),
            nullable=False,
            server_default='',
        ),
    )
    op.add_column(
        'order',
        sa.Column(
            'is_variation',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(op.f('ix_order_tenant_id'), 'order', ['tenant_id'], unique=False)

    # The old uniqueness did not include the tenant, so two tenants with the
    # same marketplace order id would collide.
    op.drop_constraint('uq_order_marketplace_item', 'order', type_='unique')
    op.create_unique_constraint(
        'uq_order_tenant_marketplace_item',
        'order',
        [
            'tenant_id',
            'marketplace',
            'marketplace_order_id',
            'marketplace_item_id',
        ],
    )

    op.alter_column('order', 'tenant_id', server_default=None)
    op.alter_column('order', 'is_variation', server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        'uq_order_tenant_marketplace_item', 'order', type_='unique'
    )
    op.create_unique_constraint(
        'uq_order_marketplace_item',
        'order',
        ['marketplace', 'marketplace_order_id', 'marketplace_item_id'],
    )
    op.drop_index(op.f('ix_order_tenant_id'), table_name='order')
    op.drop_column('order', 'is_variation')
    op.drop_column('order', 'tenant_id')
