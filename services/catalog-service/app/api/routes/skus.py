from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import case, update
from sqlmodel import Session, select

from app.api.deps import get_tenant_id
from app.core.errors import NotFoundError
from app.core.redis import publish_stock_adjust
from app.db.session import get_session
from app.models import SKU, PlatformMapping, Product
from app.schemas import SKUAdjust, SKUAdjustRead, SKUCreate, SKURead, SKUUpdate

router = APIRouter()


def _get_sku_or_404(
    session: Session,
    sku_id: int,
    tenant_id: str,
    include_deleted: bool = False,
) -> SKU:
    sku = session.get(SKU, sku_id)
    if sku is None or sku.tenant_id != tenant_id:
        raise NotFoundError("SKU")
    if not include_deleted and sku.is_deleted:
        raise NotFoundError("SKU")
    return sku


@router.get("", response_model=list[SKURead])
def list_skus(
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> list[SKU]:
    statement = select(SKU).where(
        SKU.tenant_id == tenant_id,
        SKU.is_deleted.is_(False),
    )
    return list(session.exec(statement).all())


@router.post("", response_model=SKURead, status_code=201)
def create_sku(
    payload: SKUCreate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> SKU:
    product = session.get(Product, payload.product_id)
    if product is None or product.tenant_id != tenant_id or product.is_deleted:
        raise NotFoundError("Product")
    sku = SKU(**payload.model_dump(), tenant_id=tenant_id)
    session.add(sku)
    session.commit()
    session.refresh(sku)
    if sku.stock_quantity:
        publish_stock_adjust(
            sku.id,
            sku.internal_sku,
            0,
            sku.stock_quantity,
            "product_create",
            tenant_id=tenant_id,
        )
    return sku


@router.get("/{sku_id}", response_model=SKURead)
def get_sku(
    sku_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> SKU:
    # Deleted SKUs stay readable by id so sales/history records keep working.
    return _get_sku_or_404(session, sku_id, tenant_id, include_deleted=True)


@router.put("/{sku_id}", response_model=SKURead)
def update_sku(
    sku_id: int,
    payload: SKUUpdate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> SKU:
    sku = _get_sku_or_404(session, sku_id, tenant_id)
    data = payload.model_dump(exclude_unset=True)
    if "product_id" in data and data["product_id"] is not None:
        product = session.get(Product, data["product_id"])
        if product is None or product.tenant_id != tenant_id or product.is_deleted:
            raise NotFoundError("Product")
    previous_quantity = sku.stock_quantity
    for key, value in data.items():
        setattr(sku, key, value)
    session.add(sku)
    session.commit()
    session.refresh(sku)
    if sku.stock_quantity != previous_quantity:
        publish_stock_adjust(
            sku.id,
            sku.internal_sku,
            previous_quantity,
            sku.stock_quantity,
            "catalog_update",
        )
    return sku


@router.post("/{sku_id}/adjust", response_model=SKUAdjustRead)
def adjust_sku_stock(
    sku_id: int,
    payload: SKUAdjust,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> SKUAdjustRead:
    """Atomically increase/decrease stock (clamped at 0) and emit a stream event.

    The UPDATE computes the new quantity in SQL so concurrent adjustments
    never lose updates, and the stock_adjust event lets sync-service push the
    new quantity to every linked marketplace listing.
    """
    sku = _get_sku_or_404(session, sku_id, tenant_id)

    previous_quantity = sku.stock_quantity
    new_quantity_expr = case(
        (SKU.stock_quantity + payload.delta < 0, 0),
        else_=SKU.stock_quantity + payload.delta,
    )
    result = session.execute(
        update(SKU)
        .where(SKU.id == sku_id)
        .values(stock_quantity=new_quantity_expr, updated_at=datetime.now(UTC))
        .returning(SKU.stock_quantity, SKU.internal_sku)
    )
    new_quantity, internal_sku = result.one()
    session.commit()

    clamped = previous_quantity + payload.delta < 0
    publish_stock_adjust(
        sku_id,
        internal_sku,
        previous_quantity,
        new_quantity,
        payload.source,
        tenant_id=tenant_id,
    )
    return SKUAdjustRead(
        sku_id=sku_id,
        internal_sku=internal_sku,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        clamped=clamped,
    )


@router.delete("/{sku_id}", status_code=204)
def delete_sku(
    sku_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> None:
    """Soft delete the SKU and deactivate its marketplace mappings.

    Idempotent: deleting an already-deleted SKU still returns 204.
    """
    now = datetime.now(UTC)
    sku = _get_sku_or_404(session, sku_id, tenant_id, include_deleted=True)

    sku.is_deleted = True
    sku.updated_at = now
    session.add(sku)

    mappings = session.exec(
        select(PlatformMapping).where(
            PlatformMapping.sku_id == sku_id,
            PlatformMapping.tenant_id == tenant_id,
        )
    ).all()
    for mapping in mappings:
        mapping.is_active = False
        mapping.updated_at = now
        session.add(mapping)

    session.commit()
