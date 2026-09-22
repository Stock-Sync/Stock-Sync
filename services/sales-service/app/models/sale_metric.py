from datetime import UTC, date, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class SaleMetric(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("metric_date", "marketplace", "metric_type"),)

    id: int | None = Field(default=None, primary_key=True)
    metric_date: date = Field(index=True)
    marketplace: str = Field(index=True, max_length=50)
    metric_type: str = Field(max_length=50)
    value: float = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
