INTERNAL_HEADERS = {"X-Internal-Secret": "test-secret"}


def _sale_payload(**overrides):
    payload = {
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
        "ordered_at": "2026-10-23T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_upsert_order_requires_internal_secret(client):
    response = client.post("/api/v1/orders/internal", json=_sale_payload())
    assert response.status_code == 401


def test_upsert_order_rejects_wrong_secret(client):
    response = client.post(
        "/api/v1/orders/internal",
        json=_sale_payload(),
        headers={"X-Internal-Secret": "wrong"},
    )
    assert response.status_code == 401


def test_upsert_order_creates(client):
    response = client.post(
        "/api/v1/orders/internal", json=_sale_payload(), headers=INTERNAL_HEADERS
    )
    assert response.status_code == 201
    body = response.json()
    assert body["marketplace_order_id"] == "ML-100"
    assert body["internal_sku"] == "SKU-1"
    assert body["buyer_nickname"] == "joao-buyer"
    assert body["quantity"] == 2
    assert body["total_amount"] == 100.0


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

    orders = client.get("/api/v1/orders").json()
    assert orders["total"] == 1


def test_upsert_order_allows_unmapped_sku(client):
    payload = _sale_payload(internal_sku=None, sku_id=None)
    response = client.post("/api/v1/orders/internal", json=payload, headers=INTERNAL_HEADERS)
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

    page1 = client.get("/api/v1/orders", params={"page": 1, "limit": 2}).json()
    assert page1["total"] == 3
    assert page1["page"] == 1
    assert len(page1["items"]) == 2
    # newest first
    assert page1["items"][0]["marketplace_order_id"] == "ML-2"

    page2 = client.get("/api/v1/orders", params={"page": 2, "limit": 2}).json()
    assert len(page2["items"]) == 1


def test_list_orders_empty(client):
    body = client.get("/api/v1/orders").json()
    assert body == {"items": [], "total": 0, "page": 1, "limit": 20}
