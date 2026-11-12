from datetime import UTC, datetime
from enum import Enum
from typing import Dict, Optional

from sqlmodel import Field, SQLModel
from sqlalchemy import BigInteger, Column
from sqlalchemy.dialects import postgresql


class Marketplace(str, Enum):
    mercadolivre = "mercado_livre"
    shopee = "shopee"


class MarketplaceCredential(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, max_length=36)  # References auth-service user ID
    marketplace: Marketplace = Field(index=True)
    account_name: str = Field(min_length=1, max_length=120)
    ml_user_id: int | None = Field(
        default=None, unique=True, description="Mercado Livre numeric seller ID", sa_type=BigInteger
    )
    ml_nickname: str | None = Field(
        default=None,
        max_length=100,
        description="Mercado Livre nickname/username for public profile URL",
    )
    access_token: str = Field(min_length=1, max_length=2000)
    refresh_token: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )


class MarketplaceItem(SQLModel, table=True):
    __tablename__ = "marketplace_items"
    id: int | None = Field(default=None, primary_key=True)
    item_id: str = Field(max_length=50, index=True)  # ML item ID (e.g., MLB123456)
    user_product_id: str | None = Field(default=None, max_length=50, index=True)  # UP family ID
    tenant_id: str = Field(max_length=36, index=True)  # References auth-service user ID
    ml_user_id: int | None = Field(default=None, sa_type=BigInteger)
    marketplace: str = Field(default="mercado_livre", max_length=30)
    title: str = Field(max_length=255)
    price: float = Field(ge=0)  # Numeric(12,2) in DB
    available_quantity: int = Field(default=0, ge=0)
    status: str | None = Field(default=None, max_length=30)
    thumbnail: str | None = Field(default=None, max_length=500)
    permalink: str | None = Field(default=None, max_length=500)
    family_name: str | None = Field(default=None, max_length=255)
    listing_type_id: str | None = Field(default=None, max_length=30)
    # Vínculo com o catálogo interno (products-service) e contexto do anúncio
    sku_id: int | None = Field(
        default=None, index=True, description="Local SKU that originated this listing"
    )
    product_id: int | None = Field(
        default=None, index=True, description="Local product that originated this listing"
    )
    category_id: str | None = Field(
        default=None, max_length=50, description="Mercado Livre leaf category ID"
    )
    condition: str | None = Field(default=None, max_length=10, description="new | used")
    description: str | None = Field(
        default=None, description="Plain text description sent to Mercado Livre"
    )
    attributes: Optional[Dict] = Field(
        default=None, sa_column=Column(postgresql.JSONB, nullable=True)
    )
    raw_payload: Optional[Dict] = Field(
        default=None, sa_column=Column(postgresql.JSONB, nullable=True)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
        nullable=False,
    )
    last_synced_at: datetime | None = Field(default=None)
