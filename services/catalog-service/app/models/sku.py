from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class SKU(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    internal_sku: str = Field(index=True, unique=True, min_length=1, max_length=50)
    price: float | None = Field(default=None, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
