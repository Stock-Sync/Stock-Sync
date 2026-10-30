"""QuantityFlusher tests: batching, retries, drops."""

import json

import fakeredis.aioredis
import pytest
from app.streams.consts import PENDING_STOCK_KEY
from app.tasks.flusher import QuantityFlusher


class FakeCatalog:
    def __init__(self, skus=None):
        if skus is None:
            skus = {7: {"id": 7, "internal_sku": "SKU-1", "stock_quantity": 4}}
        self.skus = skus

    async def get_sku(self, sku_id, tenant_id=None):
        return self.skus.get(sku_id)


class FakeIntegrations:
    def __init__(self):
        self.updated: list[tuple[str, str, int]] = []
        self.fail_item_ids: set[str] = set()
        self.reject_item_ids: set[str] = set()

    async def update_item_quantity(self, tenant_id, item_id, quantity):
        if item_id in self.reject_item_ids:
            response = type("R", (), {"status_code": 409})()
            exc = RuntimeError("ML rejected")
            exc.response = response
            raise exc
        if item_id in self.fail_item_ids:
            raise RuntimeError("connection reset")
        self.updated.append((tenant_id, item_id, quantity))


@pytest.fixture()
async def redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


async def _enqueue(redis, tenant, item_id, sku_id=7):
    await redis.hset(
        PENDING_STOCK_KEY,
        f"{tenant}:{item_id}",
        json.dumps({"tenant_id": tenant, "ml_item_id": item_id, "sku_id": sku_id}),
    )


async def test_flush_updates_and_clears(redis):
    integrations = FakeIntegrations()
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-1")
    await _enqueue(redis, "t1", "MLB-2")

    result = await flusher.flush_once()

    assert result == {"flushed": 2, "failed": 0, "dropped": 0}
    # Both items got the CURRENT local stock (4), not a stale value.
    assert sorted(integrations.updated) == [
        ("t1", "MLB-1", 4),
        ("t1", "MLB-2", 4),
    ]
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_flush_keeps_entry_on_transient_failure(redis):
    integrations = FakeIntegrations()
    integrations.fail_item_ids.add("MLB-1")
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-1")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 1, "dropped": 0}
    # Entry kept for the next cycle.
    assert await redis.hlen(PENDING_STOCK_KEY) == 1

    # Failure resolved → next flush succeeds.
    integrations.fail_item_ids.clear()
    result = await flusher.flush_once()
    assert result == {"flushed": 1, "failed": 0, "dropped": 0}
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_flush_drops_permanently_rejected(redis):
    integrations = FakeIntegrations()
    integrations.reject_item_ids.add("MLB-9")
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-9")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 1}
    assert await redis.hlen(PENDING_STOCK_KEY) == 0
    assert integrations.updated == []


async def test_flush_drops_unmapped_and_malformed(redis):
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=FakeIntegrations()
    )
    await _enqueue(redis, "t1", "MLB-OK", sku_id=None)
    await redis.hset(PENDING_STOCK_KEY, "bad", "not-json")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 2}
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_flush_drops_deleted_sku(redis):
    integrations = FakeIntegrations()
    catalog = FakeCatalog(
        {
            7: {
                "id": 7,
                "internal_sku": "SKU-1",
                "stock_quantity": 4,
                "is_deleted": True,
            }
        }
    )
    flusher = QuantityFlusher(
        redis_client=redis, catalog=catalog, integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-1")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 1}
    assert integrations.updated == [("t1", "MLB-1", 0)]
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_flush_deleted_sku_drops_even_if_zeroing_fails(redis):
    integrations = FakeIntegrations()
    integrations.fail_item_ids.add("MLB-1")
    catalog = FakeCatalog(
        {
            7: {
                "id": 7,
                "internal_sku": "SKU-1",
                "stock_quantity": 4,
                "is_deleted": True,
            }
        }
    )
    flusher = QuantityFlusher(
        redis_client=redis, catalog=catalog, integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-1")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 1}
    assert integrations.updated == []
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_flush_empty_pending(redis):
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=FakeIntegrations()
    )
    assert await flusher.flush_once() == {"flushed": 0, "failed": 0, "dropped": 0}
