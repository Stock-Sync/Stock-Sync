from datetime import UTC, datetime

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class SKU(SQLModel, table=True):
    # Plan 11: uniqueness is tenant-scoped and soft-delete aware.
    # - one active SKU per product (strict 1:1)
    # - one active internal_sku per tenant (identical codes may exist across
    #   tenants, and a soft-deleted code can be reused)
    __table_args__ = (
        Index(
            "ix_sku_tenant_internal_sku_active",
            "tenant_id",
            "internal_sku",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "ix_sku_product_id_active",
            "product_id",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(max_length=36, index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    # ``index`` keeps the lookup by SKU code fast; uniqueness is enforced by
    # the partial indexes above instead of a global constraint.
    internal_sku: str = Field(index=True, min_length=1, max_length=50)
    price: float | None = Field(default=None, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    is_deleted: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
