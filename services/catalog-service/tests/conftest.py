import pytest
from app.api.deps import get_tenant_id
from app.db.session import get_session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Session, SQLModel


@pytest.fixture(autouse=True)
def stock_events(monkeypatch):
    """Capture ``stock_adjust`` publishes instead of writing to Redis.

    Tests run on the host and may share the development Redis; publishing for
    real would feed sync-service with synthetic events (and dead-letter the
    ones without a tenant). The fixture also exposes the calls to tests that
    need to assert the event payload.
    """
    import app.api.routes.platform_mappings as mappings_module
    import app.api.routes.products as products_module
    import app.api.routes.skus as skus_module

    calls: list[dict] = []

    def fake_publish(
        sku_id,
        internal_sku,
        previous_quantity,
        new_quantity,
        source,
        tenant_id,
    ):
        calls.append(
            {
                "sku_id": sku_id,
                "internal_sku": internal_sku,
                "previous_quantity": previous_quantity,
                "new_quantity": new_quantity,
                "source": source,
                "tenant_id": tenant_id,
            }
        )
        return f"event-{len(calls)}"

    monkeypatch.setattr(skus_module, "publish_stock_adjust", fake_publish)
    monkeypatch.setattr(mappings_module, "publish_stock_adjust", fake_publish)
    monkeypatch.setattr(products_module, "publish_stock_adjust", fake_publish)
    return calls


@pytest.fixture()
def listing_details() -> dict[str, dict]:
    """Mutable local mirror metadata used by the batch-details stub."""
    return {}


@pytest.fixture(autouse=True)
def stub_integrations_client(monkeypatch, listing_details):
    """Keep unit tests offline: the orchestrated unbind talks to integrations.

    Tests that exercise the remote failure/success paths patch these functions
    again inside the test body.
    """
    import app.api.routes.platform_mappings as mappings_module
    import app.api.routes.products as products_module

    calls: list[tuple] = []

    async def fake_prepare_item_unlink(tenant_id: str, item_id: str):
        calls.append(("unlink", tenant_id, item_id))
        return {"item_id": item_id, "remote_action": "stubbed"}

    async def fake_update_seller_custom_field(
        tenant_id: str, item_id: str, seller_custom_field: str
    ):
        calls.append(("seller_custom_field", tenant_id, item_id, seller_custom_field))
        return {"item_id": item_id, "seller_custom_field": seller_custom_field}

    async def fake_batch_item_details(tenant_id: str, item_ids: list[str]):
        calls.append(("batch_details", tenant_id, tuple(item_ids)))
        return [
            {
                "id": item_id,
                "found": item_id in listing_details,
                **listing_details.get(
                    item_id,
                    {"status": None, "permalink": None},
                ),
            }
            for item_id in item_ids
        ]

    monkeypatch.setattr(
        mappings_module.integrations_client,
        "prepare_item_unlink",
        fake_prepare_item_unlink,
    )
    monkeypatch.setattr(
        mappings_module.integrations_client,
        "update_seller_custom_field",
        fake_update_seller_custom_field,
    )
    monkeypatch.setattr(
        products_module.integrations_client,
        "batch_item_details",
        fake_batch_item_details,
    )
    return calls


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(db_engine):
    def override_get_session():
        with Session(db_engine) as session:
            yield session

    def override_get_tenant_id():
        return "test-tenant"

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_tenant_id] = override_get_tenant_id
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
