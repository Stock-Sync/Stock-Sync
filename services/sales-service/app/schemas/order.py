from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class OrderCreate(SQLModel):
    """Internal payload used by sync-service to record a processed sale."""

    marketplace: str = Field(min_length=1, max_length=50)
    marketplace_order_id: str = Field(min_length=1, max_length=100)
    marketplace_item_id: str = Field(default="", max_length=100)
    internal_sku: str | None = Field(default=None, max_length=50)
    sku_id: int | None = None
    item_title: str | None = Field(default=None, max_length=300)
    thumbnail_url: str | None = Field(default=None, max_length=1000)
    buyer_nickname: str | None = Field(default=None, max_length=100)
    quantity: int = Field(ge=1)
    unit_price: float | None = Field(default=None, ge=0)
    total_amount: float = Field(ge=0)
    currency: str = Field(default="BRL", max_length=3)
    status: str = Field(min_length=1, max_length=50)
    ordered_at: datetime | None = Field(default=None)


class OrderRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    marketplace: str
    marketplace_order_id: str
    marketplace_item_id: str
    internal_sku: str | None
    sku_id: int | None
    item_title: str | None
    thumbnail_url: str | None
    buyer_nickname: str | None
    quantity: int
    unit_price: float | None
    total_amount: float
    currency: str
    status: str
    ordered_at: datetime
    created_at: datetime


class OrderListResponse(SQLModel):
    items: list[OrderRead]
    total: int
    page: int
    limit: int
