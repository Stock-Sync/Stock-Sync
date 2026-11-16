from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Order(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "marketplace",
            "marketplace_order_id",
            "marketplace_item_id",
            name="uq_order_tenant_marketplace_item",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, max_length=64)
    marketplace: str = Field(index=True, max_length=50)
    marketplace_order_id: str = Field(index=True, max_length=100)
    # One order can contain several items; the tuple
    # (tenant, marketplace, order, item) is unique.
    marketplace_item_id: str = Field(default="", max_length=100)
    # Catalog SKU link: nullable because a sale can reference an item that is
    # not mapped to any internal SKU (listing created directly on the marketplace).
    internal_sku: str | None = Field(default=None, max_length=50)
    sku_id: int | None = Field(default=None)
    item_title: str | None = Field(default=None, max_length=300)
    thumbnail_url: str | None = Field(default=None, max_length=1000)
    buyer_nickname: str | None = Field(default=None, max_length=100)
    quantity: int = Field(ge=1)
    unit_price: float | None = Field(default=None, ge=0)
    total_amount: float = Field(ge=0)
    currency: str = Field(default="BRL", max_length=3)
    status: str = Field(index=True, max_length=50)
    # Variations are unsupported. The sale is still recorded for history, but
    # the flag makes the item visible for review instead of silently moving
    # the parent SKU.
    is_variation: bool = Field(default=False)
    ordered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
