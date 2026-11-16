INTERNAL_HEADERS = {"X-Internal-Secret": "your-internal-service-secret-change-in-production"}


def test_internal_order_requires_secret(client):
    response = client.get(
        "/api/v1/integrations/internal/mercadolivre/orders/99",
        headers={"X-Tenant-ID": "t1"},
    )
    assert response.status_code == 401


def test_internal_order_rejects_wrong_secret(client):
    response = client.get(
        "/api/v1/integrations/internal/mercadolivre/orders/99",
        headers={"X-Tenant-ID": "t1", "X-Internal-Secret": "wrong"},
    )
    assert response.status_code == 401


def test_internal_quantity_requires_non_negative(client):
    response = client.put(
        "/api/v1/integrations/internal/mercadolivre/items/MLB1/quantity",
        json={"available_quantity": -5},
        headers={**INTERNAL_HEADERS, "X-Tenant-ID": "t1"},
    )
    # Guard passes (default secret) then payload validation rejects.
    assert response.status_code == 422


def test_internal_item_ids_requires_secret(client):
    response = client.get(
        "/api/v1/integrations/internal/mercadolivre/items",
        headers={"X-Tenant-ID": "t1"},
    )
    assert response.status_code == 401


def test_internal_credential_lookup_requires_secret(client):
    response = client.get(
        "/api/v1/integrations/internal/mercadolivre/credentials/by-ml-user/1",
    )
    assert response.status_code == 401


def test_local_listings_requires_tenant(client):
    response = client.get("/api/v1/integrations/mercadolivre/items/local")
    assert response.status_code == 401


def test_reconcile_requires_secret(client):
    response = client.post(
        "/api/v1/integrations/internal/mercadolivre/items/reconcile",
        json={"seen_item_ids": ["MLB1"]},
        headers={"X-Tenant-ID": "t1"},
    )
    assert response.status_code == 401


def test_reconcile_soft_deletes_items_missing_from_ml(client, monkeypatch):
    import app.api.routes.internal as internal_module

    calls: dict = {}

    def fake_soft_delete(self, tenant_id, seen_item_ids, synced_before=None):
        calls["tenant_id"] = tenant_id
        calls["seen_item_ids"] = seen_item_ids
        calls["synced_before"] = synced_before
        return ["MLB-GONE"]

    monkeypatch.setattr(
        internal_module.MercadoLivreService,
        "soft_delete_missing_items",
        fake_soft_delete,
    )

    response = client.post(
        "/api/v1/integrations/internal/mercadolivre/items/reconcile",
        json={
            "seen_item_ids": ["MLB1", "MLB1", "MLB2"],
            "synced_before": "2026-11-02T10:00:00Z",
        },
        headers={**INTERNAL_HEADERS, "X-Tenant-ID": "t1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "deleted_item_ids": ["MLB-GONE"],
        "deleted": 1,
    }
    # Duplicated ids from the marketplace payload are collapsed.
    assert calls["tenant_id"] == "t1"
    assert calls["seen_item_ids"] == ["MLB1", "MLB2"]
    assert calls["synced_before"] is not None


def test_internal_item_ids_returns_truncation_metadata(client, monkeypatch):
    import app.api.routes.internal as internal_module

    async def fake_search(self, tenant_id, page_size=50):
        return {
            "item_ids": ["MLB1", "MLB2"],
            "reported_total": 5,
            "truncated": True,
        }

    monkeypatch.setattr(
        internal_module.MercadoLivreService,
        "search_all_items_with_metadata",
        fake_search,
    )

    response = client.get(
        "/api/v1/integrations/internal/mercadolivre/items",
        headers={**INTERNAL_HEADERS, "X-Tenant-ID": "t1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "item_ids": ["MLB1", "MLB2"],
        "total": 2,
        "reported_total": 5,
        "truncated": True,
    }


def test_local_item_ids_splits_variations(client, monkeypatch):
    import app.api.routes.internal as internal_module

    calls: dict = {}

    def fake_list(self, tenant_id, synced_before=None):
        calls["tenant_id"] = tenant_id
        calls["synced_before"] = synced_before
        return ["MLB1"], ["MLB-VAR"]

    monkeypatch.setattr(
        internal_module.MercadoLivreService,
        "list_local_active_items",
        fake_list,
    )

    response = client.get(
        "/api/v1/integrations/internal/mercadolivre/local-items/ids",
        headers={**INTERNAL_HEADERS, "X-Tenant-ID": "t1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "item_ids": ["MLB1"],
        "variation_item_ids": ["MLB-VAR"],
        "total": 1,
    }
    assert calls["tenant_id"] == "t1"


def test_reconcile_with_missing_item_ids_uses_explicit_set(client, monkeypatch):
    import app.api.routes.internal as internal_module

    calls: dict = {}

    def fake_soft_delete(self, tenant_id, item_ids):
        calls["tenant_id"] = tenant_id
        calls["item_ids"] = item_ids
        return ["MLB-GONE"]

    monkeypatch.setattr(
        internal_module.MercadoLivreService,
        "soft_delete_items",
        fake_soft_delete,
    )

    response = client.post(
        "/api/v1/integrations/internal/mercadolivre/items/reconcile",
        json={
            "missing_item_ids": ["MLB-GONE", "MLB-GONE", "MLB-ALSO-GONE"],
        },
        headers={**INTERNAL_HEADERS, "X-Tenant-ID": "t1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "deleted_item_ids": ["MLB-GONE"],
        "deleted": 1,
    }
    assert calls == {
        "tenant_id": "t1",
        "item_ids": ["MLB-GONE", "MLB-ALSO-GONE"],
    }


def test_batch_details_requires_secret(client):
    response = client.post(
        "/api/v1/integrations/internal/mercadolivre/items/batch-details",
        json={"item_ids": ["MLB1"]},
        headers={"X-Tenant-ID": "t1"},
    )
    assert response.status_code == 401


def test_batch_details_enriches_status_permalink_and_variations(client):
    from types import SimpleNamespace

    from app.db.session import get_session
    from app.main import app

    rows = [
        SimpleNamespace(
            id=2,
            item_id="MLB1",
            status="active",
            permalink="https://produto.mercadolivre.com.br/MLB-1",
            is_active=True,
            is_deleted=False,
            available_quantity=4,
            raw_payload={"id": "MLB1", "variations": [{"id": "v1"}]},
        ),
        SimpleNamespace(
            id=1,
            item_id="MLB2",
            status="paused",
            permalink=None,
            is_active=False,
            is_deleted=False,
            available_quantity=0,
            raw_payload={"id": "MLB2"},
        ),
    ]

    class FakeSession:
        def exec(self, _statement):
            return SimpleNamespace(all=lambda: rows)

    app.dependency_overrides[get_session] = lambda: FakeSession()

    response = client.post(
        "/api/v1/integrations/internal/mercadolivre/items/batch-details",
        json={"item_ids": ["MLB1", "MLB-MISSING", "MLB1"]},
        headers={**INTERNAL_HEADERS, "X-Tenant-ID": "t1"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == ["MLB1", "MLB-MISSING"]
    assert items[0]["status"] == "active"
    assert items[0]["permalink"] == "https://produto.mercadolivre.com.br/MLB-1"
    assert items[0]["has_variations"] is True
    assert items[0]["available_quantity"] == 4
    assert items[1] == {
        "id": "MLB-MISSING",
        "status": None,
        "permalink": None,
        "is_active": False,
        "is_deleted": False,
        "available_quantity": None,
        "has_variations": False,
        "found": False,
    }


def test_internal_quantity_rejects_variation_listing(client):
    from types import SimpleNamespace

    from app.db.session import get_session
    from app.main import app

    class FakeSession:
        def exec(self, statement):
            item = SimpleNamespace(
                raw_payload={"id": "MLB1", "variations": [{"id": "v1"}]}
            )
            return SimpleNamespace(first=lambda: item)

    app.dependency_overrides[get_session] = lambda: FakeSession()

    response = client.put(
        "/api/v1/integrations/internal/mercadolivre/items/MLB1/quantity",
        json={"available_quantity": 5},
        headers={**INTERNAL_HEADERS, "X-Tenant-ID": "t1"},
    )

    assert response.status_code == 409
    assert "variations" in response.json()["error"]["message"]
