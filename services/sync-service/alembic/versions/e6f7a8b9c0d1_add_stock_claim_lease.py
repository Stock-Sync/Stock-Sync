"""add explicit stock claim states, lease and heartbeat

Revision ID: e6f7a8b9c0d1
Revises: d3a4b5c6e7f8
Create Date: 2026-11-02 20:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: str | None = 'd3a4b5c6e7f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'stockupdatelog',
        sa.Column('deducted_quantity', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'stockupdatelog',
        sa.Column('clamped', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'stockupdatelog',
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'stockupdatelog',
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'stockupdatelog',
        sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'stockupdatelog',
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Migrate legacy terminal statuses to the explicit claim vocabulary.
    op.execute(
        """
        UPDATE stockupdatelog
           SET status = 'applied'
         WHERE status IN ('success', 'clamped', 'reverted')
        """
    )
    op.execute(
        """
        UPDATE stockupdatelog
           SET status = 'failed'
         WHERE status = 'pending'
        """
    )
    op.execute(
        """
        UPDATE stockupdatelog
           SET deducted_quantity = GREATEST(previous_quantity - new_quantity, 0)
         WHERE source_platform = 'ml_sale'
           AND status = 'applied'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE stockupdatelog
           SET status = 'success'
         WHERE status = 'applied'
           AND source_platform = 'ml_sale'
        """
    )
    op.execute(
        """
        UPDATE stockupdatelog
           SET status = 'reverted'
         WHERE status = 'applied'
           AND source_platform = 'ml_cancellation'
        """
    )
    op.execute(
        """
        UPDATE stockupdatelog
           SET status = 'pending'
         WHERE status = 'in_progress'
        """
    )
    op.drop_column('stockupdatelog', 'updated_at')
    op.drop_column('stockupdatelog', 'heartbeat_at')
    op.drop_column('stockupdatelog', 'lease_expires_at')
    op.drop_column('stockupdatelog', 'attempts')
    op.drop_column('stockupdatelog', 'clamped')
    op.drop_column('stockupdatelog', 'deducted_quantity')
