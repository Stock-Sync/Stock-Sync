import hashlib
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.redis import (
    EVENT_ITEMS_CHANGED,
    EVENT_ORDER_CREATED,
    is_notification_seen,
    mark_notification_seen,
    publish_event,
)

router = APIRouter(prefix="/api/v1/integrations/webhooks", tags=["webhooks"])

logger = logging.getLogger(__name__)

# Topics we forward to the sync stream. "orders" is the legacy topic name and
# "orders_v2" is what Mercado Livre sends nowadays — accept both.
ORDER_TOPICS = {"orders", "orders_v2"}
ITEM_TOPICS = {"items"}


class WebhookNotification(BaseModel):
    """Mercado Livre notification envelope.

    ML does not sign notifications, and the payload is only a change signal:
    sync-service always refetches the authoritative resource from the ML API.
    Most topics (including ``orders_v2`` and ``items``) omit the notification
    id entirely, so every field except the routing ones is optional.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    user_id: int
    resource: str
    topic: str
    application_id: int | None = None
    attempts: int | None = None
    sent: str | None = None
    received: str | None = None
    # Some topics send ``id``, others ``_id``; both are optional.
    notification_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("id", "_id"),
    )


def _check_webhook_secret(provided: str | None) -> None:
    """Validate the shared secret embedded in the callback URL.

    Mercado Livre has no request signature, so the callback URL itself is the
    shared secret. In production (``DEBUG=false``) an unconfigured secret is a
    deployment error and is rejected instead of silently accepting anything.
    """
    configured = settings.ml_webhook_secret
    if not configured:
        if settings.debug:
            logger.warning("ml_webhook_secret_not_configured_dev")
            return
        logger.error("ml_webhook_secret_not_configured")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if not provided or not hmac.compare_digest(provided, configured):
        logger.warning("ml_webhook_invalid_secret")
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


def _dedupe_key(notification: WebhookNotification) -> str:
    """Stable idempotency key for a notification.

    Prefer ML's notification id. When it is absent (orders_v2/items), fall back
    to the resource identity: refetching the resource always yields the latest
    state, so collapsing redeliveries for the same seller/resource is safe.
    """
    if notification.notification_id:
        identity = f"id:{notification.notification_id}"
    else:
        identity = f"{notification.topic}:{notification.user_id}:{notification.resource}"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"mlwh:{notification.topic}:{digest}"


async def _handle_notification(request: Request, provided_secret: str | None) -> dict:
    _check_webhook_secret(provided_secret)

    raw_body = await request.body()
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
            "notification_id": notification.notification_id,
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

    dedupe_key = _dedupe_key(notification)
    if await is_notification_seen(dedupe_key):
        logger.info(
            "ml_webhook_duplicate",
            extra={
                "topic": notification.topic,
                "resource": notification.resource,
                "dedupe_key": dedupe_key,
            },
        )
        return {"status": "duplicate"}

    # The deterministic event id is also sync-service's SyncEvent.dedupe_key,
    # so concurrent redeliveries that slip past the cache check are still only
    # processed once.
    event_id = await publish_event(
        event_type,
        {
            "ml_user_id": notification.user_id,
            "resource": notification.resource,
            "topic": notification.topic,
            "notification_id": notification.notification_id,
            # Used by sync-service to discard out-of-order items_changed
            # deliveries (Plan 9). ML does not sign notifications; this is a
            # best-effort ordering hint, never an authentication signal.
            "sent": notification.sent,
            "received": notification.received,
        },
        event_id=dedupe_key,
    )
    if event_id is None:
        # Redis down → 503 so Mercado Livre retries the notification later.
        raise HTTPException(status_code=503, detail="Event queue unavailable")

    await mark_notification_seen(dedupe_key)
    return {"status": "queued", "event_id": event_id}


@router.post("/mercadolivre")
async def ml_webhook_without_secret(request: Request) -> dict:
    """Legacy callback URL without the secret (allowed only in DEBUG)."""
    return await _handle_notification(request, None)


@router.post("/mercadolivre/{secret}")
async def ml_webhook(request: Request, secret: str) -> dict:
    """Receive Mercado Livre notifications and forward them to Redis Streams.

    Thin forwarder: validates the shared secret, maps the topic to an event
    type and XADDs it to the ``stocksync:events`` stream. All fetching of full
    order/item details and business processing happens in sync-service.
    """
    return await _handle_notification(request, secret)
