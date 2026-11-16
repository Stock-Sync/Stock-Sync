from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class Platform(str, Enum):
    mercadolivre = "mercado_livre"
    shopee = "shopee"


class PlatformMapping(SQLModel, table=True):
    # Exactly one *active* mapping per listing and per SKU/platform_sku pair.
    # The filters make soft-deleted rows (history) invisible to both indexes.
    __table_args__ = (
        Index(
            "ix_platform_mapping_tenant_product_active",
            "tenant_id",
            "platform",
            "platform_product_id",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "ix_platform_mapping_tenant_sku_active",
            "tenant_id",
            "sku_id",
            "platform",
            "platform_sku",
            unique=True,
            postgresql_where=text("is_deleted IS FALSE"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(max_length=36, index=True)
    sku_id: int = Field(foreign_key="sku.id", index=True)
    platform: Platform = Field(index=True)
    platform_sku: str = Field(max_length=100)
    platform_product_id: str | None = Field(default=None, max_length=100)
    platform_variant_id: str | None = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)
    # Soft delete: the mapping disappears from the UI but is preserved so past
    # sales (which reference the SKU) and audits keep working.
    is_deleted: bool = Field(default=False, index=True)
    deleted_reason: str | None = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
