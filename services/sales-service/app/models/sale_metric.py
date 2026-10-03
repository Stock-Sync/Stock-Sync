from datetime import UTC, date, datetime
from uuid import UUID

from sqlmodel import Field, SQLModel, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from uuid6 import uuid7


class SaleMetric(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("metric_date", "marketplace", "metric_type", "user_id", "sku", name="uq_sale_metric_date_marketplace_type_user_sku"),)

    id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column_kwargs={"primary_key": True},
        description="Sale Metric ID (UUIDv7)"
    )
    user_id: UUID = Field(
        default_factory=uuid7,
        sa_column_kwargs={"index": True},
        description="Tenant UUID (UUIDv7)"
    )
    sku: str | None = Field(default=None, index=True, max_length=50, description="SKU for per-SKU metrics (NULL for global)")
    metric_date: date = Field(index=True)
    marketplace: str = Field(index=True, max_length=50)
    metric_type: str = Field(max_length=50)
    value: float = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
