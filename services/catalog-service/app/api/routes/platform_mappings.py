from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import SKU, PlatformMapping, Product
from app.schemas import PlatformMappingCreate, PlatformMappingRead

router = APIRouter(prefix="/platform-mappings", tags=["platform-mappings"])


@router.get("", response_model=list[PlatformMappingRead])
def list_platform_mappings(
    session: Session = Depends(get_session),
) -> list[PlatformMapping]:
    return list(session.exec(select(PlatformMapping)).all())


@router.post("", response_model=PlatformMappingRead, status_code=201)
def create_platform_mapping(
    payload: PlatformMappingCreate,
    session: Session = Depends(get_session),
) -> PlatformMapping:
    if session.get(SKU, payload.sku_id) is None:
        raise NotFoundError("SKU")
    mapping = PlatformMapping(**payload.model_dump())
    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    return mapping


@router.get("/{mapping_id}", response_model=PlatformMappingRead)
def get_platform_mapping(
    mapping_id: int, session: Session = Depends(get_session)
) -> PlatformMapping:
    mapping = session.get(PlatformMapping, mapping_id)
    if mapping is None:
        raise NotFoundError("PlatformMapping")
    return mapping


# ── Lookup endpoint for sync-service integration ──

@router.get("/by-external-id")
def get_mapping_by_external_id(
    user_id: str,
    platform: str,
    external_item_id: str,
    external_model_id: int = 0,
    session: Session = Depends(get_session),
):
    """
    Get mapping by marketplace item ID.
    Used by sync-service to find internal SKU from ML item_id or Shopee item_id.
    """
    from uuid import UUID
    user_uuid = UUID(user_id)
    
    # Join PlatformMapping -> SKU -> Product to get full info
    statement = (
        select(PlatformMapping, SKU, Product)
        .join(SKU, PlatformMapping.sku_id == SKU.id)
        .join(Product, SKU.product_id == Product.id)
        .where(PlatformMapping.user_id == user_uuid)
        .where(PlatformMapping.platform == platform)
        .where(PlatformMapping.platform_sku == external_item_id)
        .where(PlatformMapping.platform_variant_id == external_model_id)
        .where(PlatformMapping.is_active == True)
    )
    result = session.exec(statement).first()
    
    if not result:
        raise NotFoundError(
            f"Mapping not found for user_id={user_id}, "
            f"platform={platform}, item_id={external_item_id}"
        )
    
    mapping, sku_obj, product = result
    
    return {
        "id": str(mapping.id),
        "user_id": str(mapping.user_id),
        "platform": mapping.platform.value,
        "external_item_id": mapping.platform_sku,
        "external_model_id": mapping.platform_variant_id or 0,
        "product_id": str(product.id),
        "sku": sku_obj.internal_sku,
        "is_active": mapping.is_active,
        "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
        "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
    }
