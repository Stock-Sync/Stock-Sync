from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig

from app.models.platform_mapping import Platform


class PlatformMappingBase(SQLModel):
    sku_id: int
    platform: Platform
    platform_sku: str = Field(max_length=100)
    platform_product_id: str | None = Field(default=None, max_length=100)
    platform_variant_id: str | None = Field(default=None, max_length=100)
    is_active: bool = True


class PlatformMappingCreate(PlatformMappingBase):
    pass


class PlatformMappingUpdate(SQLModel):
    platform_sku: str | None = Field(default=None, max_length=100)
    platform_product_id: str | None = Field(default=None, max_length=100)
    platform_variant_id: str | None = Field(default=None, max_length=100)
    is_active: bool | None = Field(default=None)


class PlatformMappingSoftDelete(SQLModel):
    """Bulk soft delete used by the listings reconciliation pull."""

    platform: Platform = Platform.mercadolivre
    platform_product_ids: list[str] = Field(default_factory=list)


class PlatformMappingInternalCreate(PlatformMappingBase):
    """Upsert payload used by integrations-service after publishing a listing."""

    platform_product_id: str = Field(min_length=1, max_length=100)


class PlatformMappingUnbind(SQLModel):
    """Unbind payload used when one or more listings disappear.

    ``platform_product_id`` is the Plan 7 single-listing contract;
    ``platform_product_ids`` is the batch form used by the reconciliation
    pull. Both are accepted so existing callers keep working.
    """

    platform_product_id: str | None = Field(default=None, max_length=100)
    platform_product_ids: list[str] = Field(default_factory=list, max_length=1000)
    reason: str = Field(default="listing_deleted", max_length=100)


class PlatformMappingRead(PlatformMappingBase):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    tenant_id: str
    is_deleted: bool
    deleted_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class PlatformMappingRelink(SQLModel):
    """Manual re-link payload for an existing marketplace listing."""

    sku_id: int
    platform: Platform = Platform.mercadolivre
    platform_sku: str = Field(max_length=100)
    platform_product_id: str = Field(min_length=1, max_length=100)
    platform_variant_id: str | None = Field(default=None, max_length=100)


class PlatformMappingWarning(SQLModel):
    code: str
    message: str


class PlatformMappingRelinkResponse(SQLModel):
    mapping: PlatformMappingRead
    warning: PlatformMappingWarning | None = None


class PlatformMappingStateUpdate(SQLModel):
    """Internal state sync driven by Mercado Livre lifecycle events."""

    platform: Platform = Platform.mercadolivre
    platform_product_id: str = Field(min_length=1, max_length=100)
    is_active: bool
    # Webhook event timestamp; older events never overwrite newer local state.
    event_timestamp: datetime | None = None
