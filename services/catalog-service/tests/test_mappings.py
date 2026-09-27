"""
Testes para o catalog-service - Mappings endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.main import app
from app.db.session import get_session
from app.models.product import Product
from app.models.mapping import ProductPlatformMapping


# Test database (in-memory SQLite)
@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_create_mapping(client: TestClient, session: Session):
    """Test creating a new mapping via API."""
    # First create a product
    product = Product(
        user_id="user-uuid-123",
        name="Test Product",
        sku="SKU-001",
        price=99.90,
        stock_quantity=100,
    )
    session.add(product)
    session.commit()
    session.refresh(product)

    # Create mapping
    mapping_data = {
        "user_id": "user-uuid-123",
        "platform": "mercadolivre",
        "external_item_id": "MLB123456789",
        "external_model_id": 0,
        "product_id": product.id,
        "sku": "SKU-001",
    }
    response = client.post("/api/v1/mappings/", json=mapping_data)
    assert response.status_code == 201
    data = response.json()
    assert data["platform"] == "mercadolivre"
    assert data["sku"] == "SKU-001"
    assert data["external_item_id"] == "MLB123456789"
    assert data["product_id"] == product.id
    assert data["is_active"] is True


def test_get_mapping_by_external_id(client: TestClient, session: Session):
    """Test looking up mapping by marketplace item ID."""
    # Create product
    product = Product(
        user_id="user-uuid-123",
        name="Test Product 2",
        sku="SKU-002",
        price=49.90,
        stock_quantity=50,
    )
    session.add(product)
    session.commit()
    session.refresh(product)

    # Create mapping
    mapping = ProductPlatformMapping(
        user_id="user-uuid-123",
        platform="shopee",
        external_item_id="123456789",
        external_model_id=0,
        product_id=product.id,
        sku="SKU-002",
        is_active=True,
    )
    session.add(mapping)
    session.commit()

    # Retrieve mapping
    response = client.get(
        "/api/v1/mappings/by-external-id",
        params={
            "user_id": "user-uuid-123",
            "platform": "shopee",
            "external_item_id": "123456789",
            "external_model_id": 0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-002"
    assert data["platform"] == "shopee"
    assert data["external_item_id"] == "123456789"


def test_get_mapping_not_found(client: TestClient):
    """Test 404 when mapping doesn't exist."""
    response = client.get(
        "/api/v1/mappings/by-external-id",
        params={
            "user_id": "user-uuid-123",
            "platform": "mercadolivre",
            "external_item_id": "NONEXISTENT",
        },
    )
    assert response.status_code == 404


def test_create_duplicate_mapping_fails(client: TestClient, session: Session):
    """Test that creating duplicate mapping returns 409."""
    product = Product(
        user_id="user-uuid-123",
        name="Test Product 3",
        sku="SKU-003",
        price=29.90,
        stock_quantity=25,
    )
    session.add(product)
    session.commit()
    session.refresh(product)

    mapping_data = {
        "user_id": "user-uuid-123",
        "platform": "mercadolivre",
        "external_item_id": "MLB999999",
        "external_model_id": 0,
        "product_id": product.id,
        "sku": "SKU-003",
    }

    # First creation succeeds
    response1 = client.post("/api/v1/mappings/", json=mapping_data)
    assert response1.status_code == 201

    # Second creation fails
    response2 = client.post("/api/v1/mappings/", json=mapping_data)
    assert response2.status_code == 409


def test_get_product_by_sku(client: TestClient, session: Session):
    """Test getting product by SKU."""
    product = Product(
        user_id="user-uuid-123",
        name="Test Product 4",
        sku="SKU-004",
        price=19.90,
        stock_quantity=10,
    )
    session.add(product)
    session.commit()

    response = client.get(
        "/api/v1/products/by-sku",
        params={"user_id": "user-uuid-123", "sku": "SKU-004"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "SKU-004"
    assert data["user_id"] == "user-uuid-123"
    assert data["name"] == "Test Product 4"


def test_get_stock_quantity(client: TestClient, session: Session):
    """Test getting stock quantity."""
    product = Product(
        user_id="user-uuid-123",
        name="Test Product 5",
        sku="SKU-005",
        price=9.90,
        stock_quantity=42,
    )
    session.add(product)
    session.commit()

    response = client.get("/api/v1/products/stock/user-uuid-123/SKU-005")
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 42


def test_list_mappings(client: TestClient, session: Session):
    """Test listing mappings with filters."""
    product = Product(
        user_id="user-uuid-123",
        name="Test Product 6",
        sku="SKU-006",
        price=5.00,
        stock_quantity=5,
    )
    session.add(product)
    session.commit()
    session.refresh(product)

    # Create multiple mappings
    for i in range(3):
        mapping = ProductPlatformMapping(
            user_id="user-uuid-123",
            platform="mercadolivre",
            external_item_id=f"MLB{i}",
            external_model_id=0,
            product_id=product.id,
            sku="SKU-006",
            is_active=True,
        )
        session.add(mapping)
    session.commit()

    response = client.get(
        "/api/v1/mappings/",
        params={"user_id": "user-uuid-123", "limit": 10},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


def test_delete_mapping(client: TestClient, session: Session):
    """Test deactivating a mapping (soft delete)."""
    product = Product(
        user_id="user-uuid-123",
        name="Test Product 7",
        sku="SKU-007",
        price=100.00,
        stock_quantity=1,
    )
    session.add(product)
    session.commit()
    session.refresh(product)

    mapping = ProductPlatformMapping(
        user_id="user-uuid-123",
        platform="mercadolivre",
        external_item_id="MLBDELETE",
        external_model_id=0,
        product_id=product.id,
        sku="SKU-007",
        is_active=True,
    )
    session.add(mapping)
    session.commit()
    session.refresh(mapping)

    # Delete (soft delete)
    response = client.delete(f"/api/v1/mappings/{mapping.id}")
    assert response.status_code == 204

    # Verify it's deactivated
    session.refresh(mapping)
    assert mapping.is_active is False

    # Verify it doesn't appear in by-external-id lookup
    response = client.get(
        "/api/v1/mappings/by-external-id",
        params={
            "user_id": "user-uuid-123",
            "platform": "mercadolivre",
            "external_item_id": "MLBDELETE",
        },
    )
    assert response.status_code == 404