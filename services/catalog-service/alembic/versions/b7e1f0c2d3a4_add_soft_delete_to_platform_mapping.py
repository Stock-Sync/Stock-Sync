"""add soft delete to platform mappings

Revision ID: b7e1f0c2d3a4
Revises: a1b2c3d4e5f6
Create Date: 2026-11-02 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e1f0c2d3a4'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'platformmapping',
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        op.f('ix_platformmapping_is_deleted'),
        'platformmapping',
        ['is_deleted'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_platformmapping_is_deleted'), table_name='platformmapping'
    )
    op.drop_column('platformmapping', 'is_deleted')
