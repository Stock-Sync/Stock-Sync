"""
Schemas Pydantic para o sync-service.

Define a estrutura dos eventos consumidos do stream marketplaces:events
e dos eventos publicados no stream stock:updates.
"""

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Eventos consumidos do marketplaces:events ───────────────────────────────────

class MarketplaceEvent(BaseModel):
    """
    Estrutura canônica dos eventos publicados no Redis Stream `marketplaces:events`
    pelo integrations-service.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: Literal[
        "order.created",
        "order.updated",
        "order.cancelled",
        "item.updated",
        "stock.updated",
    ]
    source: Literal["mercadolivre", "shopee"]
    user_id: str = Field(..., description="user_id do tenant no SaaS.")
    external_seller_id: str = Field(..., description="seller_id ou shop_id no marketplace.")
    order_id: Optional[str] = Field(None, description="ID do pedido no marketplace.")
    item_id: Optional[str] = Field(None, description="ID do produto/anúncio no marketplace.")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Eventos publicados no stock:updates ────────────────────────────────────────

class StockUpdateEvent(BaseModel):
    """
    Estrutura dos eventos publicados no stream `stock:updates` pelo sync-service.
    Consumido pelo worker do integrations-service.
    """

    user_id: str
    platform: Literal["mercadolivre", "shopee"]
    sku: str
    item_id: str
    model_id: int = 0  # Para Shopee: model_id da variação (0 se sem variação)
    shop_id: Optional[int] = None  # Para Shopee: shop_id do vendedor
    quantity: int
    sync_reason: Literal["order_created", "order_updated", "order_cancelled", "item_updated", "manual"]
    original_event_id: str = Field(..., description="ID do evento original do marketplaces:events")


# ── Modelos para auditoria e tracking de sincronização ──────────────────────────

class SyncAuditLog(BaseModel):
    """
    Log de auditoria de sincronização para rastreamento e debugging.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    platform: Literal["mercadolivre", "shopee"]
    event_type: str
    order_id: Optional[str] = None
    item_id: Optional[str] = None
    sku: Optional[str] = None
    old_quantity: Optional[int] = None
    new_quantity: Optional[int] = None
    status: Literal["pending", "published", "failed", "completed"]
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class SyncStatusResponse(BaseModel):
    """Resposta de status de sincronização para API."""

    user_id: str
    platform: str
    pending_syncs: int
    last_sync_at: Optional[datetime] = None
    last_error: Optional[str] = None


# ── Request/Response para API manual de sync ────────────────────────────────────

class ManualSyncRequest(BaseModel):
    """Request para disparar sincronização manual de um item."""

    user_id: str
    platform: Literal["mercadolivre", "shopee"]
    sku: str
    item_id: str
    quantity: int
    model_id: int = 0
    shop_id: Optional[int] = None


class ManualSyncResponse(BaseModel):
    """Response para sincronização manual."""

    status: Literal["accepted", "failed"]
    message: str
    event_id: Optional[str] = None