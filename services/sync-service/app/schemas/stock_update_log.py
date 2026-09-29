from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class StockUpdateLogCreate(SQLModel):
    internal_sku: str = Field(min_length=1, max_length=50)
    previous_quantity: int = Field(ge=0)
    new_quantity: int = Field(ge=0)
    source_platform: str = Field(max_length=50)
    status: str = Field(default="success", max_length=20)
    error_message: str | None = Field(default=None, max_length=2000)


class StockUpdateLogRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    internal_sku: str
    previous_quantity: int
    new_quantity: int
    source_platform: str
    status: str
    error_message: str | None
    created_at: datetime
