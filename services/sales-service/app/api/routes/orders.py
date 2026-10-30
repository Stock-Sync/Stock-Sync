"""Orders API: public history listing + internal ingestion from sync-service."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, func, select

from app.api.deps import require_internal_secret
from app.db.session import get_session
from app.models import Order
from app.schemas import OrderCreate, OrderListResponse, OrderRead

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


@router.get("", response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> OrderListResponse:
    """Sales history (newest first) — consumed by the frontend Vendas page."""
    total = session.exec(select(func.count()).select_from(Order)).one()
    statement = (
        select(Order)
        .order_by(Order.ordered_at.desc(), Order.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(session.exec(statement).all())
    return OrderListResponse(items=items, total=total, page=page, limit=limit)


@router.post("/internal", response_model=OrderRead, status_code=201)
def upsert_order(
    payload: OrderCreate,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
) -> Order:
    """Record a processed sale (idempotent upsert keyed by the unique constraint).

    sync-service may retry delivery (at-least-once stream semantics), so the
    same (marketplace, order, item) tuple updates the existing row instead of
    duplicating it.
    """
    statement = select(Order).where(
        Order.marketplace == payload.marketplace,
        Order.marketplace_order_id == payload.marketplace_order_id,
        Order.marketplace_item_id == payload.marketplace_item_id,
    )
    order = session.exec(statement).first()
    is_new = order is None

    if order is None:
        order = Order(
            marketplace=payload.marketplace,
            marketplace_order_id=payload.marketplace_order_id,
            marketplace_item_id=payload.marketplace_item_id,
        )
        session.add(order)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(order, key, value)
    if payload.ordered_at is not None:
        order.ordered_at = payload.ordered_at
    order.updated_at = datetime.now(UTC)

    session.add(order)
    session.commit()
    session.refresh(order)
    # Returning 201 also for updates keeps the client logic simple; the
    # response body always reflects the final stored state.
    _ = is_new
    return order
