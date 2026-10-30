import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings
from app.core.redis import EVENT_ITEMS_CHANGED, EVENT_ORDER_CREATED, publish_event

router = APIRouter(prefix="/api/v1/integrations/webhooks", tags=["webhooks"])

logger = logging.getLogger(__name__)

# Topics we forward to the sync stream. "orders" is the legacy topic name and
# "orders_v2" is what Mercado Livre sends nowadays — accept both.
ORDER_TOPICS = {"orders", "orders_v2"}
ITEM_TOPICS = {"items"}


class WebhookNotification(BaseModel):
    user_id: int
    resource: str
    topic: str
    received: str
    sent: str
    attempts: int
    id: str


def _verify_signature(raw_body: bytes, x_signature: str | None) -> bool:
    """Validate ML's X-Signature (HMAC-SHA256 of the raw body).

    Mercado Livre signs notifications with the webhook secret configured in the
    app panel. When no secret is configured we accept the notification (with a
    warning log) so local development keeps working.
    """
    if not settings.ml_webhook_secret:
        logger.warning("ml_webhook_signature_skipped_no_secret")
        return True
    if not x_signature:
        return False
    expected = hmac.new(
        settings.ml_webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, x_signature.lower())


@router.post("/mercadolivre")
async def ml_webhook(
    request: Request,
    x_signature: str | None = Header(None),
):
    """Receive Mercado Livre notifications and forward them to Redis Streams.

    Thin forwarder: validates the signature, maps the topic to an event type
    and XADDs it to the ``stocksync:events`` stream. All fetching of full
    order/item details and business processing happens in sync-service.
    A non-2xx response here makes ML retry the notification later.
    """
    raw_body = await request.body()
    if not _verify_signature(raw_body, x_signature):
        logger.warning("ml_webhook_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        notification = WebhookNotification.model_validate_json(raw_body)
    except Exception:
        logger.warning("ml_webhook_malformed_payload")
        raise HTTPException(status_code=400, detail="Malformed notification") from None

    logger.info(
        "mercadolivre_webhook_received",
        extra={
            "user_id": notification.user_id,
            "resource": notification.resource,
            "topic": notification.topic,
            "notification_id": notification.id,
        },
    )

    if notification.topic in ITEM_TOPICS and notification.resource.startswith("/items/"):
        event_type = EVENT_ITEMS_CHANGED
    elif notification.topic in ORDER_TOPICS and notification.resource.startswith(
        ("/orders/", "/orders_v2/")
    ):
        event_type = EVENT_ORDER_CREATED
    else:
        # Unknown topic: acknowledge and ignore (ML stops retrying).
        logger.info(
            "ml_webhook_ignored_topic",
            extra={"topic": notification.topic, "resource": notification.resource},
        )
        return {"status": "ignored"}

    event_id = await publish_event(
        event_type,
        {
            "ml_user_id": notification.user_id,
            "resource": notification.resource,
            "topic": notification.topic,
            "notification_id": notification.id,
        },
    )
    if event_id is None:
        # Redis down → 500 so Mercado Livre retries the notification later.
        raise HTTPException(status_code=503, detail="Event queue unavailable")

    return {"status": "queued", "event_id": event_id}
