"""Redis Streams producer for stock-change events.

Every stock mutation done through this service (SKU creation, update and the
atomic ``POST /skus/{id}/adjust``) is published to the ``stocksync:events``
stream so sync-service can react: propagate the new quantity to marketplaces
and keep its audit logs in sync.

Publishing is best-effort: a Redis outage must never fail the originating
request. The manual "Sincronizar" pull in the frontend re-heals any drift.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from functools import lru_cache

import redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

STREAM_KEY = "stocksync:events"

EVENT_STOCK_ADJUST = "stock_adjust"


@lru_cache
def _client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def publish_event(event_type: str, payload: dict) -> str | None:
    """XADD an event to the shared stream. Returns the entry id or None."""
    event_id = f"{event_type}:{uuid.uuid4()}"
    try:
        entry_id = _client().xadd(
            STREAM_KEY,
            {
                "event_type": event_type,
                "event_id": event_id,
                "payload": json.dumps(payload),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        logger.info(
            "stock_event_published",
            extra={"event_type": event_type, "entry_id": entry_id, "event_id": event_id},
        )
        return event_id
    except RedisError as exc:
        # Best-effort: never fail the caller's request because Redis is down.
        logger.warning(
            "stock_event_publish_failed",
            extra={"event_type": event_type, "error": str(exc)},
        )
        return None


def publish_stock_adjust(
    sku_id: int,
    internal_sku: str,
    previous_quantity: int,
    new_quantity: int,
    source: str,
    tenant_id: str | None = None,
) -> str | None:
    """Notify listeners that a SKU stock level changed."""
    return publish_event(
        EVENT_STOCK_ADJUST,
        {
            "sku_id": sku_id,
            "internal_sku": internal_sku,
            "previous_quantity": previous_quantity,
            "new_quantity": new_quantity,
            "source": source,
            "tenant_id": tenant_id,
        },
    )
