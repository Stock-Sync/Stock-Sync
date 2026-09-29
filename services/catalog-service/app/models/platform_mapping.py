from datetime import UTC, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class Platform(str, Enum):
    mercadolivre = "mercado_livre"
    shopee = "shopee"


class PlatformMapping(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="sku.id", index=True)
    platform: Platform = Field(index=True)
    platform_sku: str = Field(max_length=100)
    platform_product_id: str | None = Field(default=None, max_length=100)
    platform_variant_id: str | None = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
