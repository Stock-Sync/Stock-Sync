from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Field, SQLModel
from uuid6 import uuid7


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: UUID = Field(
        default_factory=uuid7,
        sa_column_kwargs={"index": True},
        description="Tenant UUID (UUIDv7)"
    )
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # No unique constraint on (user_id, name) - product names can repeat per tenant
    # SKU table handles uniqueness via (user_id, internal_sku)
