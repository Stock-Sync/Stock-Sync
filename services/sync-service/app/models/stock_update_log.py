from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class StockUpdateLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    internal_sku: str = Field(index=True, min_length=1, max_length=50)
    previous_quantity: int = Field(ge=0)
    new_quantity: int = Field(ge=0)
    source_platform: str = Field(max_length=50)
    status: str = Field(default="success", index=True, max_length=20)
    error_message: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
