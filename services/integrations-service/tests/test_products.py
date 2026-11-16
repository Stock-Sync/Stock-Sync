"""Plan 9: paginated local listings and stale webhook protection."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest


def _item(item_id: str, *, sku_id: int | None = 1) -> SimpleNamespace:
    return SimpleNamespace(
        item_id=item_id,
        title=f"Item {item_id}",
        price=10.0,
        available_quantity=1,
        status="active",
        is_active=True,
        thumbnail=None,
        permalink=None,
        sku_id=sku_id,
        product_id=1 if sku_id is not None else None,
        updated_at=datetime.now(UTC),
        is_deleted=False,
    )


class _Result:
    def __init__(self, *, one_value=None, all_value=None) -> None:
        self._one = one_value
        self._all = all_value or []

    def one(self):
        return self._one

    def all(self):
        return self._all


class _ListSession:
    def __init__(self, total: int, items: list) -> None:
        self.total = total
        self.items = items
        self.calls = 0

    def exec(self, _statement):
        self.calls += 1
        if self.calls == 1:
            return _Result(one_value=self.total)
        return _Result(all_value=self.items)


def test_local_items_paginated_contract(monkeypatch):
    import app.api.routes.products as products_module

    monkeypatch.setattr(products_module, "get_tenant_id", lambda request: "tenant-1")
    session = _ListSession(total=3, items=[_item("MLB1"), _item("MLB2")])

    result = products_module.list_local_ml_items(
        request=object(),
        session=session,
        page=2,
        limit=10,
        search="MLB",
        unmapped_only=True,
    )

    assert result["page"] == 2
    assert result["limit"] == 10
    assert result["total"] == 3
    assert result["total_pages"] == 1
    assert [item["item_id"] for item in result["items"]] == ["MLB1", "MLB2"]
    assert result["items"][0]["is_mapped"] is True
    assert result["items"][0]["is_active"] is True


def test_local_items_total_pages_rounds_up(monkeypatch):
    import app.api.routes.products as products_module

    monkeypatch.setattr(products_module, "get_tenant_id", lambda request: "tenant-1")
    session = _ListSession(total=21, items=[])

    result = products_module.list_local_ml_items(
        request=object(),
        session=session,
        page=1,
        limit=20,
        search=None,
        unmapped_only=False,
    )

    assert result["total_pages"] == 2


class _FirstResult:
    def __init__(self, value) -> None:
        self._value = value

    def first(self):
        return self._value


class _StaleSession:
    def __init__(self, existing) -> None:
        self.existing = existing

    def exec(self, _statement):
        return _FirstResult(self.existing)


@pytest.mark.asyncio
async def test_stale_item_event_is_discarded():
    import app.api.routes.internal as internal_module

    existing = SimpleNamespace(
        tenant_id="tenant-1",
        item_id="MLB1",
        updated_at=datetime.now(UTC),
        is_active=True,
        sku_id=1,
        product_id=2,
    )
    result = await internal_module.sync_item_local(
        item_data={"id": "MLB1", "status": "paused", "seller_id": 321},
        event_timestamp=datetime.now(UTC) - timedelta(minutes=5),
        tenant_id="tenant-1",
        session=_StaleSession(existing),
    )

    assert result["applied"] is False
    assert result["reason"] == "stale_event"
    assert result["is_active"] is True


@pytest.mark.asyncio
async def test_fresh_item_event_updates_state_and_catalog(monkeypatch):
    import app.api.routes.internal as internal_module

    state_calls: list[tuple] = []

    class FakeML:
        def __init__(self, session) -> None:
            pass

        def sync_item_to_local(self, tenant_id, item_data, ml_user_id):
            return SimpleNamespace(
                item_id="MLB1",
                sku_id=1,
                product_id=2,
                is_active=False,
            )

        async def sync_catalog_mapping_state(
            self, tenant_id, item_id, is_active, event_timestamp=None
        ):
            state_calls.append((tenant_id, item_id, is_active, event_timestamp))

    monkeypatch.setattr(internal_module, "MercadoLivreService", FakeML)

    result = await internal_module.sync_item_local(
        item_data={"id": "MLB1", "status": "paused", "seller_id": 321},
        event_timestamp=datetime.now(UTC),
        tenant_id="tenant-1",
        session=_StaleSession(None),
    )

    assert result["applied"] is True
    assert result["is_active"] is False
    assert state_calls[0][1] == "MLB1"
    assert state_calls[0][2] is False


@pytest.mark.asyncio
async def test_update_route_uses_requested_status_when_ml_omits_it(monkeypatch):
    """A partial ML PUT response must still deactivate the catalog mapping."""
    import app.api.routes.products as products_module
    from app.schemas.marketplace_credential import ItemUpdateRequest

    calls: dict[str, object] = {}

    class FakeML:
        def __init__(self, session) -> None:
            pass

        async def update_item(self, tenant_id, item_id, item_data):
            calls["update"] = (tenant_id, item_id, item_data)
            # ML accepted the pause but returned no status field.
            return {"id": item_id, "available_quantity": 0}

        async def get_valid_credential(self, tenant_id):
            return SimpleNamespace(tenant_id=tenant_id, ml_user_id=321)

        def sync_item_to_local(self, tenant_id, item_data, ml_user_id):
            calls["local"] = dict(item_data)

        async def sync_catalog_mapping_state(
            self, tenant_id, item_id, is_active, event_timestamp=None
        ):
            calls["state"] = (tenant_id, item_id, is_active)

    monkeypatch.setattr(products_module, "MercadoLivreService", FakeML)
    monkeypatch.setattr(products_module, "get_tenant_id", lambda request: "tenant-1")

    result = await products_module.update_ml_item(
        item_id="MLB1",
        request=object(),
        payload=ItemUpdateRequest(status="paused", available_quantity=0),
        session=object(),
    )

    assert result["status"] == "paused"
    assert calls["local"]["status"] == "paused"
    assert calls["state"] == ("tenant-1", "MLB1", False)


@pytest.mark.asyncio
async def test_update_route_does_not_guess_status_when_not_requested(monkeypatch):
    """Without a requested status, a partial response leaves the mirror alone."""
    import app.api.routes.products as products_module
    from app.schemas.marketplace_credential import ItemUpdateRequest

    calls: dict[str, object] = {}

    class FakeML:
        def __init__(self, session) -> None:
            pass

        async def update_item(self, tenant_id, item_id, item_data):
            return {"id": item_id, "price": 12.0}

        async def get_valid_credential(self, tenant_id):
            return SimpleNamespace(tenant_id=tenant_id, ml_user_id=321)

        def sync_item_to_local(self, tenant_id, item_data, ml_user_id):
            calls["local"] = dict(item_data)

        async def sync_catalog_mapping_state(
            self, tenant_id, item_id, is_active, event_timestamp=None
        ):
            calls["state"] = (tenant_id, item_id, is_active)

    monkeypatch.setattr(products_module, "MercadoLivreService", FakeML)
    monkeypatch.setattr(products_module, "get_tenant_id", lambda request: "tenant-1")

    result = await products_module.update_ml_item(
        item_id="MLB1",
        request=object(),
        payload=ItemUpdateRequest(price=12.0),
        session=object(),
    )

    assert "status" not in result
    assert "status" not in calls["local"]
    assert "state" not in calls
