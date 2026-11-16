from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class StockUpdateLogCreate(SQLModel):
    internal_sku: str = Field(min_length=1, max_length=50)
    previous_quantity: int = Field(ge=0)
    new_quantity: int = Field(ge=0)
    source_platform: str = Field(max_length=50)
    marketplace_order_id: str | None = Field(default=None, max_length=100)
    marketplace_item_id: str | None = Field(default=None, max_length=100)
    status: str = Field(default="in_progress", max_length=20)
    deducted_quantity: int = Field(default=0, ge=0)
    clamped: bool = False
    attempts: int = Field(default=0, ge=0)
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    error_message: str | None = Field(default=None, max_length=2000)


class StockUpdateLogRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    internal_sku: str
    previous_quantity: int
    new_quantity: int
    source_platform: str
    marketplace_order_id: str | None
    marketplace_item_id: str | None
    status: str
    deducted_quantity: int
    clamped: bool
    attempts: int
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
