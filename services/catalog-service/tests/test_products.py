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
