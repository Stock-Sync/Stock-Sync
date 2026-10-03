from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class OrderCreate(SQLModel):
    marketplace: str = Field(min_length=1, max_length=50)
    marketplace_order_id: str = Field(min_length=1, max_length=100)
    internal_sku: str = Field(min_length=1, max_length=50)
    quantity: int = Field(ge=1)
    total_amount: float = Field(ge=0)
    currency: str = Field(default="BRL", max_length=3)
    status: str = Field(min_length=1, max_length=50)
    ordered_at: datetime | None = Field(default=None)


class OrderRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: UUID
    user_id: UUID
    marketplace: str
    marketplace_order_id: str
    internal_sku: str
    quantity: int
    total_amount: float
    currency: str
    status: str
    ordered_at: datetime
    created_at: datetime
