"""Consumer tests: dedupe, dispatch, ack and dead-letter behavior."""

import json

import fakeredis.aioredis
import pytest
from app.models import SyncEvent
from app.streams.consts import (
    CONSUMER_GROUP,
    DEAD_STREAM_KEY,
    EVENT_ITEMS_CHANGED,
    EVENT_ORDER_CREATED,
    EVENT_STOCK_ADJUST,
    STREAM_KEY,
)
from app.streams.consumer import EventConsumer


class FakeProcessor:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.fail = False
        self.integrations = self

    async def resolve_tenant_by_ml_user(self, ml_user_id: int):
        return {"tenant_id": "tenant-1"}

    async def process_order(self, tenant_id: str, order_id: str):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append(("order", {"tenant_id": tenant_id, "order_id": order_id}))

    async def process_stock_adjust(self, payload: dict):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append(("stock_adjust", payload))

    async def get_item(self, tenant_id: str, item_id: str) -> dict:
        return {"id": item_id, "title": f"Item {item_id}", "available_quantity": 10}

    async def upsert_local_item(self, tenant_id: str, item_data: dict) -> dict:
        self.calls.append(("upsert_local_item", item_data))
        return {"item_id": item_data.get("id"), "sku_id": None}


@pytest.fixture()
async def fake_redis():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.flushall()
    await redis.aclose()


def _make_consumer(db_session, processor, redis):
    return EventConsumer(
        redis_client=redis,
        session_factory=lambda: db_session,
        processor_factory=lambda session: processor,
    )


async def _publish(redis, event_type, payload, event_id):
    await redis.xadd(
        STREAM_KEY,
        {
            "event_type": event_type,
            "event_id": event_id,
            "payload": json.dumps(payload),
        },
    )


@pytest.mark.asyncio
async def test_stock_adjust_is_processed_and_acked(db_session, fake_redis):
    processor = FakeProcessor()
    consumer = _make_consumer(db_session, processor, fake_redis)
    await consumer.ensure_group()
    await _publish(
        fake_redis, EVENT_STOCK_ADJUST, {"sku_id": 1, "new_quantity": 5}, "sa-1"
    )

    await consumer._read_once(block_ms=1)

    assert processor.calls == [("stock_adjust", {"sku_id": 1, "new_quantity": 5})]
    pending = await fake_redis.xpending(STREAM_KEY, CONSUMER_GROUP)
    assert pending["pending"] == 0
    record = db_session.query(SyncEvent).filter_by(dedupe_key="sa-1").one()
    assert record.status == "processed"


@pytest.mark.asyncio
async def test_order_event_resolves_tenant_and_fetches_order(db_session, fake_redis):
    processor = FakeProcessor()
    consumer = _make_consumer(db_session, processor, fake_redis)
    await consumer.ensure_group()
    await _publish(
        fake_redis,
        EVENT_ORDER_CREATED,
        {"ml_user_id": 42, "resource": "/orders/99"},
        "ord-1",
    )

    await consumer._read_once(block_ms=1)

    assert processor.calls == [
        ("order", {"tenant_id": "tenant-1", "order_id": "99"})
    ]


@pytest.mark.asyncio
async def test_item_changed_is_synced_locally(db_session, fake_redis):
    processor = FakeProcessor()
    consumer = _make_consumer(db_session, processor, fake_redis)
    await consumer.ensure_group()
    await _publish(
        fake_redis,
        EVENT_ITEMS_CHANGED,
        {"ml_user_id": 42, "resource": "/items/MLB123"},
        "itm-1",
    )

    await consumer._read_once(block_ms=1)

    assert processor.calls == [("upsert_local_item", {"id": "MLB123", "title": "Item MLB123", "available_quantity": 10})]
    pending = await fake_redis.xpending(STREAM_KEY, CONSUMER_GROUP)
    assert pending["pending"] == 0
    record = db_session.query(SyncEvent).filter_by(dedupe_key="itm-1").one()
    assert record.status == "processed"


@pytest.mark.asyncio
async def test_redelivered_event_is_skipped(db_session, fake_redis):
    processor = FakeProcessor()
    consumer = _make_consumer(db_session, processor, fake_redis)
    await consumer.ensure_group()
    await _publish(fake_redis, EVENT_STOCK_ADJUST, {"sku_id": 1, "new_quantity": 3}, "sa-dup")

    await consumer._read_once(block_ms=1)
    assert len(processor.calls) == 1

    # Simulate a redelivery of the same event_id (new stream entry).
    await _publish(fake_redis, EVENT_STOCK_ADJUST, {"sku_id": 1, "new_quantity": 3}, "sa-dup")
    await consumer._read_once(block_ms=1)

    # Processed only once — second delivery ACKed without dispatching.
    assert len(processor.calls) == 1


@pytest.mark.asyncio
async def test_failure_retries_then_dead_letters(db_session, fake_redis, monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "stream_max_attempts", 2)
    # Reclaim immediately so the test doesn't wait the 30s visibility timeout.
    monkeypatch.setattr(config_module.settings, "stream_claim_min_idle_ms", 0)

    processor = FakeProcessor()
    processor.fail = True
    consumer = _make_consumer(db_session, processor, fake_redis)
    await consumer.ensure_group()
    await _publish(fake_redis, EVENT_STOCK_ADJUST, {"sku_id": 9, "new_quantity": 1}, "sa-fail")

    await consumer._read_once(block_ms=1)
    record = db_session.query(SyncEvent).filter_by(dedupe_key="sa-fail").one()
    assert record.status == "retry"
    assert record.retry_count == 1

    # Reclaim (entry is still pending) and fail again → dead letter.
    await consumer._claim_stale()
    record = db_session.query(SyncEvent).filter_by(dedupe_key="sa-fail").one()
    assert record.status == "failed"
    assert record.retry_count == 2

    dead = await fake_redis.xrevrange(DEAD_STREAM_KEY)
    assert len(dead) == 1
    pending = await fake_redis.xpending(STREAM_KEY, CONSUMER_GROUP)
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_unknown_event_type_is_dropped(db_session, fake_redis):
    processor = FakeProcessor()
    consumer = _make_consumer(db_session, processor, fake_redis)
    await consumer.ensure_group()
    await _publish(fake_redis, "mystery", {"a": 1}, "m-1")

    await consumer._read_once(block_ms=1)

    assert processor.calls == []
    pending = await fake_redis.xpending(STREAM_KEY, CONSUMER_GROUP)
    assert pending["pending"] == 0
