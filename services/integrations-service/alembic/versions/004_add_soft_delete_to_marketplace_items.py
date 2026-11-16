"""add soft delete to marketplace_items

Revision ID: 004
Revises: 003
Create Date: 2026-11-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'marketplace_items',
        sa.Column(
            'is_deleted',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        op.f('ix_marketplace_items_is_deleted'),
        'marketplace_items',
        ['is_deleted'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_marketplace_items_is_deleted'), table_name='marketplace_items'
    )
    op.drop_column('marketplace_items', 'is_deleted')
