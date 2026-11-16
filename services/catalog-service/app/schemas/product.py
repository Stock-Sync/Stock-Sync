from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig

from app.schemas.sku import SKURead


class ProductBase(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    pictures: list[str] = Field(default_factory=list)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    pictures: list[str] | None = None


class ProductRead(ProductBase):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    tenant_id: str
    is_description_truncated: bool = Field(default=False)
    has_active_listing: bool = Field(default=False)
    pictures: list[str] = Field(default_factory=list)
    is_deleted: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime


class ProductCompositeCreate(SQLModel):
    """Plan 11: create a Product and its single SKU atomically."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    internal_sku: str = Field(min_length=1, max_length=50)
    price: Decimal = Field(ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    pictures: list[str] = Field(default_factory=list)


class ProductCompositeUpdate(SQLModel):
    """Plan 11: update the Product and its single SKU in one transaction."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    internal_sku: str | None = Field(default=None, min_length=1, max_length=50)
    price: Decimal | None = Field(default=None, ge=0)
    stock_quantity: int | None = Field(default=None, ge=0)
    pictures: list[str] | None = None


class ProductCompositeRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    tenant_id: str
    name: str
    description: str | None
    is_description_truncated: bool
    pictures: list[str]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    has_active_listing: bool = Field(default=False)
    sku: SKURead