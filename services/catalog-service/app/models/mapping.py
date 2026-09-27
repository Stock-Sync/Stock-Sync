from datetime import datetime, timezone
from sqlmodel import Field, SQLModel


class ProductPlatformMapping(SQLModel, table=True):
    """Maps internal catalog products to marketplace item IDs."""

    __tablename__ = "catalog_mapping"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, nullable=False, max_length=36)  # Tenant UUID as string
    platform: str = Field(max_length=30, nullable=False)  # "mercadolivre" or "shopee"
    external_item_id: str = Field(max_length=100, nullable=False)  # ML item_id or Shopee item_id
    external_model_id: int = Field(default=0, nullable=False)  # Shopee variation model_id
    product_id: int | None = Field(default=None, foreign_key="product.id", nullable=False)  # Links to product
    sku: str = Field(max_length=50, nullable=False)  # Internal StockSync SKU
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Note: Unique constraint is defined via __table_args__ for SQLAlchemy
    __table_args__ = (
        # Unique: one mapping per (platform, item, model, user)
        # For ML: external_model_id is usually 0
        # For Shopee: external_model_id distinguishes variations
        {"unique": ("platform", "external_item_id", "external_model_id", "user_id")},
    )