from datetime import datetime
from pydantic import BaseModel, Field


class CatalogMappingBase(BaseModel):
    user_id: str = Field(..., description="Tenant UUID as string")
    platform: str = Field(..., max_length=30, description="'mercadolivre' or 'shopee'")
    external_item_id: str = Field(..., max_length=100, description="ML item_id or Shopee item_id")
    external_model_id: int = Field(default=0, description="Shopee variation model_id (0 if no variation)")
    product_id: int = Field(..., description="Catalog-service product ID")
    sku: str = Field(..., max_length=50, description="Internal StockSync SKU")
    is_active: bool = Field(default=True, description="Whether mapping is active")


class CatalogMappingCreate(CatalogMappingBase):
    """Schema for creating a new mapping."""
    pass


class CatalogMapping(CatalogMappingBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True