from jose import jwt

INTERNAL_HEADERS = {
    "X-Internal-Secret": "test-secret",
    "X-Tenant-ID": "tenant-1",
}


def _access_cookie(tenant_id: str = "tenant-1") -> dict[str, str]:
    from app.core.config import settings

    token = jwt.encode(
        {"tenant_id": tenant_id, "type": "access"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"access_token": token}


def _refresh_cookie(tenant_id: str = "tenant-1") -> dict[str, str]:
    from app.core.config import settings

    token = jwt.encode(
        {"tenant_id": tenant_id, "type": "refresh"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"access_token": token}


def _sale_payload(**overrides):
    payload = {
        "tenant_id": "tenant-1",
        "marketplace": "mercado_livre",
        "marketplace_order_id": "ML-100",
        "marketplace_item_id": "MLB-1",
        "internal_sku": "SKU-1",
        "sku_id": 7,
        "item_title": "Fone Bluetooth",
        "buyer_nickname": "joao-buyer",
        "quantity": 2,
        "unit_price": 50.0,
        "total_amount": 100.0,
        "currency": "BRL",
        "status": "paid",
        "is_variation": False,
        "ordered_at": "2026-10-23T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_list_orders_requires_tenant(client):
    response = client.get("/api/v1/orders")
    assert response.status_code == 401


def test_list_orders_rejects_standalone_tenant_header(client):
    response = client.get("/api/v1/orders", headers={"X-Tenant-ID": "tenant-1"})
    assert response.status_code == 401


def test_list_orders_rejects_legacy_tenant_cookie(client):
    response = client.get("/api/v1/orders", cookies={"tenant_id": "tenant-1"})
    assert response.status_code == 401


def test_list_orders_rejects_refresh_token(client):
    response = client.get("/api/v1/orders", cookies=_refresh_cookie())
    assert response.status_code == 401


def test_list_orders_accepts_bearer_access_token(client):
    from app.core.config import settings

    token = jwt.encode(
        {"tenant_id": "tenant-1", "type": "access"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get(
        "/api/v1/orders", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


def test_upsert_order_requires_internal_secret(client):
    response = client.post(
        "/api/v1/orders/internal",
        json=_sale_payload(),
        headers={"X-Tenant-ID": "tenant-1"},
    )
    assert response.status_code == 401


def test_upsert_order_rejects_wrong_secret(client):
    response = client.post(
        "/api/v1/orders/internal",
        json=_sale_payload(),
        headers={"X-Internal-Secret": "wrong", "X-Tenant-ID": "tenant-1"},
    )
    assert response.status_code == 401


def test_upsert_order_rejects_tenant_mismatch(client):
    response = client.post(
        "/api/v1/orders/internal",
        json=_sale_payload(tenant_id="tenant-2"),
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 409


def test_upsert_order_creates(client):
    response = client.post(
        "/api/v1/orders/internal", json=_sale_payload(), headers=INTERNAL_HEADERS
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tenant_id"] == "tenant-1"
    assert body["marketplace_order_id"] == "ML-100"
    assert body["internal_sku"] == "SKU-1"
    assert body["buyer_nickname"] == "joao-buyer"
    assert body["quantity"] == 2
    assert body["total_amount"] == 100.0
    assert body["is_variation"] is False


def test_upsert_order_persists_variation_flag(client):
    response = client.post(
        "/api/v1/orders/internal",
        json=_sale_payload(is_variation=True),
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["is_variation"] is True


def test_upsert_order_is_idempotent(client):
    first = client.post(
        "/api/v1/orders/internal", json=_sale_payload(), headers=INTERNAL_HEADERS
    )
    second = client.post(
        "/api/v1/orders/internal", json=_sale_payload(), headers=INTERNAL_HEADERS
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    orders = client.get("/api/v1/orders", cookies=_access_cookie()).json()
    assert orders["total"] == 1


def test_upsert_order_allows_unmapped_sku(client):
    payload = _sale_payload(internal_sku=None, sku_id=None)
    response = client.post(
        "/api/v1/orders/internal", json=payload, headers=INTERNAL_HEADERS
    )
    assert response.status_code == 201
    assert response.json()["internal_sku"] is None


def test_list_orders_pagination_and_order(client):
    for i in range(3):
        client.post(
            "/api/v1/orders/internal",
            json=_sale_payload(
                marketplace_order_id=f"ML-{i}",
                ordered_at=f"2026-10-2{i + 1}T12:00:00Z",
            ),
            headers=INTERNAL_HEADERS,
        )

    page1 = client.get(
        "/api/v1/orders", params={"page": 1, "limit": 2}, cookies=_access_cookie()
    ).json()
    assert page1["total"] == 3
    assert page1["page"] == 1
    assert len(page1["items"]) == 2
    # newest first
    assert page1["items"][0]["marketplace_order_id"] == "ML-2"

    page2 = client.get(
        "/api/v1/orders", params={"page": 2, "limit": 2}, cookies=_access_cookie()
    ).json()
    assert len(page2["items"]) == 1


def test_list_orders_is_tenant_scoped(client):
    client.post(
        "/api/v1/orders/internal", json=_sale_payload(), headers=INTERNAL_HEADERS
    )
    client.post(
        "/api/v1/orders/internal",
        json=_sale_payload(
            tenant_id="tenant-2",
            marketplace_order_id="ML-200",
            marketplace_item_id="MLB-2",
        ),
        headers={"X-Internal-Secret": "test-secret", "X-Tenant-ID": "tenant-2"},
    )

    tenant_1 = client.get("/api/v1/orders", cookies=_access_cookie()).json()
    tenant_2 = client.get(
        "/api/v1/orders", cookies=_access_cookie("tenant-2")
    ).json()

    assert tenant_1["total"] == 1
    assert tenant_1["items"][0]["marketplace_order_id"] == "ML-100"
    assert tenant_2["total"] == 1
    assert tenant_2["items"][0]["marketplace_order_id"] == "ML-200"


def test_list_orders_empty(client):
    body = client.get("/api/v1/orders", cookies=_access_cookie()).json()
    assert body == {"items": [], "total": 0, "page": 1, "limit": 20}
