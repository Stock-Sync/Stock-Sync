"""
Schemas Pydantic para validação de entrada/saída do integrations-service.

Separação clara entre DTOs de API (o que entra/sai das rotas),
payloads de webhooks e a estrutura dos eventos do Redis Streams.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── OAuth / Auth ──────────────────────────────────────────────────────────────

class AuthURLResponse(BaseModel):
    """Resposta do endpoint GET /auth/{platform}/url."""

    platform: str
    auth_url: str


class CallbackRequest(BaseModel):
    """Body do endpoint POST /auth/{platform}/callback."""

    code: str = Field(..., description="Authorization code retornado pelo marketplace.")
    state: str | None = Field(
        None,
        description="user_id do tenant, passado como state no início do fluxo OAuth.",
    )
    # Shopee envia shop_id no redirect — necessário para exchange_code
    shop_id: int | None = Field(None, description="shop_id retornado pela Shopee no callback.")


class IntegrationOut(BaseModel):
    """DTO público de uma integração — tokens nunca são expostos."""

    id: uuid.UUID
    user_id: uuid.UUID
    platform: str
    external_seller_id: str
    access_token_expires_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Webhook Mercado Livre ─────────────────────────────────────────────────────

class WebhookMLPayload(BaseModel):
    """
    Estrutura das notificações de webhook enviadas pelo Mercado Livre.

    Referência: https://developers.mercadolibre.com.br/pt_br/notificacoes
    """

    _id: str | None = None  # ID da notificação (nem sempre enviado)
    resource: str = Field(..., description="Recurso afetado, ex: '/orders/2000001234'.")
    user_id: int = Field(..., description="seller_id do ML que originou o evento.")
    topic: str = Field(..., description="Tópico do evento, ex: 'orders_v2', 'items'.")
    application_id: int | None = None
    attempts: int | None = None
    sent: str | None = None
    received: str | None = None


# ── Webhook Shopee ────────────────────────────────────────────────────────────

class WebhookShopeePayload(BaseModel):
    """
    Estrutura base das notificações push da Shopee.

    Referência: https://open.shopee.com/developer-guide/257
    """

    code: int = Field(..., description="Tipo do evento (1=Order Status, 3=Shop Update, etc.).")
    timestamp: int = Field(..., description="Unix timestamp do evento.")
    shop_id: int = Field(..., description="ID da loja na Shopee.")
    data: dict[str, Any] = Field(default_factory=dict, description="Payload específico do evento.")


# ── Redis Streams ─────────────────────────────────────────────────────────────

class StreamEvent(BaseModel):
    """
    Estrutura canônica dos eventos publicados no Redis Stream `marketplaces:events`.

    Consumido pelo sync-service e sales-service.
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
    order_id: str | None = Field(None, description="ID do pedido no marketplace.")
    item_id: str | None = Field(None, description="ID do produto/anúncio no marketplace.")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    # Payload adicional livre para dados específicos da plataforma
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Worker: Stock Update ──────────────────────────────────────────────────────

class StockUpdateEvent(BaseModel):
    """
    Estrutura dos eventos lidos do stream `stock:updates` (publicados pelo sync-service).
    """

    user_id: str
    platform: Literal["mercadolivre", "shopee"]
    sku: str
    item_id: str
    # Para Shopee: model_id da variação (0 se sem variação)
    model_id: int = 0
    # Para Shopee: shop_id do vendedor
    shop_id: int | None = None
    quantity: int
