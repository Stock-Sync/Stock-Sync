from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Field, SQLModel, UniqueConstraint


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: UUID = Field(index=True, nullable=False)  # Tenant UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Unique constraint per tenant (optional, for multi-tenancy)
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_product_user_name"),)
