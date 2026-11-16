"""add items_removed audit column to listings_sync_run

Revision ID: f8b9c0d1e2a3
Revises: e6f7a8b9c0d1
Create Date: 2026-11-08 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8b9c0d1e2a3"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listingssyncrun",
        sa.Column("items_removed", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.alter_column("listingssyncrun", "items_removed", server_default=None)


def downgrade() -> None:
    op.drop_column("listingssyncrun", "items_removed")
