from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    marketplace: str = Field(index=True, max_length=50)
    marketplace_order_id: str = Field(index=True, max_length=100)
    internal_sku: str = Field(index=True, min_length=1, max_length=50)
    quantity: int = Field(ge=1)
    total_amount: float = Field(ge=0)
    currency: str = Field(default="BRL", max_length=3)
    status: str = Field(index=True, max_length=50)
    ordered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
