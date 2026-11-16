from app.api.routes.skus import adjust_sku_stock
from app.models import SKU, PlatformMapping
from app.schemas import SKUAdjust
from sqlalchemy import text
from sqlmodel import Session


def _make_product(client):
    return client.post("/api/v1/products", json={"name": "Produto"}).json()


def _make_sku(client, stock_quantity=10, internal_sku="SKU-1"):
    product = _make_product(client)
    return client.post(
        "/api/v1/skus",
        json={
            "product_id": product["id"],
            "internal_sku": internal_sku,
            "stock_quantity": stock_quantity,
        },
    ).json()


def test_create_sku(client):
    response = client.post(
        "/api/v1/skus",
        json={
            "product_id": _make_product(client)["id"],
            "internal_sku": "SKU-1",
            "stock_quantity": 10,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["internal_sku"] == "SKU-1"
    assert body["stock_quantity"] == 10


def test_create_sku_product_not_found(client):
    response = client.post("/api/v1/skus", json={"product_id": 999, "internal_sku": "SKU-1"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_create_sku_duplicate(client):
    product = _make_product(client)
    payload = {"product_id": product["id"], "internal_sku": "SKU-1"}
    assert client.post("/api/v1/skus", json=payload).status_code == 201
    response = client.post("/api/v1/skus", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_list_skus(client):
    first_product = _make_product(client)
    second_product = _make_product(client)
    client.post(
        "/api/v1/skus",
        json={"product_id": first_product["id"], "internal_sku": "SKU-1"},
    )
    client.post(
        "/api/v1/skus",
        json={"product_id": second_product["id"], "internal_sku": "SKU-2"},
    )
    response = client.get("/api/v1/skus")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_sku_not_found(client):
    response = client.get("/api/v1/skus/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_update_sku(client):
    sku = _make_sku(client)
    response = client.put(f"/api/v1/skus/{sku['id']}", json={"stock_quantity": 25})
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 25


def test_update_sku_publishes_event_with_tenant(client, stock_events):
    sku = _make_sku(client, stock_quantity=10)
    stock_events.clear()

    response = client.put(f"/api/v1/skus/{sku['id']}", json={"stock_quantity": 25})

    assert response.status_code == 200
    assert stock_events == [
        {
            "sku_id": sku["id"],
            "internal_sku": "SKU-1",
            "previous_quantity": 10,
            "new_quantity": 25,
            "source": "catalog_update",
            "tenant_id": "test-tenant",
        }
    ]


def test_update_sku_locks_internal_sku_with_active_mapping(client):
    sku = _make_sku(client)
    client.post(
        "/api/v1/platform-mappings",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "SKU-1",
        },
    )

    response = client.put(
        f"/api/v1/skus/{sku['id']}", json={"internal_sku": "SKU-RENAMED"}
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "internal_sku_locked"
    assert client.get(f"/api/v1/skus/{sku['id']}").json()[
        "internal_sku"
    ] == "SKU-1"


def test_update_sku_allows_internal_sku_after_mapping_is_deleted(client):
    sku = _make_sku(client)
    mapping = client.post(
        "/api/v1/platform-mappings",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "SKU-1",
        },
    ).json()
    assert (
        client.delete(f"/api/v1/platform-mappings/{mapping['id']}").status_code
        == 204
    )

    response = client.put(
        f"/api/v1/skus/{sku['id']}", json={"internal_sku": "SKU-RENAMED"}
    )

    assert response.status_code == 200
    assert response.json()["internal_sku"] == "SKU-RENAMED"


def test_update_sku_cannot_move_to_product_with_active_sku(client):
    first_sku = _make_sku(client, internal_sku="SKU-1")
    second_product = _make_product(client)
    second_sku = client.post(
        "/api/v1/skus",
        json={"product_id": second_product["id"], "internal_sku": "SKU-2"},
    ).json()

    response = client.put(
        f"/api/v1/skus/{second_sku['id']}",
        json={"product_id": first_sku["product_id"], "internal_sku": "SKU-3"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_adjust_sku_decrease(client):
    sku = _make_sku(client, stock_quantity=10)
    response = client.post(f"/api/v1/skus/{sku['id']}/adjust", json={"delta": -3})
    assert response.status_code == 200
    body = response.json()
    assert body["previous_quantity"] == 10
    assert body["new_quantity"] == 7
    assert body["clamped"] is False


def test_adjust_sku_increase(client):
    sku = _make_sku(client, stock_quantity=10)
    response = client.post(f"/api/v1/skus/{sku['id']}/adjust", json={"delta": 5})
    assert response.status_code == 200
    assert response.json()["new_quantity"] == 15


def test_adjust_sku_clamped_at_zero(client):
    sku = _make_sku(client, stock_quantity=4)
    response = client.post(
        f"/api/v1/skus/{sku['id']}/adjust", json={"delta": -10, "source": "sale"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["new_quantity"] == 0
    assert body["clamped"] is True
    # persisted quantity must also be 0
    assert client.get(f"/api/v1/skus/{sku['id']}").json()["stock_quantity"] == 0


def test_adjust_sku_reads_fresh_row_despite_stale_identity_map(client, db_engine):
    """Regression: ``previous_quantity`` must not come from a stale snapshot.

    A session may already hold the SKU in its identity map with an outdated
    quantity (for example, because another request committed a sale in the
    meantime). The adjust endpoint must lock and re-read the row instead of
    reporting the cached value, otherwise ``deducted_quantity`` and the
    cancellation restock are computed from the wrong baseline.
    """
    sku = _make_sku(client, stock_quantity=10)

    with Session(db_engine) as session:
        stale = session.get(SKU, sku["id"])
        assert stale.stock_quantity == 10

        # Simulate the concurrent commit leaving this session's identity map
        # with the old quantity. Raw text avoids ORM synchronization.
        session.execute(
            text("UPDATE sku SET stock_quantity = 5 WHERE id = :id"),
            {"id": sku["id"]},
        )

        result = adjust_sku_stock(
            sku["id"], SKUAdjust(delta=-2, source="ml_sale"), session, "test-tenant"
        )

    assert result.previous_quantity == 5
    assert result.new_quantity == 3
    assert result.clamped is False


def test_adjust_sku_not_found(client):
    response = client.post("/api/v1/skus/999/adjust", json={"delta": -1})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_adjust_sku_missing_delta(client):
    sku = _make_sku(client)
    response = client.post(f"/api/v1/skus/{sku['id']}/adjust", json={})
    assert response.status_code == 422


def test_create_sku_on_deleted_product_not_found(client):
    product = _make_product(client)
    assert client.delete(f"/api/v1/products/{product['id']}").status_code == 204

    response = client.post(
        "/api/v1/skus",
        json={"product_id": product["id"], "internal_sku": "SKU-ORPHAN"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_create_second_active_sku_for_product_conflicts(client):
    product = _make_product(client)
    assert (
        client.post(
            "/api/v1/skus",
            json={"product_id": product["id"], "internal_sku": "SKU-1"},
        ).status_code
        == 201
    )

    response = client.post(
        "/api/v1/skus",
        json={"product_id": product["id"], "internal_sku": "SKU-2"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_create_sku_reusing_deleted_code_succeeds(client):
    product = _make_product(client)
    payload = {"product_id": product["id"], "internal_sku": "SKU-ARCHIVED"}
    assert client.post("/api/v1/skus", json=payload).status_code == 201
    deleted = client.get("/api/v1/skus").json()[0]
    assert client.delete(f"/api/v1/skus/{deleted['id']}").status_code == 204

    # Plan 11: the partial indexes ignore soft-deleted rows, so both the code
    # and the product can be reused after archiving.
    response = client.post("/api/v1/skus", json=payload)
    assert response.status_code == 201
    assert response.json()["internal_sku"] == "SKU-ARCHIVED"


def test_delete_sku_soft_deletes_and_is_idempotent(client, db_engine):
    sku = _make_sku(client)

    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204
    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204

    detail = client.get(f"/api/v1/skus/{sku['id']}")
    assert detail.status_code == 200
    assert detail.json()["is_deleted"] is True
    assert client.get("/api/v1/skus").json() == []

    with Session(db_engine) as session:
        stored = session.get(SKU, sku["id"])
        assert stored is not None
        assert stored.is_deleted is True


def test_delete_sku_deactivates_mappings(client, db_engine):
    sku = _make_sku(client)
    mapping = client.post(
        "/api/v1/platform-mappings",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "ML-1",
        },
    ).json()

    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204

    with Session(db_engine) as session:
        stored = session.get(PlatformMapping, mapping["id"])
        assert stored is not None
        assert stored.is_active is False


def test_update_deleted_sku_not_found(client):
    sku = _make_sku(client)
    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204

    response = client.put(f"/api/v1/skus/{sku['id']}", json={"price": 99})
    assert response.status_code == 404


def test_adjust_deleted_sku_not_found(client):
    sku = _make_sku(client)
    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204

    response = client.post(f"/api/v1/skus/{sku['id']}/adjust", json={"delta": 1})
    assert response.status_code == 404


# =============================================================================
# Internal lookup used by listing auto-matching (Plan 8)
# =============================================================================


def _internal_headers(tenant_id="test-tenant", secret=None):
    from app.core.config import settings

    return {
        "X-Internal-Secret": secret or settings.internal_service_secret,
        "X-Tenant-ID": tenant_id,
    }


def test_internal_sku_lookup_is_mappable_when_active(client):
    sku = _make_sku(client)

    response = client.get(
        "/api/v1/internal/skus/lookup",
        params={"internal_sku": "SKU-1"},
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == sku["id"]
    assert body["is_deleted"] is False
    assert body["product_is_deleted"] is False
    assert body["mappable"] is True


def test_internal_sku_lookup_reports_deleted_sku(client):
    sku = _make_sku(client)
    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204

    response = client.get(
        "/api/v1/internal/skus/lookup",
        params={"internal_sku": "SKU-1"},
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_deleted"] is True
    assert body["mappable"] is False


def test_internal_sku_lookup_reports_deleted_product(client, db_engine):
    product = _make_product(client)
    sku = client.post(
        "/api/v1/skus",
        json={"product_id": product["id"], "internal_sku": "SKU-1"},
    ).json()

    from app.models import Product
    from sqlmodel import Session

    with Session(db_engine) as session:
        stored = session.get(Product, product["id"])
        stored.is_deleted = True
        session.add(stored)
        session.commit()

    response = client.get(
        "/api/v1/internal/skus/lookup",
        params={"internal_sku": "SKU-1"},
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == sku["id"]
    assert body["product_is_deleted"] is True
    assert body["mappable"] is False


def test_internal_sku_lookup_requires_secret(client):
    _make_sku(client)
    response = client.get(
        "/api/v1/internal/skus/lookup",
        params={"internal_sku": "SKU-1"},
        headers={"X-Tenant-ID": "test-tenant"},
    )
    assert response.status_code == 401


def test_internal_sku_lookup_not_found(client):
    response = client.get(
        "/api/v1/internal/skus/lookup",
        params={"internal_sku": "NOPE"},
        headers=_internal_headers(),
    )
    assert response.status_code == 404
