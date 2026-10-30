from app.models import SKU, PlatformMapping
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
    sku = _make_sku(client)
    response = client.put(f"/api/v1/skus/{sku['id']}", json={"stock_quantity": 25})
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 25


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


def test_create_sku_reusing_deleted_code_conflicts(client):
    product = _make_product(client)
    payload = {"product_id": product["id"], "internal_sku": "SKU-ARCHIVED"}
    assert client.post("/api/v1/skus", json=payload).status_code == 201
    deleted = client.get("/api/v1/skus").json()[0]
    assert client.delete(f"/api/v1/skus/{deleted['id']}").status_code == 204

    response = client.post("/api/v1/skus", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


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
