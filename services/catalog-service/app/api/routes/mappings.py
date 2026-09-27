from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.mapping import ProductPlatformMapping
from app.models.product import Product
from app.schemas.mapping import CatalogMapping, CatalogMappingCreate

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.get("/by-external-id", response_model=CatalogMapping)
def get_mapping_by_external_id(
    user_id: str = Query(..., description="Tenant UUID"),
    platform: str = Query(..., description="Marketplace platform: 'mercadolivre' or 'shopee'"),
    external_item_id: str = Query(..., description="Marketplace item ID (ML item_id or Shopee item_id)"),
    external_model_id: int = Query(0, description="Shopee variation model_id (0 if no variation)"),
    db: Session = Depends(get_session),
) -> CatalogMapping:
    """
    Get mapping by marketplace item ID.

    Used by sync-service to find internal SKU from ML item_id or Shopee item_id.
    """
    mapping = db.query(ProductPlatformMapping).filter(
        ProductPlatformMapping.user_id == user_id,
        ProductPlatformMapping.platform == platform,
        ProductPlatformMapping.external_item_id == external_item_id,
        ProductPlatformMapping.external_model_id == external_model_id,
        ProductPlatformMapping.is_active == True,
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Mapping not found for user_id={user_id}, "
                f"platform={platform}, item_id={external_item_id}"
            ),
        )

    return CatalogMapping.model_validate(mapping)


@router.post("/", response_model=CatalogMapping, status_code=201)
def create_mapping(
    mapping_data: CatalogMappingCreate,
    db: Session = Depends(get_session),
) -> CatalogMapping:
    """Create a new marketplace-to-SKU mapping."""
    # Check if mapping already exists
    existing = db.query(ProductPlatformMapping).filter(
        ProductPlatformMapping.user_id == mapping_data.user_id,
        ProductPlatformMapping.platform == mapping_data.platform,
        ProductPlatformMapping.external_item_id == mapping_data.external_item_id,
        ProductPlatformMapping.external_model_id == mapping_data.external_model_id,
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="Mapping already exists")

    # Verify product exists
    product = db.query(Product).filter(Product.id == mapping_data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Verify SKU matches
    if product.sku != mapping_data.sku:
        raise HTTPException(
            status_code=400,
            detail=f"SKU mismatch: product has SKU '{product.sku}', mapping provides '{mapping_data.sku}'",
        )

    mapping = ProductPlatformMapping(
        user_id=mapping_data.user_id,
        platform=mapping_data.platform,
        external_item_id=mapping_data.external_item_id,
        external_model_id=mapping_data.external_model_id,
        product_id=mapping_data.product_id,
        sku=mapping_data.sku,
        is_active=True,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return CatalogMapping.model_validate(mapping)


@router.get("/by-sku/{sku}", response_model=dict)
def get_product_by_sku(
    sku: str,
    db: Session = Depends(get_session),
) -> dict:
    """Get product by internal SKU (already existed, keep for compatibility)."""
    product = db.query(Product).filter(Product.sku == sku).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "price": product.price,
        "stock_quantity": product.stock_quantity,
        "created_at": product.created_at,
    }


@router.get("/", response_model=list[CatalogMapping])
def list_mappings(
    user_id: str | None = Query(None, description="Filter by tenant UUID"),
    platform: str | None = Query(None, description="Filter by platform"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_session),
) -> list[CatalogMapping]:
    """List all mappings with optional filters."""
    query = db.query(ProductPlatformMapping)

    if user_id:
        query = query.filter(ProductPlatformMapping.user_id == user_id)
    if platform:
        query = query.filter(ProductPlatformMapping.platform == platform)
    if is_active is not None:
        query = query.filter(ProductPlatformMapping.is_active == is_active)

    mappings = query.offset(offset).limit(limit).all()
    return [CatalogMapping.model_validate(m) for m in mappings]


@router.delete("/{mapping_id}", status_code=204)
def delete_mapping(
    mapping_id: int,
    db: Session = Depends(get_session),
) -> None:
    """Deactivate a mapping (soft delete)."""
    mapping = db.query(ProductPlatformMapping).filter(
        ProductPlatformMapping.id == mapping_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    mapping.is_active = False
    db.commit()