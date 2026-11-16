"""OrderProcessor tests with faked inter-service clients."""

from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest
from app.models import StockUpdateLog
from app.services.order_processor import (
    CANCELLATION_SOURCE,
    DEDUCTION_SOURCE,
    OrderProcessor,
    StockProcessingError,
)
from app.streams.consts import PENDING_STOCK_KEY

ORDER = {
    "id": "99",
    "status": "paid",
    "currency": "BRL",
    "date_created": "2026-10-23T12:00:00Z",
    "buyer": {"nickname": "joao-buyer"},
    "order_items": [
        {
            "item": {"id": "MLB-1", "title": "Fone", "seller_custom_field": "SKU-1"},
            "quantity": 2,
            "unit_price": 50.0,
            "full_unit_price": 100.0,
        }
    ],
}


class FakeIntegrations:
    def __init__(self, order=ORDER):
        self.order = order

    async def get_order(self, tenant_id, order_id):
        return self.order

    async def resolve_tenant_by_ml_user(self, ml_user_id):
        return {"tenant_id": "tenant-1"}


class FakeCatalog:
    def __init__(self, sku=None):
        if sku is None:
            sku = {"id": 7, "internal_sku": "SKU-1", "stock_quantity": 10}
        self.sku = sku
        self.adjust_calls: list[tuple[int, int, str]] = []
        self.adjust_result = {
            "previous_quantity": 10,
            "new_quantity": 8,
            "clamped": False,
        }
        self.raise_on_adjust = False

    async def adjust_stock(self, sku_id, delta, source, tenant_id=None):
        self.adjust_calls.append((sku_id, delta, source))
        if self.raise_on_adjust:
            raise RuntimeError("catalog unavailable")
        return self.adjust_result

    async def find_sku_by_internal_sku(self, internal_sku, tenant_id=None):
        if self.sku and internal_sku == self.sku["internal_sku"]:
            return self.sku
        return None

    async def find_mapping_by_product_id(
        self, platform_product_id, tenant_id=None, include_deleted=False
    ):
        return None

    async def get_sku(self, sku_id, tenant_id=None):
        return self.sku


class FakeSales:
    def __init__(self):
        self.recorded: list[tuple[dict, str | None]] = []

    async def record_order(self, payload, tenant_id=None):
        self.recorded.append((payload, tenant_id))
        return {"id": 1}


@pytest.fixture()
async def redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture()
def processor(db_session, redis):
    return OrderProcessor(
        db_session,
        catalog=FakeCatalog(),
        integrations=FakeIntegrations(),
        sales=FakeSales(),
        redis_client=redis,
    )


def _sale(processor) -> dict:
    return processor.sales.recorded[0][0]


async def test_paid_order_deducts_persists_and_enqueues(processor, redis):
    result = await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == [(7, -2, DEDUCTION_SOURCE)]

    sale = _sale(processor)
    assert sale["tenant_id"] == "tenant-1"
    assert sale["marketplace_order_id"] == "99"
    assert sale["marketplace_item_id"] == "MLB-1"
    assert sale["internal_sku"] == "SKU-1"
    assert sale["buyer_nickname"] == "joao-buyer"
    assert sale["total_amount"] == 100.0
    assert sale["is_variation"] is False
    assert processor.sales.recorded[0][1] == "tenant-1"

    pending = await redis.hgetall(PENDING_STOCK_KEY)
    assert "tenant-1:MLB-1" in pending

    log = processor.session.query(StockUpdateLog).one()
    assert log.internal_sku == "SKU-1"
    assert log.new_quantity == 8
    assert log.source_platform == DEDUCTION_SOURCE
    assert log.status == "applied"
    assert log.deducted_quantity == 2
    assert log.clamped is False
    assert log.lease_expires_at is None

    assert result["items"][0]["mapped"] is True
    assert result["items"][0]["stock_action"] == "deducted"


async def test_confirmed_order_deducts(processor):
    processor.integrations.order = {**ORDER, "status": "confirmed"}

    await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == [(7, -2, DEDUCTION_SOURCE)]


async def test_pending_order_records_sale_without_deducting(processor, redis):
    processor.integrations.order = {**ORDER, "status": "payment_required"}

    result = await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == []
    assert _sale(processor)["status"] == "payment_required"
    assert processor.session.query(StockUpdateLog).count() == 0
    assert await redis.hlen(PENDING_STOCK_KEY) == 0
    assert result["items"][0]["stock_action"] == "awaiting_payment"


async def test_paid_notification_after_pending_deducts(processor):
    processor.integrations.order = {**ORDER, "status": "payment_required"}
    await processor.process_order("tenant-1", "99")
    assert processor.catalog.adjust_calls == []

    processor.integrations.order = {**ORDER, "status": "paid"}
    await processor.process_order("tenant-1", "99")
    assert processor.catalog.adjust_calls == [(7, -2, DEDUCTION_SOURCE)]


async def test_process_order_unmapped_item_still_records_sale(db_session, redis):
    catalog = FakeCatalog(sku=None)
    sales = FakeSales()
    order = {
        **ORDER,
        "order_items": [
            {"item": {"id": "MLB-X", "title": "Sem SKU"}, "quantity": 1, "unit_price": 30.0}
        ],
    }
    processor = OrderProcessor(
        db_session,
        catalog=catalog,
        integrations=FakeIntegrations(order=order),
        sales=sales,
        redis_client=redis,
    )

    result = await processor.process_order("tenant-1", "99")

    assert catalog.adjust_calls == []
    assert sales.recorded[0][0]["internal_sku"] is None
    assert sales.recorded[0][0]["marketplace_item_id"] == "MLB-X"
    assert result["items"][0]["mapped"] is False
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_clamped_deduction_records_actual_quantity(processor):
    processor.catalog.adjust_result = {
        "previous_quantity": 1,
        "new_quantity": 0,
        "clamped": True,
    }

    await processor.process_order("tenant-1", "99")

    log = processor.session.query(StockUpdateLog).one()
    assert log.status == "applied"
    assert log.clamped is True
    assert log.deducted_quantity == 1
    assert log.new_quantity == 0


async def test_deleted_sku_keeps_sale_and_zeroes_listing(processor, redis):
    processor.catalog.sku["is_deleted"] = True

    result = await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == []
    assert _sale(processor)["sku_id"] == 7
    assert _sale(processor)["internal_sku"] == "SKU-1"
    assert processor.session.query(StockUpdateLog).count() == 0
    # The flusher must receive the item so it can push quantity 0 / pause it.
    pending = await redis.hgetall(PENDING_STOCK_KEY)
    assert "tenant-1:MLB-1" in pending
    assert result["items"][0]["stock_action"] == "deleted_sku_paused"
    assert result["items"][0]["mapped"] is True


async def test_variation_sale_does_not_move_parent_sku(processor, redis):
    order = {
        **ORDER,
        "order_items": [
            {
                "item": {
                    "id": "MLB-1",
                    "title": "Fone",
                    "seller_custom_field": "SKU-1",
                    "variation_id": 12345,
                },
                "quantity": 2,
                "unit_price": 50.0,
                "full_unit_price": 100.0,
            }
        ],
    }
    processor.integrations.order = order

    result = await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == []
    assert _sale(processor)["is_variation"] is True
    assert processor.session.query(StockUpdateLog).count() == 0
    assert await redis.hlen(PENDING_STOCK_KEY) == 0
    assert result["items"][0]["stock_action"] == "variation_skipped"
    assert result["items"][0]["is_variation"] is True


async def test_process_order_is_idempotent_for_duplicate_notifications(processor):
    await processor.process_order("tenant-1", "99")
    await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == [(7, -2, DEDUCTION_SOURCE)]
    assert processor.session.query(StockUpdateLog).count() == 1


async def test_cancellation_restocks_only_the_deducted_quantity(processor):
    # The paid sale was clamped: 1 unit deducted for an order of 2.
    processor.catalog.adjust_result = {
        "previous_quantity": 1,
        "new_quantity": 0,
        "clamped": True,
    }
    await processor.process_order("tenant-1", "99")

    processor.catalog.adjust_result = {
        "previous_quantity": 0,
        "new_quantity": 1,
        "clamped": False,
    }
    processor.integrations.order = {**ORDER, "status": "cancelled"}
    await processor.process_order("tenant-1", "99")

    # A refund/duplicate cancellation notification must not restock again.
    processor.integrations.order = {**ORDER, "status": "refunded"}
    await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == [
        (7, -2, DEDUCTION_SOURCE),
        (7, 1, CANCELLATION_SOURCE),
    ]
    logs = (
        processor.session.query(StockUpdateLog)
        .order_by(StockUpdateLog.id)
        .all()
    )
    assert [log.source_platform for log in logs] == [
        DEDUCTION_SOURCE,
        CANCELLATION_SOURCE,
    ]
    assert logs[1].status == "applied"
    assert logs[1].new_quantity == 1
    assert logs[1].deducted_quantity == 0


async def test_cancellation_without_deduction_does_not_restock(db_session, redis):
    catalog = FakeCatalog()
    processor = OrderProcessor(
        db_session,
        catalog=catalog,
        integrations=FakeIntegrations(order={**ORDER, "status": "cancelled"}),
        sales=FakeSales(),
        redis_client=redis,
    )

    await processor.process_order("tenant-1", "99")

    assert catalog.adjust_calls == []
    log = db_session.query(StockUpdateLog).one()
    assert log.source_platform == CANCELLATION_SOURCE
    assert log.status == "skipped"


async def test_late_paid_notification_does_not_deduct_after_cancellation(
    db_session, redis
):
    catalog = FakeCatalog()
    integrations = FakeIntegrations(order={**ORDER, "status": "cancelled"})
    processor = OrderProcessor(
        db_session,
        catalog=catalog,
        integrations=integrations,
        sales=FakeSales(),
        redis_client=redis,
    )

    await processor.process_order("tenant-1", "99")
    # Out-of-order delivery: the paid event shows up after the cancellation.
    integrations.order = {**ORDER, "status": "paid"}
    await processor.process_order("tenant-1", "99")

    assert catalog.adjust_calls == []
    assert db_session.query(StockUpdateLog).count() == 1


async def test_live_claim_lease_prevents_duplicate_deduction(processor):
    now = datetime.now(UTC)
    processor.session.add(
        StockUpdateLog(
            internal_sku="SKU-1",
            previous_quantity=0,
            new_quantity=0,
            source_platform=DEDUCTION_SOURCE,
            marketplace_order_id="99",
            marketplace_item_id="MLB-1",
            status="in_progress",
            attempts=1,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=60),
            updated_at=now,
        )
    )
    processor.session.commit()

    result = await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == []
    assert result["items"][0]["stock_action"] == "duplicate"
    log = processor.session.query(StockUpdateLog).one()
    assert log.status == "in_progress"


async def test_expired_claim_lease_is_taken_over(processor):
    now = datetime.now(UTC)
    processor.session.add(
        StockUpdateLog(
            internal_sku="SKU-1",
            previous_quantity=0,
            new_quantity=0,
            source_platform=DEDUCTION_SOURCE,
            marketplace_order_id="99",
            marketplace_item_id="MLB-1",
            status="in_progress",
            attempts=1,
            heartbeat_at=now - timedelta(minutes=5),
            lease_expires_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=5),
        )
    )
    processor.session.commit()

    await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == [(7, -2, DEDUCTION_SOURCE)]
    log = processor.session.query(StockUpdateLog).one()
    assert log.status == "applied"
    assert log.attempts == 2


async def test_stock_failure_is_retried_after_sale_is_recorded(processor):
    processor.catalog.raise_on_adjust = True

    with pytest.raises(StockProcessingError):
        await processor.process_order("tenant-1", "99")

    # The sale exists even though the stock movement failed.
    assert _sale(processor)["marketplace_order_id"] == "99"
    log = processor.session.query(StockUpdateLog).one()
    assert log.status == "failed"
    assert "catalog unavailable" in log.error_message

    processor.catalog.raise_on_adjust = False
    await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == [
        (7, -2, DEDUCTION_SOURCE),
        (7, -2, DEDUCTION_SOURCE),
    ]
    log = processor.session.query(StockUpdateLog).one()
    assert log.status == "applied"
    assert log.attempts == 2


async def test_failed_cancellation_is_retried(processor):
    await processor.process_order("tenant-1", "99")

    processor.catalog.raise_on_adjust = True
    processor.integrations.order = {**ORDER, "status": "cancelled"}
    with pytest.raises(StockProcessingError):
        await processor.process_order("tenant-1", "99")

    cancellation = (
        processor.session.query(StockUpdateLog)
        .filter_by(source_platform=CANCELLATION_SOURCE)
        .one()
    )
    assert cancellation.status == "failed"

    processor.catalog.raise_on_adjust = False
    processor.catalog.adjust_result = {
        "previous_quantity": 8,
        "new_quantity": 10,
        "clamped": False,
    }
    await processor.process_order("tenant-1", "99")

    cancellation = (
        processor.session.query(StockUpdateLog)
        .filter_by(source_platform=CANCELLATION_SOURCE)
        .one()
    )
    assert cancellation.status == "applied"
    assert cancellation.attempts == 2
    assert processor.catalog.adjust_calls == [
        (7, -2, DEDUCTION_SOURCE),
        (7, 2, CANCELLATION_SOURCE),
        (7, 2, CANCELLATION_SOURCE),
    ]


async def test_cancellation_waits_for_in_progress_deduction(processor):
    now = datetime.now(UTC)
    processor.session.add(
        StockUpdateLog(
            internal_sku="SKU-1",
            previous_quantity=0,
            new_quantity=0,
            source_platform=DEDUCTION_SOURCE,
            marketplace_order_id="99",
            marketplace_item_id="MLB-1",
            status="in_progress",
            attempts=1,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=60),
            updated_at=now,
        )
    )
    processor.session.commit()
    processor.integrations.order = {**ORDER, "status": "cancelled"}

    with pytest.raises(StockProcessingError):
        await processor.process_order("tenant-1", "99")

    assert (
        processor.session.query(StockUpdateLog)
        .filter_by(source_platform=CANCELLATION_SOURCE)
        .count()
        == 0
    )


class FakeHTTPResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


async def test_process_stock_adjust_enqueues_mapped_items(processor, redis, monkeypatch):
    import app.services.order_processor as op_module

    mappings = [
        {"sku_id": 7, "platform_product_id": "MLB-1"},
        {"sku_id": 7, "platform_product_id": "MLB-2"},
        {"sku_id": 999, "platform_product_id": "OTHER"},
    ]

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            if url.endswith("/platform-mappings"):
                return FakeHTTPResponse(mappings)
            if url.endswith("/owner"):
                return FakeHTTPResponse({"tenant_id": "tenant-1"})
            raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(op_module.httpx, "AsyncClient", FakeAsyncClient)

    result = await processor.process_stock_adjust(
        {"sku_id": 7, "new_quantity": 3, "internal_sku": "SKU-1", "tenant_id": "tenant-1"}
    )

    assert sorted(result["enqueued_items"]) == ["MLB-1", "MLB-2"]
    pending = await redis.hgetall(PENDING_STOCK_KEY)
    assert set(pending) == {"tenant-1:MLB-1", "tenant-1:MLB-2"}


async def test_process_stock_adjust_requires_fields(processor):
    with pytest.raises(ValueError):
        await processor.process_stock_adjust({"sku_id": 7})


async def test_process_stock_adjust_requires_tenant(processor):
    with pytest.raises(ValueError, match="tenant_id"):
        await processor.process_stock_adjust(
            {"sku_id": 7, "new_quantity": 3}
        )


async def test_process_stock_adjust_skips_inactive_and_variation_mappings(
    processor, redis, monkeypatch
):
    import app.services.order_processor as op_module

    mappings = [
        {"sku_id": 7, "platform_product_id": "MLB-INACTIVE", "is_active": False},
        {
            "sku_id": 7,
            "platform_product_id": "MLB-VAR",
            "is_active": True,
            "platform_variant_id": "v1",
        },
        {"sku_id": 7, "platform_product_id": "MLB-OK", "is_active": True},
    ]

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            if url.endswith("/platform-mappings"):
                return FakeHTTPResponse(mappings)
            raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(op_module.httpx, "AsyncClient", FakeAsyncClient)

    result = await processor.process_stock_adjust(
        {
            "sku_id": 7,
            "new_quantity": 3,
            "internal_sku": "SKU-1",
            "tenant_id": "tenant-1",
        }
    )

    assert result["enqueued_items"] == ["MLB-OK"]
    pending = await redis.hgetall(PENDING_STOCK_KEY)
    assert set(pending) == {"tenant-1:MLB-OK"}
