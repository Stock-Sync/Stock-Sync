def _make_sku(client):
    product = client.post("/api/v1/products", json={"name": "Produto"}).json()
    return client.post(
        "/api/v1/skus", json={"product_id": product["id"], "internal_sku": "SKU-1"}
    ).json()


def _make_mapping(client, sku_id, platform="mercado_livre", platform_sku="ML-1", **extra):
    payload = {"sku_id": sku_id, "platform": platform, "platform_sku": platform_sku, **extra}
    return client.post("/api/v1/platform-mappings", json=payload)


def test_create_platform_mapping(client):
    sku = _make_sku(client)
    response = _make_mapping(client, sku["id"])
    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "mercado_livre"
    assert body["platform_sku"] == "ML-1"


def test_create_platform_mapping_sku_not_found(client):
    response = _make_mapping(client, 999, platform="shopee", platform_sku="SH-1")
    assert response.status_code == 404


def test_create_platform_mapping_deleted_sku_not_found(client):
    sku = _make_sku(client)
    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204

    response = _make_mapping(client, sku["id"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_create_platform_mapping_invalid_platform(client):
    sku = _make_sku(client)
    response = _make_mapping(client, sku["id"], platform="amazon", platform_sku="AM-1")
    assert response.status_code == 422


def test_list_platform_mappings_empty(client):
    response = client.get("/api/v1/platform-mappings")
    assert response.status_code == 200
    assert response.json() == []


def test_filter_by_platform(client):
    sku = _make_sku(client)
    _make_mapping(client, sku["id"], platform="mercado_livre", platform_sku="ML-1")
    _make_mapping(client, sku["id"], platform="shopee", platform_sku="SH-1")

    response = client.get("/api/v1/platform-mappings", params={"platform": "mercado_livre"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["platform_sku"] == "ML-1"


def test_filter_by_platform_product_id(client):
    sku = _make_sku(client)
    _make_mapping(
        client, sku["id"], platform_sku="MLB123", platform_product_id="MLB123"
    )
    _make_mapping(client, sku["id"], platform_sku="MLB456", platform_product_id="MLB456")

    response = client.get(
        "/api/v1/platform-mappings", params={"platform_product_id": "MLB123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["platform_product_id"] == "MLB123"


def test_filter_by_platform_sku(client):
    sku = _make_sku(client)
    _make_mapping(client, sku["id"], platform_sku="SKU-A")
    _make_mapping(client, sku["id"], platform_sku="SKU-B")

    response = client.get("/api/v1/platform-mappings", params={"platform_sku": "SKU-B"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["platform_sku"] == "SKU-B"
