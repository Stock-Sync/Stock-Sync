"""Redis Streams producer shared with catalog-service and sync-service.

Webhook notifications received from Mercado Livre are forwarded to the
``stocksync:events`` stream. sync-service owns the consumer group and all
business processing; the webhook receiver stays a thin, validated forwarder.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from functools import lru_cache

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

STREAM_KEY = "stocksync:events"

EVENT_ITEMS_CHANGED = "items_changed"
EVENT_ORDER_CREATED = "order_created"


@lru_cache
def _client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


async def publish_event(event_type: str, payload: dict) -> str | None:
    """XADD an event to the shared stream. Returns the event id or None."""
    event_id = f"{event_type}:{uuid.uuid4()}"
    try:
        await _client().xadd(
            STREAM_KEY,
            {
                "event_type": event_type,
                "event_id": event_id,
                "payload": json.dumps(payload),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        logger.info(
            "integration_event_published",
            extra={"event_type": event_type, "event_id": event_id},
        )
        return event_id
    except RedisError as exc:
        logger.error(
            "integration_event_publish_failed",
            extra={"event_type": event_type, "error": str(exc)},
        )
        return None
