import uuid


def test_create_platform_mapping(client):
    product = client.post("/api/v1/products", json={"name": "Produto"}).json()
    sku = client.post("/api/v1/skus", json={"product_id": product["id"], "internal_sku": "SKU-1"}).json()
    response = client.post(
        "/api/v1/platform-mappings",
        json={"sku_id": sku["id"], "platform": "mercado_livre", "platform_sku": "ML-1"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "mercado_livre"
    assert body["platform_sku"] == "ML-1"
    assert "user_id" in body


def test_create_platform_mapping_sku_not_found(client):
    response = client.post(
        "/api/v1/platform-mappings",
        json={"sku_id": 999, "platform": "shopee", "platform_sku": "SH-1"},
    )
    assert response.status_code == 404


def test_create_platform_mapping_invalid_platform(client):
    product = client.post("/api/v1/products", json={"name": "Produto"}).json()
    sku = client.post("/api/v1/skus", json={"product_id": product["id"], "internal_sku": "SKU-1"}).json()
    response = client.post(
        "/api/v1/platform-mappings",
        json={"sku_id": sku["id"], "platform": "amazon", "platform_sku": "AM-1"},
    )
    assert response.status_code == 422


def test_list_platform_mappings_empty(client):
    response = client.get("/api/v1/platform-mappings")
    assert response.status_code == 200
    assert response.json() == []
