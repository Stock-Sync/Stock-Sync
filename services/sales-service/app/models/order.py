from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Field, SQLModel, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from uuid6 import uuid7


class Order(SQLModel, table=True):
    id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column_kwargs={"primary_key": True},
        description="Order ID (UUIDv7)"
    )
    user_id: UUID = Field(
        default_factory=uuid7,
        sa_column_kwargs={"index": True},
        description="Tenant UUID (UUIDv7)"
    )
    marketplace: str = Field(index=True, max_length=50)
    marketplace_order_id: str = Field(index=True, max_length=100)
    internal_sku: str = Field(index=True, min_length=1, max_length=50)
    quantity: int = Field(ge=1)
    total_amount: float = Field(ge=0)
    currency: str = Field(default="BRL", max_length=3)
    status: str = Field(index=True, max_length=50)
    ordered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
