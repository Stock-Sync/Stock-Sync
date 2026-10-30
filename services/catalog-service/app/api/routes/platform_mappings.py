from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.api.deps import get_tenant_id
from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import SKU, Platform, PlatformMapping
from app.schemas import PlatformMappingCreate, PlatformMappingRead

router = APIRouter()


def _get_mapping_or_404(session: Session, mapping_id: int, tenant_id: str) -> PlatformMapping:
    mapping = session.get(PlatformMapping, mapping_id)
    if mapping is None or mapping.tenant_id != tenant_id:
        raise NotFoundError("PlatformMapping")
    return mapping


@router.get("", response_model=list[PlatformMappingRead])
def list_platform_mappings(
    platform: Platform | None = None,
    platform_sku: str | None = Query(default=None, max_length=100),
    platform_product_id: str | None = Query(default=None, max_length=100),
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> list[PlatformMapping]:
    """List mappings for the current tenant, optionally filtered."""
    statement = select(PlatformMapping).where(PlatformMapping.tenant_id == tenant_id)
    if platform is not None:
        statement = statement.where(PlatformMapping.platform == platform)
    if platform_sku is not None:
        statement = statement.where(PlatformMapping.platform_sku == platform_sku)
    if platform_product_id is not None:
        statement = statement.where(
            PlatformMapping.platform_product_id == platform_product_id
        )
    return list(session.exec(statement).all())


@router.post("", response_model=PlatformMappingRead, status_code=201)
def create_platform_mapping(
    payload: PlatformMappingCreate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> PlatformMapping:
    sku = session.get(SKU, payload.sku_id)
    if sku is None or sku.tenant_id != tenant_id or sku.is_deleted:
        raise NotFoundError("SKU")
    mapping = PlatformMapping(**payload.model_dump(), tenant_id=tenant_id)
    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    return mapping


@router.get("/{mapping_id}", response_model=PlatformMappingRead)
def get_platform_mapping(
    mapping_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> PlatformMapping:
    return _get_mapping_or_404(session, mapping_id, tenant_id)


@router.delete("/{mapping_id}", status_code=204)
def delete_platform_mapping(
    mapping_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
):
    mapping = _get_mapping_or_404(session, mapping_id, tenant_id)
    session.delete(mapping)
    session.commit()
