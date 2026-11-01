from datetime import datetime
from typing import Any, List, Optional

from typing_extensions import Annotated
from pydantic import ConfigDict, Field, StringConstraints, field_serializer
from sqlmodel import Field as SQLModelField
from sqlmodel import SQLModel
from sqlmodel.main import SQLModelConfig

from app.models.marketplace_credential import Marketplace


def mask_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}***{token[-4:]}"


# =============================================================================
# Marketplace Credential Schemas
# =============================================================================


class MarketplaceCredentialCreate(SQLModel):
    marketplace: Marketplace
    account_name: str = SQLModelField(min_length=1, max_length=120)
    access_token: str = SQLModelField(min_length=1, max_length=2000)
    refresh_token: str | None = SQLModelField(default=None, max_length=2000)
    expires_at: datetime | None = SQLModelField(default=None)
    ml_user_id: int | None = SQLModelField(default=None)


class MarketplaceCredentialUpdate(SQLModel):
    account_name: str | None = SQLModelField(default=None, min_length=1, max_length=120)
    access_token: str | None = SQLModelField(default=None, min_length=1, max_length=2000)
    refresh_token: str | None = SQLModelField(default=None, max_length=2000)
    expires_at: datetime | None = SQLModelField(default=None)
    is_active: bool | None = SQLModelField(default=None)
    ml_user_id: int | None = SQLModelField(default=None)


class MarketplaceCredentialRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    tenant_id: str
    marketplace: Marketplace
    account_name: str
    ml_user_id: int | None
    ml_nickname: str | None
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("access_token")
    def mask_access_token(self, value: str) -> str:
        return mask_token(value) or ""

    @field_serializer("refresh_token")
    def mask_refresh_token(self, value: str | None) -> str | None:
        return mask_token(value)


class CredentialResponse(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    marketplace: str
    account_name: str
    ml_user_id: int | None
    ml_nickname: str | None
    is_active: bool
    expires_at: str | None
    created_at: str
    updated_at: str


# =============================================================================
# Category Schemas
# =============================================================================


class CategoryAttributeValue(SQLModel):
    """Mercado Livre attribute definition.

    Extra fields from the ML payload (filterable, hidden, customizable, ...)
    are preserved so the UI can react to future metadata without a backend
    release.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    type: str = "string"  # "string", "number", "list", "boolean"
    value_type: str = "string"  # "string", "number", "list", "boolean", "dict"
    required: bool = False
    min_length: int | None = None
    max_length: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    number_unit: str | None = None  # e.g. "Centímetros", "Gramos"
    allowed_values: List[dict[str, Any]] | None = None  # [{"id": "...", "name": "..."}]
    allowed_units: List[dict[str, Any]] | None = None
    tags: dict[str, Any] | None = None  # {"required": true, "catalog_required": true, ...}


class CategoryAttributesResponse(SQLModel):
    category_id: str
    category_name: str
    attributes: List[CategoryAttributeValue]


class CategoryResult(SQLModel):
    """Leaf category returned by Domain Discovery or a tree node."""

    category_id: str
    category_name: str
    domain_id: str | None = None
    domain_name: str | None = None
    # Tree navigation (fallback path): present on /categories/{id} responses
    children_categories: List[dict[str, Any]] | None = None
    path_from_root: List[dict[str, Any]] | None = None


class DomainDiscoveryResult(SQLModel):
    category_id: str
    category_name: str
    domain_id: str | None = None
    domain_name: str | None = None


class MLCategoryAttributeResponse(SQLModel):
    """Cached category attributes response."""

    category_id: str
    category_name: str
    attributes: List[CategoryAttributeValue]
    cached_at: datetime
    expires_at: datetime


# =============================================================================
# Item Schemas (Mercado Livre / User Products v3)
# =============================================================================


class ItemAttribute(SQLModel):
    id: str
    value_name: str | None = None
    value_id: str | None = None
    # Numeric attributes (dimensions/weight) must also carry the raw number and
    # unit separately; ``value_name`` holds only the numeric part.
    value_struct: dict[str, Any] | None = None


class ItemPicture(SQLModel):
    source: str  # Cloudinary URL; ML downloads it and returns secure_url


class ItemSaleTerm(SQLModel):
    id: str
    value_name: str | None = None
    value_id: str | None = None


class ItemChild(SQLModel):
    """Variation (child) in the User Products v3 model."""

    attributes: List[ItemAttribute] = SQLModelField(default_factory=list)
    available_quantity: int = SQLModelField(ge=0)
    price: float = SQLModelField(gt=0)
    seller_custom_field: str | None = SQLModelField(default=None, max_length=100)
    pictures: List[ItemPicture] | None = None


# String constraints for pattern validation
ListingTypeStr = Annotated[str, StringConstraints(pattern=r"^(gold_pro|gold_special)$")]
ConditionStr = Annotated[str, StringConstraints(pattern=r"^(new|used)$")]
CurrencyStr = Annotated[str, StringConstraints(pattern=r"^BRL$")]
BuyingModeStr = Annotated[str, StringConstraints(pattern=r"^(buy_it_now|auction|classified)$")]
StatusStr = Annotated[str, StringConstraints(pattern=r"^(active|paused|closed)$")]

ML_TITLE_MAX_LENGTH = 60


class ItemCreateRequest(SQLModel):
    """Payload for creating a listing via the Mercado Livre items endpoint."""

    title: str | None = SQLModelField(default=None, max_length=ML_TITLE_MAX_LENGTH)
    category_id: str = SQLModelField(min_length=1)  # must be a leaf category
    family_name: str | None = SQLModelField(default=None, max_length=255)
    listing_type_id: ListingTypeStr = "gold_special"  # gold_pro=Premium, gold_special=Classic
    condition: ConditionStr = "new"
    currency_id: CurrencyStr = "BRL"
    buying_mode: BuyingModeStr = "buy_it_now"
    price: float = SQLModelField(gt=0)
    available_quantity: int = SQLModelField(default=0, ge=0)
    pictures: List[ItemPicture] = SQLModelField(min_length=1, max_length=12)
    attributes: List[ItemAttribute] = SQLModelField(default_factory=list)
    sale_terms: List[ItemSaleTerm] | None = None
    description: str | None = None  # sent as a separate POST /items/{id}/description call
    children: List[ItemChild] = SQLModelField(default_factory=list)  # optional variations
    # Local catalog link (products-service) so the listing hub can join back
    sku_id: int | None = None
    product_id: int | None = None


class ItemUpdateRequest(SQLModel):
    """Payload for updating a listing (only editable fields).

    ``title``/``family_name`` and other immutable fields are intentionally not
    accepted: Mercado Livre's User Products v3 rejects them on ``PUT /items``.
    """

    price: float | None = SQLModelField(default=None, gt=0)
    available_quantity: int | None = SQLModelField(default=None, ge=0)
    status: StatusStr | None = None
    pictures: List[ItemPicture] | None = None
    description: str | None = None
    attributes: List[ItemAttribute] | None = None
    sale_terms: List[ItemSaleTerm] | None = None
    children: List[ItemChild] | None = None


class ItemDescriptionRequest(SQLModel):
    """POST /items/{item_id}/description payload (v3 uses plain_text)."""

    plain_text: str = SQLModelField(min_length=1)


class ItemDescriptionResponse(SQLModel):
    text: str | None = None
    plain_text: str | None = None


class ItemPictureResponse(SQLModel):
    secure_url: str
    size: str | None = None
    max_size: str | None = None
    quality: str | None = None


class ItemChildResponse(SQLModel):
    id: str | None = None
    attributes: List[ItemAttribute] = SQLModelField(default_factory=list)
    available_quantity: int
    price: float
    seller_custom_field: str | None = None
    pictures: List[ItemPictureResponse] | None = None


class ItemResponse(SQLModel):
    """Response for item list/detail."""

    model_config = SQLModelConfig(from_attributes=True)

    id: str  # ML item_id (e.g., MLB123456)
    user_product_id: str | None = None
    tenant_id: str
    ml_user_id: int | None = None
    marketplace: str
    title: str
    price: float
    available_quantity: int
    status: str | None = None
    thumbnail: str | None = None
    permalink: str | None = None
    family_name: str | None = None
    listing_type_id: str | None = None
    category_id: str | None = None
    condition: str | None = None
    sku_id: int | None = None
    product_id: int | None = None
    attributes: List[ItemAttribute] | List[dict[str, Any]] | None = None
    children: List[ItemChildResponse] | None = None
    pictures: List[ItemPictureResponse] | None = None
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime | None = None


class ItemListResponse(SQLModel):
    """Paginated response for item listing."""

    items: List[ItemResponse]
    page: int
    limit: int
    total: int
    total_pages: int


class MLPictureUploadResponse(SQLModel):
    """Response from ML POST /pictures."""

    secure_url: str
    size: str | None = None
    max_size: str | None = None
    quality: str | None = None
