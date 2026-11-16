"""Plan 11: tenant-scoped, soft-delete aware SKU uniqueness.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-11-10

The old global unique index on ``sku.internal_sku`` prevented two tenants from
using the same code and also blocked reuse after soft delete. The new partial
unique indexes enforce:

* ``(tenant_id, internal_sku)`` unique only for active rows;
* exactly one active SKU per product (1:1 relationship).

The index creation intentionally fails if legacy data already violates these
rules; no rows are mutated silently by the migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Replace the global unique index with a regular lookup index.
    op.drop_index("ix_sku_internal_sku", table_name="sku")
    op.create_index(
        "ix_sku_internal_sku", "sku", ["internal_sku"], unique=False
    )

    op.create_index(
        "ix_sku_tenant_internal_sku_active",
        "sku",
        ["tenant_id", "internal_sku"],
        unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )
    op.create_index(
        "ix_sku_product_id_active",
        "sku",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def downgrade() -> None:
    op.drop_index("ix_sku_product_id_active", table_name="sku")
    op.drop_index("ix_sku_tenant_internal_sku_active", table_name="sku")

    op.drop_index("ix_sku_internal_sku", table_name="sku")
    op.create_index(
        "ix_sku_internal_sku", "sku", ["internal_sku"], unique=True
    )
