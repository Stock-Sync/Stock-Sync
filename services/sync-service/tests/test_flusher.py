"""QuantityFlusher tests: batching, retries, drops and Plan 10 guards."""

import json
import logging

import fakeredis.aioredis
import pytest
from app.streams.consts import PENDING_STOCK_KEY
from app.tasks.flusher import QuantityFlusher


class FakeCatalog:
    def __init__(self, skus=None, mappings=None):
        if skus is None:
            skus = {7: {"id": 7, "internal_sku": "SKU-1", "stock_quantity": 4}}
        self.skus = skus
        self.mappings = mappings or {}

    async def get_sku(self, sku_id, tenant_id=None):
        return self.skus.get(sku_id)

    async def find_mapping_by_product_id(
        self, item_id, tenant_id=None, include_deleted=False
    ):
        return self.mappings.get(
            item_id,
            {"item_id": item_id, "is_active": True, "is_deleted": False},
        )


class FakeIntegrations:
    def __init__(self, details=None):
        self.updated: list[tuple[str, str, int]] = []
        self.fail_item_ids: set[str] = set()
        self.reject_item_ids: set[str] = set()
        self.variation_item_ids: set[str] = set()
        self.details = details or {}
        self.detail_fail = False
        self.detail_calls: list[tuple[str, list[str]]] = []

    @staticmethod
    def _rejection(text: str):
        response = type("R", (), {"status_code": 409, "text": text})()
        exc = RuntimeError("ML rejected")
        exc.response = response
        return exc

    async def get_item_details_batch(self, tenant_id, item_ids):
        self.detail_calls.append((tenant_id, list(item_ids)))
        if self.detail_fail:
            raise RuntimeError("integrations down")
        return {
            item_id: self.details.get(
                item_id,
                {
                    "id": item_id,
                    "found": False,
                    "status": None,
                    "is_active": False,
                    "is_deleted": False,
                    "has_variations": False,
                },
            )
            for item_id in item_ids
        }

    async def update_item_quantity(self, tenant_id, item_id, quantity):
        if item_id in self.variation_item_ids:
            raise self._rejection("variations are not supported")
        if item_id in self.reject_item_ids:
            raise self._rejection("ML rejected")
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

    assert result == {"flushed": 2, "failed": 0, "dropped": 0, "skipped": 0}
    # Both items got the CURRENT local stock (4), not a stale value.
    assert sorted(integrations.updated) == [
        ("t1", "MLB-1", 4),
        ("t1", "MLB-2", 4),
    ]
    assert await redis.hlen(PENDING_STOCK_KEY) == 0
    # One batch enrichment call per tenant.
    assert integrations.detail_calls == [("t1", ["MLB-1", "MLB-2"])]


async def test_flush_keeps_entry_on_transient_failure(redis):
    integrations = FakeIntegrations()
    integrations.fail_item_ids.add("MLB-1")
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-1")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 1, "dropped": 0, "skipped": 0}
    # Entry kept for the next cycle.
    assert await redis.hlen(PENDING_STOCK_KEY) == 1

    # Failure resolved → next flush succeeds.
    integrations.fail_item_ids.clear()
    result = await flusher.flush_once()
    assert result == {"flushed": 1, "failed": 0, "dropped": 0, "skipped": 0}
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_flush_keeps_entries_when_details_enrichment_fails(redis):
    integrations = FakeIntegrations()
    integrations.detail_fail = True
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-1")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 1, "dropped": 0, "skipped": 0}
    assert await redis.hlen(PENDING_STOCK_KEY) == 1
    assert integrations.updated == []


async def test_flush_drops_permanently_rejected(redis):
    integrations = FakeIntegrations()
    integrations.reject_item_ids.add("MLB-9")
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-9")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 1, "skipped": 0}
    assert await redis.hlen(PENDING_STOCK_KEY) == 0
    assert integrations.updated == []


async def test_flush_drops_variation_rejection_with_warning(
    redis, caplog
):
    integrations = FakeIntegrations()
    integrations.variation_item_ids.add("MLB-VAR")
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-VAR")

    with caplog.at_level(logging.WARNING):
        result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 1, "skipped": 0}
    assert await redis.hlen(PENDING_STOCK_KEY) == 0
    assert any(
        record.message == "variation_stock_update_ignored"
        for record in caplog.records
    )


async def test_flush_drops_unmapped_and_malformed(redis):
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=FakeIntegrations()
    )
    await _enqueue(redis, "t1", "MLB-OK", sku_id=None)
    await redis.hset(PENDING_STOCK_KEY, "bad", "not-json")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 2, "skipped": 0}
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

    assert result == {"flushed": 0, "failed": 0, "dropped": 1, "skipped": 0}
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

    assert result == {"flushed": 0, "failed": 0, "dropped": 1, "skipped": 0}
    assert integrations.updated == []
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_flush_skips_inactive_or_deleted_mapping(redis):
    integrations = FakeIntegrations()
    catalog = FakeCatalog(
        mappings={
            "MLB-INACTIVE": {
                "item_id": "MLB-INACTIVE",
                "is_active": False,
                "is_deleted": False,
            },
            "MLB-DELETED": {
                "item_id": "MLB-DELETED",
                "is_active": False,
                "is_deleted": True,
            },
        }
    )
    flusher = QuantityFlusher(
        redis_client=redis, catalog=catalog, integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-INACTIVE")
    await _enqueue(redis, "t1", "MLB-DELETED")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 0, "skipped": 2}
    assert integrations.updated == []
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


@pytest.mark.parametrize("status", ["paused", "closed"])
async def test_flush_skips_paused_or_closed_listing(redis, status):
    integrations = FakeIntegrations(
        details={
            "MLB-1": {
                "id": "MLB-1",
                "found": True,
                "status": status,
                "is_active": False,
                "is_deleted": False,
                "has_variations": False,
            }
        }
    )
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-1")

    result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 0, "skipped": 1}
    assert integrations.updated == []
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_flush_skips_variation_listing_without_calling_ml(redis, caplog):
    integrations = FakeIntegrations(
        details={
            "MLB-VAR": {
                "id": "MLB-VAR",
                "found": True,
                "status": "active",
                "is_active": True,
                "is_deleted": False,
                "has_variations": True,
            }
        }
    )
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=integrations
    )
    await _enqueue(redis, "t1", "MLB-VAR")

    with caplog.at_level(logging.WARNING):
        result = await flusher.flush_once()

    assert result == {"flushed": 0, "failed": 0, "dropped": 0, "skipped": 1}
    assert integrations.updated == []
    assert any(
        record.message == "variation_stock_update_ignored"
        for record in caplog.records
    )


async def test_flush_empty_pending(redis):
    flusher = QuantityFlusher(
        redis_client=redis, catalog=FakeCatalog(), integrations=FakeIntegrations()
    )
    assert await flusher.flush_once() == {
        "flushed": 0,
        "failed": 0,
        "dropped": 0,
        "skipped": 0,
    }
