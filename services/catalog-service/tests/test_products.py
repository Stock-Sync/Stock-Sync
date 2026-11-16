from datetime import UTC, datetime

from app.models import SKU, PlatformMapping, Product
from sqlmodel import Session


def test_create_product(client):
    response = client.post(
        "/api/v1/products", json={"name": "Produto A", "description": "descricao"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "Produto A"
    assert body["description"] == "descricao"


def test_create_product_validation_error(client):
    response = client.post("/api/v1/products", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "validation_error"


def test_list_products(client):
    client.post("/api/v1/products", json={"name": "Produto A"})
    client.post("/api/v1/products", json={"name": "Produto B"})
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_products_empty(client):
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    assert response.json() == []


def test_get_product(client):
    product_id = client.post("/api/v1/products", json={"name": "Produto A"}).json()["id"]
    response = client.get(f"/api/v1/products/{product_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Produto A"


def test_get_product_not_found(client):
    response = client.get("/api/v1/products/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_update_product(client):
    product_id = client.post("/api/v1/products", json={"name": "Produto A"}).json()["id"]
    response = client.put(f"/api/v1/products/{product_id}", json={"name": "Produto B"})
    assert response.status_code == 200
    assert response.json()["name"] == "Produto B"


def test_update_product_not_found(client):
    response = client.put("/api/v1/products/999", json={"name": "Produto B"})
    assert response.status_code == 404


def test_delete_product(client, db_engine):
    product_id = client.post("/api/v1/products", json={"name": "Produto A"}).json()["id"]
    response = client.delete(f"/api/v1/products/{product_id}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/products/{product_id}").status_code == 404
    assert client.get("/api/v1/products").json() == []

    with Session(db_engine) as session:
        product = session.get(Product, product_id)
        assert product is not None
        assert product.is_deleted is True


def test_delete_product_soft_deletes_children(client, db_engine):
    product = client.post("/api/v1/products", json={"name": "Produto A"}).json()
    sku = client.post(
        "/api/v1/skus",
        json={"product_id": product["id"], "internal_sku": "SKU-DELETE"},
    ).json()
    mapping = client.post(
        "/api/v1/platform-mappings",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "SKU-DELETE",
        },
    ).json()

    assert client.delete(f"/api/v1/products/{product['id']}").status_code == 204

    with Session(db_engine) as session:
        stored_product = session.get(Product, product["id"])
        stored_sku = session.get(SKU, sku["id"])
        stored_mapping = session.get(PlatformMapping, mapping["id"])

        assert stored_product is not None and stored_product.is_deleted is True
        assert stored_sku is not None and stored_sku.is_deleted is True
        assert stored_mapping is not None and stored_mapping.is_active is False

    assert client.get("/api/v1/skus").json() == []


def _make_product_with_active_mapping(client, item_id="MLB123"):
    product = client.post("/api/v1/products", json={"name": "Camiseta"}).json()
    sku = client.post(
        "/api/v1/skus",
        json={
            "product_id": product["id"],
            "internal_sku": "SKU-ACTIVE",
            "stock_quantity": 7,
        },
    ).json()
    mapping = client.post(
        "/api/v1/platform-mappings",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "SKU-ACTIVE",
            "platform_product_id": item_id,
        },
    ).json()
    return product, sku, mapping


def test_delete_product_blocks_active_listing_with_structured_409(
    client, listing_details
):
    product, _sku, _mapping = _make_product_with_active_mapping(client)
    listing_details["MLB123"] = {
        "status": "active",
        "permalink": "https://produto.mercadolivre.com.br/MLB-123",
    }

    response = client.delete(f"/api/v1/products/{product['id']}")

    assert response.status_code == 409
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "product_has_active_listings"
    details = body["error"]["details"]
    assert details["product_id"] == product["id"]
    assert details["product_name"] == "Camiseta"
    assert details["listings"] == [
        {
            "id": "MLB123",
            "status": "active",
            "permalink": "https://produto.mercadolivre.com.br/MLB-123",
        }
    ]
    # Nothing was deleted.
    assert client.get(f"/api/v1/products/{product['id']}").status_code == 200


def test_delete_product_blocks_active_mapping_when_details_are_unavailable(
    client,
):
    # No entry in listing_details: enrichment falls back to the mapping flag.
    product, _sku, _mapping = _make_product_with_active_mapping(client)

    response = client.delete(f"/api/v1/products/{product['id']}")

    assert response.status_code == 409
    details = response.json()["error"]["details"]
    assert details["listings"] == [
        {"id": "MLB123", "status": None, "permalink": None}
    ]


def test_delete_product_falls_back_when_listing_metadata_is_unavailable(
    client, monkeypatch
):
    import app.api.routes.products as products_module
    from app.core.errors import APIError

    product, _sku, _mapping = _make_product_with_active_mapping(client)

    async def failing_batch_details(tenant_id: str, item_ids: list[str]):
        raise APIError(
            status_code=503,
            code="listing_details_unavailable",
            message="indisponivel",
        )

    monkeypatch.setattr(
        products_module.integrations_client,
        "batch_item_details",
        failing_batch_details,
    )

    response = client.delete(f"/api/v1/products/{product['id']}")

    assert response.status_code == 409
    details = response.json()["error"]["details"]
    assert details["listings"] == [
        {"id": "MLB123", "status": None, "permalink": None}
    ]


def test_unbind_product_listings_then_delete(client, db_engine, listing_details):
    product, _sku, mapping = _make_product_with_active_mapping(client)
    listing_details["MLB123"] = {"status": "active", "permalink": None}

    unbind = client.post(f"/api/v1/products/{product['id']}/unbind-listings")

    assert unbind.status_code == 200
    assert unbind.json() == {
        "unbound": 1,
        "platform_product_ids": ["MLB123"],
    }

    with Session(db_engine) as session:
        stored = session.get(PlatformMapping, mapping["id"])
        assert stored is not None
        assert stored.is_deleted is True
        assert stored.deleted_reason == "product_deleted"

    assert client.delete(f"/api/v1/products/{product['id']}").status_code == 204
    assert client.get(f"/api/v1/products/{product['id']}").status_code == 404

    # Idempotent: the product is gone, so the endpoint reports not found.
    assert (
        client.post(f"/api/v1/products/{product['id']}/unbind-listings").status_code
        == 404
    )


def test_delete_product_allows_paused_listing(client, db_engine, listing_details):
    product, _sku, mapping = _make_product_with_active_mapping(client)
    listing_details["MLB123"] = {"status": "paused", "permalink": None}

    assert client.delete(f"/api/v1/products/{product['id']}").status_code == 204

    with Session(db_engine) as session:
        stored = session.get(PlatformMapping, mapping["id"])
        assert stored is not None
        assert stored.is_active is False
        assert stored.is_deleted is False


def test_delete_product_allows_closed_listing(client, db_engine, listing_details):
    product, _sku, mapping = _make_product_with_active_mapping(client)
    listing_details["MLB123"] = {"status": "closed", "permalink": None}

    assert client.delete(f"/api/v1/products/{product['id']}").status_code == 204

    with Session(db_engine) as session:
        stored = session.get(PlatformMapping, mapping["id"])
        assert stored is not None
        assert stored.is_active is False


def test_update_product_refreshes_updated_at(client, db_engine):
    product_id = client.post(
        "/api/v1/products", json={"name": "Produto A"}
    ).json()["id"]
    old = datetime(2020, 1, 1, tzinfo=UTC)
    with Session(db_engine) as session:
        stored = session.get(Product, product_id)
        stored.updated_at = old
        session.add(stored)
        session.commit()

    response = client.put(
        f"/api/v1/products/{product_id}", json={"name": "Produto B"}
    )

    assert response.status_code == 200
    updated = datetime.fromisoformat(
        response.json()["updated_at"].replace("Z", "+00:00")
    )
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    assert updated > old


def test_update_sku_refreshes_updated_at(client, db_engine):
    product = client.post("/api/v1/products", json={"name": "Produto"}).json()
    sku = client.post(
        "/api/v1/skus",
        json={"product_id": product["id"], "internal_sku": "SKU-UPDATED"},
    ).json()
    old = datetime(2020, 1, 1, tzinfo=UTC)
    with Session(db_engine) as session:
        stored = session.get(SKU, sku["id"])
        stored.updated_at = old
        session.add(stored)
        session.commit()

    response = client.put(
        f"/api/v1/skus/{sku['id']}", json={"stock_quantity": 3}
    )

    assert response.status_code == 200
    updated = datetime.fromisoformat(
        response.json()["updated_at"].replace("Z", "+00:00")
    )
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    assert updated > old


# =============================================================================
# Plan 11: Product + SKU Composite Endpoints & Multi-Tenant Uniqueness Tests
# =============================================================================


def test_create_product_composite_success(client):
    payload = {
        "name": "Composite Product",
        "description": "Composite description",
        "internal_sku": "COMP-1",
        "price": 49.90,
        "stock_quantity": 15,
        "pictures": ["https://example.com/p1.jpg"],
    }
    response = client.post("/api/v1/products/composite", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Composite Product"
    assert body["description"] == "Composite description"
    assert body["pictures"] == ["https://example.com/p1.jpg"]
    assert "sku" in body
    assert body["sku"]["internal_sku"] == "COMP-1"
    assert float(body["sku"]["price"]) == 49.90
    assert body["sku"]["stock_quantity"] == 15
    assert body["sku"]["product_id"] == body["id"]


def test_create_product_composite_duplicate_sku_same_tenant_conflicts(client):
    payload = {
        "name": "First Product",
        "internal_sku": "COMP-DUP",
        "price": 10.0,
        "stock_quantity": 5,
    }
    assert client.post("/api/v1/products/composite", json=payload).status_code == 201

    payload2 = {
        "name": "Second Product",
        "internal_sku": "COMP-DUP",
        "price": 20.0,
        "stock_quantity": 8,
    }
    response = client.post("/api/v1/products/composite", json=payload2)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_create_product_composite_allows_same_sku_across_different_tenants(client, monkeypatch):
    import app.api.routes.products as products_module

    payload = {
        "name": "Tenant 1 Product",
        "internal_sku": "SHARED-SKU-1",
        "price": 15.0,
        "stock_quantity": 2,
    }
    # Create under default test-tenant
    res1 = client.post("/api/v1/products/composite", json=payload)
    assert res1.status_code == 201

    # Override tenant to another tenant
    from app.api.deps import get_tenant_id
    from app.main import app

    app.dependency_overrides[get_tenant_id] = lambda: "tenant-two"
    try:
        res2 = client.post("/api/v1/products/composite", json=payload)
        assert res2.status_code == 201
        assert res2.json()["tenant_id"] == "tenant-two"
        assert res2.json()["sku"]["internal_sku"] == "SHARED-SKU-1"
    finally:
        app.dependency_overrides[get_tenant_id] = lambda: "test-tenant"


def test_create_product_composite_reuses_soft_deleted_sku(client):
    payload = {
        "name": "Reused SKU Product",
        "internal_sku": "REUSE-1",
        "price": 30.0,
        "stock_quantity": 10,
    }
    created = client.post("/api/v1/products/composite", json=payload).json()
    assert client.delete(f"/api/v1/products/{created['id']}").status_code == 204

    # Now create again with the same internal_sku
    response = client.post("/api/v1/products/composite", json=payload)
    assert response.status_code == 201
    assert response.json()["sku"]["internal_sku"] == "REUSE-1"


def test_update_product_composite_success(client):
    created = client.post(
        "/api/v1/products/composite",
        json={
            "name": "Original Name",
            "internal_sku": "COMP-ORIG",
            "price": 25.0,
            "stock_quantity": 10,
        },
    ).json()

    update_payload = {
        "name": "Updated Name",
        "internal_sku": "COMP-NEW",
        "price": 35.0,
        "stock_quantity": 20,
    }
    response = client.put(f"/api/v1/products/{created['id']}/composite", json=update_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Updated Name"
    assert body["sku"]["internal_sku"] == "COMP-NEW"
    assert float(body["sku"]["price"]) == 35.0
    assert body["sku"]["stock_quantity"] == 20


def test_update_product_composite_locks_internal_sku_with_active_mapping(client):
    created = client.post(
        "/api/v1/products/composite",
        json={
            "name": "Locked Product",
            "internal_sku": "LOCKED-SKU",
            "price": 25.0,
            "stock_quantity": 10,
        },
    ).json()

    # Link an active platform mapping
    client.post(
        "/api/v1/platform-mappings",
        json={
            "sku_id": created["sku"]["id"],
            "platform": "mercado_livre",
            "platform_sku": "LOCKED-SKU",
            "platform_product_id": "MLB999",
        },
    )

    # Attempt to change internal_sku
    response = client.put(
        f"/api/v1/products/{created['id']}/composite",
        json={"internal_sku": "LOCKED-SKU-RENAMED"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "internal_sku_locked"

    # Plan 12: ML-managed fields (name, price) are read-only when listing is active.
    response_locked = client.put(
        f"/api/v1/products/{created['id']}/composite",
        json={"name": "Name Changed Freely", "price": 99.0},
    )
    assert response_locked.status_code == 400
    assert response_locked.json()["error"]["code"] == "ml_managed_field_readonly"

    # Only stock_quantity can be edited locally.
    response_ok = client.put(
        f"/api/v1/products/{created['id']}/composite",
        json={"stock_quantity": 999},
    )
    assert response_ok.status_code == 200
    assert response_ok.json()["sku"]["stock_quantity"] == 999
    assert response_ok.json()["sku"]["internal_sku"] == "LOCKED-SKU"

