"""Partial unique indexes for active platform mappings.

Revision ID: c9d0e1f2a3b4
Revises: b7e1f0c2d3a4
Create Date: 2026-11-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b7e1f0c2d3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_platform_mapping_tenant_product_active",
        "platformmapping",
        ["tenant_id", "platform", "platform_product_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )
    op.create_index(
        "ix_platform_mapping_tenant_sku_active",
        "platformmapping",
        ["tenant_id", "sku_id", "platform", "platform_sku"],
        unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_mapping_tenant_sku_active", table_name="platformmapping"
    )
    op.drop_index(
        "ix_platform_mapping_tenant_product_active", table_name="platformmapping"
    )
