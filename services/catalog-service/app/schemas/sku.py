from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class SKUBase(SQLModel):
    product_id: int
    internal_sku: str = Field(min_length=1, max_length=50)
    price: float | None = Field(default=None, ge=0)
    stock_quantity: int = Field(default=0, ge=0)


class SKUCreate(SKUBase):
    pass


class SKUUpdate(SQLModel):
    product_id: int | None = Field(default=None)
    internal_sku: str | None = Field(default=None, min_length=1, max_length=50)
    price: float | None = Field(default=None, ge=0)
    stock_quantity: int | None = Field(default=None, ge=0)


class SKUAdjust(SQLModel):
    """Relative stock change (negative to deduct, positive to add)."""

    delta: int
    source: str = Field(default="manual", max_length=50)


class SKUAdjustRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    sku_id: int
    internal_sku: str
    previous_quantity: int
    new_quantity: int
    clamped: bool


class SKURead(SKUBase):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    tenant_id: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
