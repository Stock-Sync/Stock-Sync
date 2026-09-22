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


class PlatformMappingRead(PlatformMappingBase):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
