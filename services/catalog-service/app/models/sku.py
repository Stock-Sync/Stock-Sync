from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Field, SQLModel, UniqueConstraint
from uuid6 import uuid7


class SKU(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    user_id: UUID = Field(
        default_factory=uuid7,
        sa_column_kwargs={"index": True},
        description="Tenant UUID (UUIDv7)"
    )
    internal_sku: str = Field(min_length=1, max_length=50)
    price: float | None = Field(default=None, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Unique constraint: one SKU per user
    __table_args__ = (UniqueConstraint("user_id", "internal_sku", name="uq_sku_user_internal"),)
