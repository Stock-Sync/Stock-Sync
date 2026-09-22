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


class SKURead(SKUBase):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
