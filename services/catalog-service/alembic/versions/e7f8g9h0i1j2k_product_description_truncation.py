"""Plan 12: Track description truncation in catalog Product.

Adds the ``is_description_truncated`` column to the ``product`` table so the
frontend can inform the user when a Mercado Livre listing exceeds the 2000
character limit and its description has been truncated in the local catalog.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8g9h0i1j2k"
down_revision: str | None = "d1e2f3a4b5c6"  # Last Plan 11 migration
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column(
            "is_description_truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("product", "is_description_truncated")
