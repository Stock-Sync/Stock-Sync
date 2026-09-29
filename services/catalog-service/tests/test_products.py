def test_create_product(client):
    response = client.post("/products", json={"name": "Produto A", "description": "descricao"})
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "Produto A"
    assert body["description"] == "descricao"


def test_create_product_validation_error(client):
    response = client.post("/products", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "validation_error"


def test_list_products(client):
    client.post("/products", json={"name": "Produto A"})
    client.post("/products", json={"name": "Produto B"})
    response = client.get("/products")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_products_empty(client):
    response = client.get("/products")
    assert response.status_code == 200
    assert response.json() == []


def test_get_product(client):
    product_id = client.post("/products", json={"name": "Produto A"}).json()["id"]
    response = client.get(f"/products/{product_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Produto A"


def test_get_product_not_found(client):
    response = client.get("/products/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_update_product(client):
    product_id = client.post("/products", json={"name": "Produto A"}).json()["id"]
    response = client.put(f"/products/{product_id}", json={"name": "Produto B"})
    assert response.status_code == 200
    assert response.json()["name"] == "Produto B"


def test_update_product_not_found(client):
    response = client.put("/products/999", json={"name": "Produto B"})
    assert response.status_code == 404


def test_delete_product(client):
    product_id = client.post("/products", json={"name": "Produto A"}).json()["id"]
    response = client.delete(f"/products/{product_id}")
    assert response.status_code == 204
    assert client.get(f"/products/{product_id}").status_code == 404
