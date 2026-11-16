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
DEDUPE_KEY_PREFIX = "webhook:dedupe:"
OAUTH_STATE_KEY_PREFIX = "oauth:state:"
ML_REFRESH_LOCK_KEY_PREFIX = "lock:mercadolivre:refresh:"

# Atomically delete the lock only when the caller still owns it. Without this,
# a process whose TTL expired could delete a lock acquired by another process.
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

EVENT_ITEMS_CHANGED = "items_changed"
EVENT_ORDER_CREATED = "order_created"


@lru_cache
def _client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


async def publish_event(event_type: str, payload: dict, event_id: str | None = None) -> str | None:
    """XADD an event to the shared stream.

    ``event_id`` doubles as the stream dedupe key in sync-service, so webhook
    deliveries pass a deterministic value (derived from the ML notification)
    to make redeliveries idempotent end to end.
    """
    event_id = event_id or f"{event_type}:{uuid.uuid4()}"
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


async def is_notification_seen(dedupe_key: str) -> bool:
    """Return True when this notification was already accepted recently.

    Best-effort: if Redis is unavailable we report "not seen" and let the
    publish attempt surface the outage (the endpoint then returns 503 so ML
    retries).
    """
    try:
        return bool(await _client().exists(f"{DEDUPE_KEY_PREFIX}{dedupe_key}"))
    except RedisError as exc:
        logger.error(
            "webhook_dedupe_check_failed",
            extra={"dedupe_key": dedupe_key, "error": str(exc)},
        )
        return False


async def mark_notification_seen(dedupe_key: str, ttl_seconds: int | None = None) -> None:
    """Remember a notification id for the retry window (best-effort)."""
    ttl = ttl_seconds or settings.ml_webhook_dedup_ttl_seconds
    try:
        await _client().set(f"{DEDUPE_KEY_PREFIX}{dedupe_key}", "1", ex=ttl)
    except RedisError as exc:
        # The event is already queued; sync-service dedupes by event_id, so a
        # cache failure must not turn a successful delivery into an error.
        logger.error(
            "webhook_dedupe_mark_failed",
            extra={"dedupe_key": dedupe_key, "error": str(exc)},
        )


async def save_oauth_state(nonce: str, tenant_id: str, ttl_seconds: int) -> None:
    """Store the OAuth nonce so it can be consumed exactly once.

    Failures propagate: the caller must abort the OAuth flow with 503 instead
    of issuing a state that cannot be validated later.
    """
    try:
        await _client().set(
            f"{OAUTH_STATE_KEY_PREFIX}{nonce}",
            tenant_id,
            ex=ttl_seconds,
        )
    except RedisError as exc:
        logger.error(
            "oauth_state_store_failed",
            extra={"error": str(exc)},
        )
        raise


async def pop_oauth_state(nonce: str) -> str | None:
    """Atomically read and delete the OAuth nonce (single use)."""
    try:
        return await _client().getdel(f"{OAUTH_STATE_KEY_PREFIX}{nonce}")
    except RedisError as exc:
        logger.error(
            "oauth_state_consume_failed",
            extra={"error": str(exc)},
        )
        raise


async def acquire_refresh_lock(key: str, token: str, ttl_seconds: int) -> bool:
    """Try to take a refresh lock exactly once (``SET NX PX``).

    ``RedisError`` is propagated so the caller can decide how to degrade when
    Redis is unavailable (the token refresh itself must keep working).
    """
    acquired = await _client().set(
        key,
        token,
        nx=True,
        px=int(ttl_seconds * 1000),
    )
    return bool(acquired)


async def release_refresh_lock(key: str, token: str) -> bool:
    """Release the lock only if ``token`` is still its owner.

    The comparison and delete run atomically in Redis (Lua), so an expired
    owner can never remove a lock that was legitimately re-acquired by someone
    else. Failures are best-effort: the TTL eventually reclaims the lock.
    """
    try:
        released = await _client().eval(_RELEASE_LOCK_SCRIPT, 1, key, token)
        return bool(released)
    except RedisError as exc:
        logger.error(
            "ml_refresh_lock_release_failed",
            extra={"lock_key": key, "error": str(exc)},
        )
        return False
