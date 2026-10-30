"""OrderProcessor tests with faked inter-service clients."""

import fakeredis.aioredis
import pytest
from app.models import StockUpdateLog
from app.services.order_processor import OrderProcessor
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

    async def adjust_stock(self, sku_id, delta, source, tenant_id=None):
        self.adjust_calls.append((sku_id, delta, source))
        return self.adjust_result

    async def find_sku_by_internal_sku(self, internal_sku, tenant_id=None):
        if self.sku and internal_sku == self.sku["internal_sku"]:
            return self.sku
        return None

    async def find_mapping_by_product_id(self, platform_product_id, tenant_id=None):
        return None

    async def get_sku(self, sku_id, tenant_id=None):
        return self.sku


class FakeSales:
    def __init__(self):
        self.recorded: list[dict] = []

    async def record_order(self, payload):
        self.recorded.append(payload)
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


async def test_process_order_deducts_persists_and_enqueues(processor, redis):
    result = await processor.process_order("tenant-1", "99")

    # Stock deducted atomically via the catalog client
    assert processor.catalog.adjust_calls == [(7, -2, "ml_sale")]

    # Sale persisted with buyer + totals
    sale = processor.sales.recorded[0]
    assert sale["marketplace_order_id"] == "99"
    assert sale["marketplace_item_id"] == "MLB-1"
    assert sale["internal_sku"] == "SKU-1"
    assert sale["buyer_nickname"] == "joao-buyer"
    assert sale["total_amount"] == 100.0

    # Quantity refresh enqueued for the flusher
    pending = await redis.hgetall(PENDING_STOCK_KEY)
    assert "tenant-1:MLB-1" in pending

    # Audit log written
    log = processor.session.query(StockUpdateLog).one()
    assert log.internal_sku == "SKU-1"
    assert log.new_quantity == 8
    assert log.source_platform == "ml_sale"

    assert result["items"][0]["mapped"] is True


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

    # No stock deduction, but the sale is still recorded (sku null)
    assert catalog.adjust_calls == []
    assert sales.recorded[0]["internal_sku"] is None
    assert sales.recorded[0]["marketplace_item_id"] == "MLB-X"
    assert result["items"][0]["mapped"] is False
    # No quantity flush for unmapped items
    assert await redis.hlen(PENDING_STOCK_KEY) == 0


async def test_process_order_clamped_deduct_is_logged(processor):
    processor.catalog.adjust_result = {"previous_quantity": 1, "new_quantity": 0, "clamped": True}

    await processor.process_order("tenant-1", "99")

    log = processor.session.query(StockUpdateLog).one()
    assert log.status == "clamped"
    assert log.new_quantity == 0


async def test_process_order_deleted_sku_keeps_sale_without_stock(processor, redis):
    processor.catalog.sku["is_deleted"] = True

    result = await processor.process_order("tenant-1", "99")

    assert processor.catalog.adjust_calls == []
    assert processor.sales.recorded[0]["sku_id"] == 7
    assert processor.sales.recorded[0]["internal_sku"] == "SKU-1"
    assert processor.session.query(StockUpdateLog).count() == 0
    assert await redis.hlen(PENDING_STOCK_KEY) == 0
    assert result["items"][0]["mapped"] is True


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
