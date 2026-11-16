from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.api.deps import get_internal_tenant_id, get_tenant_id
from app.core.errors import NotFoundError
from app.core.redis import publish_stock_adjust
from app.db.session import get_session
from app.models import SKU, PlatformMapping, Product
from app.schemas import (
    SKUAdjust,
    SKUAdjustRead,
    SKUCreate,
    SKULookupRead,
    SKURead,
    SKUUpdate,
)
from app.services.sku_rules import (
    ensure_internal_sku_editable,
    ensure_sku_uniqueness,
)

router = APIRouter()
# Mounted by ``app.main`` under ``/api/v1/internal/skus``.
internal_router = APIRouter()


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
    ensure_sku_uniqueness(
        session,
        tenant_id=tenant_id,
        product_id=product.id,
        internal_sku=payload.internal_sku,
    )
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
    target_product_id = sku.product_id
    if "product_id" in data and data["product_id"] is not None:
        product = session.get(Product, data["product_id"])
        if product is None or product.tenant_id != tenant_id or product.is_deleted:
            raise NotFoundError("Product")
        target_product_id = product.id

    new_internal_sku = data.get("internal_sku")
    ensure_internal_sku_editable(
        session,
        sku_id=sku.id,
        tenant_id=tenant_id,
        current_internal_sku=sku.internal_sku,
        new_internal_sku=new_internal_sku,
    )
    ensure_sku_uniqueness(
        session,
        tenant_id=tenant_id,
        product_id=target_product_id,
        internal_sku=(
            new_internal_sku
            if new_internal_sku is not None
            else sku.internal_sku
        ),
        exclude_sku_id=sku.id,
    )

    previous_quantity = sku.stock_quantity
    for key, value in data.items():
        setattr(sku, key, value)
    # Plan 10: keep updated_at accurate on every catalog mutation.
    sku.updated_at = datetime.now(UTC)
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
            tenant_id=tenant_id,
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

    The row is read with ``SELECT ... FOR UPDATE`` so ``previous_quantity``,
    ``new_quantity`` and ``clamped`` describe the same serialized transition.
    Computing the new value in Python (instead of reading it before an atomic
    UPDATE) is what makes the response safe to use for reversal: a concurrent
    adjustment must wait for this transaction before it can read the row, so
    it sees the quantity written here and reports the correct ``deducted``
    amount.

    The ``stock_adjust`` event lets sync-service push the new quantity to every
    linked marketplace listing.
    """
    statement = (
        select(SKU)
        .where(SKU.id == sku_id, SKU.tenant_id == tenant_id)
        .with_for_update()
        # Ignore any stale copy already present in the session's identity map.
        .execution_options(populate_existing=True)
    )
    sku = session.exec(statement).first()
    if sku is None or sku.is_deleted:
        raise NotFoundError("SKU")

    previous_quantity = sku.stock_quantity
    internal_sku = sku.internal_sku
    new_quantity = max(0, previous_quantity + payload.delta)
    clamped = previous_quantity + payload.delta < 0

    sku.stock_quantity = new_quantity
    sku.updated_at = datetime.now(UTC)
    session.add(sku)
    session.commit()

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


# =============================================================================
# Internal (service-to-service) endpoints
# =============================================================================


def _sku_lookup_payload(sku: SKU, product: Product | None) -> SKULookupRead:
    product_is_deleted = product is None or product.is_deleted
    return SKULookupRead(
        id=sku.id,
        tenant_id=sku.tenant_id,
        product_id=sku.product_id,
        internal_sku=sku.internal_sku,
        price=sku.price,
        stock_quantity=sku.stock_quantity,
        is_deleted=sku.is_deleted,
        created_at=sku.created_at,
        updated_at=sku.updated_at,
        product_is_deleted=product_is_deleted,
        mappable=not sku.is_deleted and not product_is_deleted,
    )


@internal_router.get("/lookup", response_model=SKULookupRead)
def lookup_internal_sku(
    internal_sku: str,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_internal_tenant_id),
) -> SKULookupRead:
    """Resolve a platform SKU to an internal SKU, including deletion state.

    Listing auto-matching calls this endpoint and only creates a mapping when
    ``mappable`` is true, i.e. both the SKU and its product are active.
    """
    sku = session.exec(
        select(SKU)
        .where(
            SKU.tenant_id == tenant_id,
            SKU.internal_sku == internal_sku,
        )
        .order_by(SKU.id.desc())
    ).first()
    if sku is None:
        raise NotFoundError("SKU")
    product = session.get(Product, sku.product_id)
    return _sku_lookup_payload(sku, product)
