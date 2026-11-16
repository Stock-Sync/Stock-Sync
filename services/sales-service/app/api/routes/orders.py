"""Orders API: tenant-filtered history + internal ingestion from sync-service."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.api.deps import get_internal_tenant_id, get_tenant_id
from app.db.session import get_session
from app.models import Order
from app.schemas import OrderCreate, OrderListResponse, OrderRead

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


@router.get("", response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(get_tenant_id),
    session: Session = Depends(get_session),
) -> OrderListResponse:
    """Sales history of the authenticated tenant (newest first)."""
    total = session.exec(
        select(func.count())
        .select_from(Order)
        .where(Order.tenant_id == tenant_id)
    ).one()
    statement = (
        select(Order)
        .where(Order.tenant_id == tenant_id)
        .order_by(Order.ordered_at.desc(), Order.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(session.exec(statement).all())
    return OrderListResponse(items=items, total=total, page=page, limit=limit)


@router.post("/internal", response_model=OrderRead, status_code=201)
def upsert_order(
    payload: OrderCreate,
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
) -> Order:
    """Record a processed sale (idempotent upsert keyed by the unique constraint).

    sync-service may retry delivery (at-least-once stream semantics), so the
    same (tenant, marketplace, order, item) tuple updates the existing row
    instead of duplicating it.

    Two concurrent deliveries can both miss the initial SELECT and race on the
    INSERT. The unique constraint is the source of truth: on ``IntegrityError``
    we roll back, re-select the winning row and apply the payload to it.
    """
    if payload.tenant_id and payload.tenant_id != tenant_id:
        raise HTTPException(
            status_code=409,
            detail="tenant_id in payload does not match the request tenant",
        )

    statement = select(Order).where(
        Order.tenant_id == tenant_id,
        Order.marketplace == payload.marketplace,
        Order.marketplace_order_id == payload.marketplace_order_id,
        Order.marketplace_item_id == payload.marketplace_item_id,
    )
    order = session.exec(statement).first()

    if order is None:
        order = Order(
            tenant_id=tenant_id,
            marketplace=payload.marketplace,
            marketplace_order_id=payload.marketplace_order_id,
            marketplace_item_id=payload.marketplace_item_id,
        )
        session.add(order)

    data = payload.model_dump(exclude_unset=True)
    data.pop("tenant_id", None)
    for key, value in data.items():
        setattr(order, key, value)
    if payload.ordered_at is not None:
        order.ordered_at = payload.ordered_at
    order.tenant_id = tenant_id
    order.updated_at = datetime.now(UTC)

    session.add(order)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent delivery inserted the same unique tuple first.
        session.rollback()
        order = session.exec(statement).first()
        if order is None:
            # Not a duplicate we can recover from: surface the original error.
            raise
        data = payload.model_dump(exclude_unset=True)
        data.pop("tenant_id", None)
        for key, value in data.items():
            setattr(order, key, value)
        if payload.ordered_at is not None:
            order.ordered_at = payload.ordered_at
        order.tenant_id = tenant_id
        order.updated_at = datetime.now(UTC)
        session.add(order)
        session.commit()

    session.refresh(order)
    # Returning 201 also for updates keeps the client logic simple; the
    # response body always reflects the final stored state.
    return order
