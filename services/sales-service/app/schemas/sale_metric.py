from datetime import date, datetime
from uuid import UUID

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class SaleMetricCreate(SQLModel):
    metric_date: date
    marketplace: str = Field(min_length=1, max_length=50)
    metric_type: str = Field(min_length=1, max_length=50)
    value: float = Field(ge=0)
    sku: str | None = Field(default=None, max_length=50)


class SaleMetricRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: UUID
    user_id: UUID
    sku: str | None
    metric_date: date
    marketplace: str
    metric_type: str
    value: float
    created_at: datetime
