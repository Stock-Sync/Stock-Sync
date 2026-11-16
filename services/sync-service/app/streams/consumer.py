"""Redis Streams consumer: reads events and dispatches to processors.

Reliability model (at-least-once):
- entries are read with XREADGROUP under the ``sync-service`` consumer group
- XACK only after successful processing
- failed entries stay pending; XAUTOCLAIM sweeps them after a visibility
  timeout so a crashed consumer doesn't lose events
- after ``stream_max_attempts`` failures the entry moves to the dead-letter
  stream (``stocksync:dead``) with its SyncEvent row marked ``failed``

Idempotency: every event carries a dedupe_key persisted in SyncEvent (unique
constraint); redelivered entries that already processed are ACKed and skipped.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from app.core.config import settings
from app.core.redis import get_redis
from app.models import SyncEvent
from app.services.order_processor import OrderProcessor
from app.streams.consts import (
    CONSUMER_GROUP,
    CONSUMER_NAME,
    DEAD_STREAM_KEY,
    EVENT_ITEMS_CHANGED,
    EVENT_ORDER_CREATED,
    EVENT_STOCK_ADJUST,
    KNOWN_EVENT_TYPES,
    STREAM_KEY,
)
from redis.exceptions import ResponseError
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

logger = logging.getLogger(__name__)


def _event_timestamp(payload: dict) -> datetime | None:
    """Best-effort parse of the ML notification timestamp.

    ML sends ``sent``/``received`` as ISO-8601 strings. They are only an
    ordering hint (not signed), so malformed values are ignored.
    """
    raw = payload.get("sent") or payload.get("received")
    if not raw or not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class EventConsumer:
    def __init__(self, redis_client=None, session_factory=None, processor_factory=None):
        self.redis = redis_client or get_redis()
        self._session_factory = session_factory
        self._processor_factory = processor_factory
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------------ #
    # setup
    # ------------------------------------------------------------------ #

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="$", mkstream=True)
            logger.info("stream_group_created", extra={"group": CONSUMER_GROUP})
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    # ------------------------------------------------------------------ #
    # main loop
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        await self.ensure_group()
        logger.info("consumer_started", extra={"consumer": CONSUMER_NAME})
        while not self._stopping.is_set():
            try:
                await self._claim_stale()
                await self._read_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("consumer_loop_error")
                await asyncio.sleep(1)

    async def stop(self) -> None:
        self._stopping.set()

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    async def _read_once(self, count: int = 25, block_ms: int = 5000) -> None:
        response = await self.redis.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={STREAM_KEY: ">"},
            count=count,
            block=block_ms,
        )
        for _stream, entries in response or []:
            for entry_id, fields in entries:
                await self._handle_entry(entry_id, fields)

    async def _claim_stale(self) -> None:
        """Reclaim entries abandoned by a dead consumer."""
        try:
            _next, entries, _deleted = await self.redis.xautoclaim(
                name=STREAM_KEY,
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                min_idle_time=settings.stream_claim_min_idle_ms,
                start_id="0-0",
                count=10,
            )
        except ResponseError:
            return  # older Redis without XAUTOCLAIM
        for entry_id, fields in entries or []:
            logger.info("entry_reclaimed", extra={"entry_id": entry_id})
            await self._handle_entry(entry_id, fields)

    async def _handle_entry(self, entry_id: str, fields: dict) -> None:
        event_type = fields.get("event_type", "")
        dedupe_key = fields.get("event_id")
        try:
            payload = json.loads(fields.get("payload", "{}"))
        except json.JSONDecodeError:
            payload = {}

        if event_type not in KNOWN_EVENT_TYPES:
            logger.warning("unknown_event_type", extra={"event_type": event_type})
            await self.redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
            return

        # Plan 10: tenant_id is mandatory in stock events. A missing tenant is
        # not retryable (the producer will never add it later), so the message
        # goes straight to the dead-letter stream instead of poisoning retries.
        if event_type == EVENT_STOCK_ADJUST and not payload.get("tenant_id"):
            logger.critical(
                "stock_adjust_missing_tenant",
                extra={
                    "entry_id": entry_id,
                    "event_id": dedupe_key,
                    "payload": payload,
                },
            )
            await self.redis.xadd(DEAD_STREAM_KEY, dict(fields), maxlen=1000)
            await self.redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
            return

        record = self._get_or_create_event(event_type, dedupe_key, payload)
        if record.status == "processed":
            # Already handled (redelivery) — just acknowledge.
            await self.redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
            return

        try:
            await self._dispatch(event_type, payload)
        except Exception as exc:  # noqa: BLE001
            record.retry_count += 1
            record.error_message = str(exc)[:2000]
            if record.retry_count >= settings.stream_max_attempts:
                record.status = "failed"
                self._commit(record)
                await self.redis.xadd(
                    DEAD_STREAM_KEY, dict(fields), maxlen=1000
                )
                await self.redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
                logger.error(
                    "event_dead_lettered",
                    extra={"entry_id": entry_id, "error": str(exc)},
                )
            else:
                record.status = "retry"
                self._commit(record)
                # Leave un-ACKed so XAUTOCLAIM picks it up after the timeout.
            return

        record.status = "processed"
        record.processed_at = datetime.now(UTC)
        self._commit(record)
        await self.redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)

    async def _dispatch(self, event_type: str, payload: dict) -> None:
        session = self._open_session()
        try:
            processor = self._make_processor(session)
            if event_type == EVENT_ORDER_CREATED:
                await self._process_order_event(processor, payload)
            elif event_type == EVENT_STOCK_ADJUST:
                await processor.process_stock_adjust(payload)
            elif event_type == EVENT_ITEMS_CHANGED:
                await self._process_item_changed(processor, payload)
            else:
                logger.info("event_noop", extra={"event_type": event_type})
        finally:
            session.close()

    async def _process_order_event(self, processor: OrderProcessor, payload: dict) -> None:
        ml_user_id = payload.get("ml_user_id")
        resource = payload.get("resource", "")
        order_id = resource.rstrip("/").split("/")[-1]
        if not ml_user_id or not order_id:
            raise ValueError(f"malformed order payload: {payload}")

        resolved = await processor.integrations.resolve_tenant_by_ml_user(int(ml_user_id))
        if resolved is None:
            raise ValueError(f"no credential for ml_user_id={ml_user_id}")
        await processor.process_order(resolved["tenant_id"], order_id)

    async def _process_item_changed(self, processor: OrderProcessor, payload: dict) -> None:
        """Sync a Mercado Livre item that changed externally (price, stock, status, ...).

        Fetches the full item from ML and upserts it into the local MarketplaceItem
        table so the platform reflects the latest state announced by the webhook.
        The notification timestamp is forwarded so integrations-service can
        discard an out-of-order delivery (Plan 9 stale-event protection).
        """
        ml_user_id = payload.get("ml_user_id")
        resource = payload.get("resource", "")
        item_id = resource.rstrip("/").split("/")[-1]
        if not ml_user_id or not item_id:
            raise ValueError(f"malformed item payload: {payload}")

        resolved = await processor.integrations.resolve_tenant_by_ml_user(int(ml_user_id))
        if resolved is None:
            raise ValueError(f"no credential for ml_user_id={ml_user_id}")

        item_data = await processor.integrations.get_item(resolved["tenant_id"], item_id)
        await processor.integrations.upsert_local_item(
            resolved["tenant_id"],
            item_data,
            event_timestamp=_event_timestamp(payload),
        )
        # Plan 12: mirror ML metadata into catalog Product/SKU (best-effort).
        try:
            await processor.mirror_metadata_from_ml(
                resolved["tenant_id"], item_data
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "metadata_mirror_failed",
                extra={"ml_item_id": item_id, "tenant_id": resolved["tenant_id"]},
            )

    # ------------------------------------------------------------------ #
    # DB helpers (kept small so tests can substitute a session factory)
    # ------------------------------------------------------------------ #

    def _open_session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from app.db.session import engine
        from sqlmodel import Session as SQLModelSession

        return SQLModelSession(engine)

    def _make_processor(self, session):
        if self._processor_factory is not None:
            return self._processor_factory(session)
        return OrderProcessor(session, redis_client=self.redis)

    def _get_or_create_event(
        self, event_type: str, dedupe_key: str | None, payload: dict
    ) -> SyncEvent:
        session = self._open_session()
        try:
            # Fast path: the event was already persisted by an earlier delivery.
            if dedupe_key:
                existing = session.exec(
                    select(SyncEvent).where(SyncEvent.dedupe_key == dedupe_key)
                ).first()
                if existing is not None:
                    return existing

            # Optimistic insert. Concurrent deliveries with the same dedupe_key
            # race here; the unique constraint picks a single winner.
            record = SyncEvent(event_type=event_type, dedupe_key=dedupe_key, payload=payload)
            session.add(record)
            try:
                session.commit()
                session.refresh(record)
                return record
            except IntegrityError:
                # PostgreSQL aborts the transaction; clear it before querying again.
                session.rollback()

                # Without a dedupe_key the failure is not a duplicate delivery, so
                # the original constraint violation must surface to the caller.
                if not dedupe_key:
                    raise

                logger.info(
                    "syncevent_dedupe_conflict",
                    extra={"dedupe_key": dedupe_key, "event_type": event_type},
                )

                existing = session.exec(
                    select(SyncEvent).where(SyncEvent.dedupe_key == dedupe_key)
                ).first()
                if existing is not None:
                    return existing

                # The concurrent winner rolled back before we could read its row.
                # Retry the insert exactly once so at-least-once delivery holds.
                fallback = SyncEvent(
                    event_type=event_type, dedupe_key=dedupe_key, payload=payload
                )
                session.add(fallback)
                try:
                    session.commit()
                    session.refresh(fallback)
                    return fallback
                except IntegrityError:
                    session.rollback()
                    raise
        finally:
            session.close()

    def _commit(self, record: SyncEvent) -> None:
        session = self._open_session()
        try:
            merged = session.merge(record)
            session.add(merged)
            session.commit()
        finally:
            session.close()
