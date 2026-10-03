"""
Rotas de API para Orders do sales-service.

Endpoints:
  - GET /api/v1/orders - Lista pedidos com filtros
  - POST /api/v1/orders - Cria pedido manual (fallback)
  - GET /api/v1/orders/{order_id} - Busca pedido por ID
  - POST /api/v1/orders/webhook - Webhook fallback para pedidos
"""

import logging
import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models.order import Order
from app.schemas.order import OrderCreate, OrderRead
from app.schemas.integration import StreamEvent
from app.services.sales_engine import process_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderRead])
def list_orders(
    session: Session = Depends(get_session),
    user_id: Optional[UUID] = Query(None, description="Filtrar por tenant"),
    marketplace: Optional[str] = Query(None, description="Filtrar por marketplace"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    start_date: Optional[str] = Query(None, description="Data início (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Data fim (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
) -> list[Order]:
    """Lista pedidos com filtros opcionais."""
    query = select(Order)

    if user_id:
        query = query.where(Order.user_id == user_id)
    if marketplace:
        query = query.where(Order.marketplace == marketplace)
    if status:
        query = query.where(Order.status == status)
    if start_date:
        from datetime import datetime
        query = query.where(Order.ordered_at >= datetime.fromisoformat(start_date))
    if end_date:
        from datetime import datetime
        query = query.where(Order.ordered_at <= datetime.fromisoformat(end_date))

    query = query.order_by(Order.ordered_at.desc()).offset(offset).limit(limit)
    return list(session.exec(query).all())


@router.post("", response_model=OrderRead, status_code=201)
def create_order(
    payload: OrderCreate,
    session: Session = Depends(get_session),
) -> Order:
    """Cria um pedido manual (fallback para webhook)."""
    order = Order(
        user_id=uuid.uuid4(),  # Seria preenchido pelo auth
        **payload.model_dump(),
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: UUID,
    session: Session = Depends(get_session),
) -> Order:
    """Busca pedido por ID."""
    order = session.get(Order, order_id)
    if order is None:
        raise NotFoundError("Order")
    return order


@router.post("/webhook")
async def webhook_order(
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Webhook fallback para receber pedidos diretamente.
    Usado quando o fluxo via Redis Stream falha.
    """
    from app.schemas.integration import StreamEvent
    from app.services.sales_engine import process_batch

    body = await request.json()
    try:
        event = StreamEvent(**body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Payload inválido: {exc}")

    deltas = process_batch([(str(uuid.uuid4()), body)])
    return {"status": "ok", "deltas": deltas}