"""
Endpoints de recebimento de webhooks dos marketplaces.

REGRA FUNDAMENTAL: Estes endpoints devem responder em < 100ms.
Nenhuma chamada síncrona para APIs externas ou queries pesadas ao banco.
Pipeline: Validar → Checar Idempotência → Resolver user_id → Publicar no Stream → 200 OK.

POST /webhooks/mercadolivre — Notificações assíncronas do Mercado Livre
POST /webhooks/shopee       — Notificações push da Shopee
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.integration import TenantIntegration
from app.schemas.integration import (
    StreamEvent,
    WebhookMLPayload,
    WebhookShopeePayload,
)
from app.core.security import verify_shopee_signature
from app.services.redis_stream import is_duplicate_event, publish_event

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_user_id(db: Session, platform: str, external_seller_id: str) -> str | None:
    """
    Resolve o user_id interno do SaaS a partir do external_seller_id.

    Query leve por índice — não viola o requisito de < 100ms.
    Retorna None se não houver integração ativa para o seller.
    """
    integration = (
        db.query(TenantIntegration)
        .filter_by(platform=platform, external_seller_id=external_seller_id)
        .first()
    )
    return str(integration.user_id) if integration else None


# ── POST /webhooks/mercadolivre ───────────────────────────────────────────────

@router.post("/mercadolivre")
async def webhook_mercadolivre(
    payload: WebhookMLPayload,
    db: Session = Depends(get_session),
):
    """
    Recebe notificações de eventos do Mercado Livre (orders_v2, items, etc.).

    O ML envia o notification ID no campo `_id` (ou resource + topic como chave única).
    Responde 200 imediatamente após publicar no stream.
    """
    # Extrai identificador único do recurso (ex: '/orders/2000001234567890' → '2000001234567890')
    resource_id = payload.resource.rstrip("/").split("/")[-1]
    idempotency_key = f"webhook:ml:{payload.topic}:{resource_id}"

    # Checa idempotência — retorna 200 sem processar se já foi visto
    if is_duplicate_event(idempotency_key):
        logger.info(
            "Evento duplicado ignorado — key=%s topic=%s", idempotency_key, payload.topic
        )
        return {"status": "duplicate", "detail": "Evento já processado."}

    # Resolve user_id a partir do seller_id do ML
    external_seller_id = str(payload.user_id)
    user_id = _resolve_user_id(db, "mercadolivre", external_seller_id)

    if not user_id:
        logger.warning(
            "Webhook ML recebido para seller_id=%s sem integração ativa. Ignorando.",
            external_seller_id,
        )
        return {"status": "ignored", "detail": "Sem integração ativa para este seller."}

    # Mapeia o tópico ML para o event_type canônico
    event_type_map = {
        "orders_v2": "order.created",
        "shipments": "order.updated",
        "items": "item.updated",
    }
    event_type = event_type_map.get(payload.topic, "order.updated")

    event = StreamEvent(
        event_type=event_type,
        source="mercadolivre",
        user_id=user_id,
        external_seller_id=external_seller_id,
        order_id=resource_id if payload.topic == "orders_v2" else None,
        item_id=resource_id if payload.topic == "items" else None,
        metadata={"resource": payload.resource, "topic": payload.topic},
    )

    publish_event(event.model_dump())
    logger.info(
        "Evento ML publicado no stream — event_type=%s seller_id=%s order_id=%s",
        event_type, external_seller_id, event.order_id,
    )
    return {"status": "ok"}


# ── POST /webhooks/shopee ─────────────────────────────────────────────────────

@router.post("/shopee")
async def webhook_shopee(
    request: Request,
    payload: WebhookShopeePayload,
    authorization: str | None = Header(None),
    db: Session = Depends(get_session),
):
    """
    Recebe notificações push da Shopee (Order Status, Shop Update, etc.).

    A Shopee assina o payload com HMAC-SHA256 e envia no header 'Authorization'.
    Valida a assinatura antes de processar.
    """
    # Valida assinatura HMAC da Shopee
    body_bytes = await request.body()
    if not authorization or not verify_shopee_signature(body_bytes, authorization):
        logger.warning(
            "Webhook Shopee rejeitado — assinatura inválida ou ausente. shop_id=%s",
            payload.shop_id,
        )
        raise HTTPException(status_code=401, detail="Assinatura inválida.")

    # Chave de idempotência: código do evento + shop_id + timestamp
    idempotency_key = f"webhook:shopee:{payload.code}:{payload.shop_id}:{payload.timestamp}"

    if is_duplicate_event(idempotency_key):
        logger.info("Evento Shopee duplicado ignorado — key=%s", idempotency_key)
        return {"status": "duplicate", "detail": "Evento já processado."}

    # Resolve user_id a partir do shop_id
    external_seller_id = str(payload.shop_id)
    user_id = _resolve_user_id(db, "shopee", external_seller_id)

    if not user_id:
        logger.warning(
            "Webhook Shopee recebido para shop_id=%s sem integração ativa. Ignorando.",
            external_seller_id,
        )
        return {"status": "ignored", "detail": "Sem integração ativa para este shop."}

    # code 1 = Order Status Push (novo pedido / atualização)
    # code 3 = Shop Update
    event_type_map = {
        1: "order.created",
        2: "order.updated",
        3: "item.updated",
    }
    event_type = event_type_map.get(payload.code, "order.updated")

    order_id = payload.data.get("ordersn") or payload.data.get("order_sn")

    event = StreamEvent(
        event_type=event_type,
        source="shopee",
        user_id=user_id,
        external_seller_id=external_seller_id,
        order_id=order_id,
        metadata={"shopee_code": payload.code, "raw_data": payload.data},
    )

    publish_event(event.model_dump())
    logger.info(
        "Evento Shopee publicado no stream — event_type=%s shop_id=%s",
        event_type, external_seller_id,
    )
    return {"status": "ok"}
