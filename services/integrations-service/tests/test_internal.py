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
