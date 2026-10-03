import uuid


def _make_product(client):
    return client.post("/api/v1/products", json={"name": "Produto"}).json()


def test_create_sku(client):
    product = _make_product(client)
    response = client.post(
        "/api/v1/skus",
        json={
            "product_id": product["id"],
            "internal_sku": "SKU-1",
            "stock_quantity": 10,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["internal_sku"] == "SKU-1"
    assert body["stock_quantity"] == 10
    assert "user_id" in body


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
    product = _make_product(client)
    client.post("/api/v1/skus", json={"product_id": product["id"], "internal_sku": "SKU-1"})
    client.post("/api/v1/skus", json={"product_id": product["id"], "internal_sku": "SKU-2"})
    response = client.get("/api/v1/skus")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_sku_not_found(client):
    response = client.get("/api/v1/skus/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_update_sku(client):
    product = _make_product(client)
    sku_id = client.post(
        "/api/v1/skus", json={"product_id": product["id"], "internal_sku": "SKU-1"}
    ).json()["id"]
    response = client.put(f"/api/v1/skus/{sku_id}", json={"stock_quantity": 25})
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 25
