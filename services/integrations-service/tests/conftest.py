import pytest
from app.db.session import get_session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Session


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # NOTE: tables are intentionally not created here — MarketplaceItem uses
    # JSONB (PostgreSQL-only). The routes under test either skip the DB
    # entirely (webhooks) or reject at the secret guard before using it.
    yield engine
    engine.dispose()


@pytest.fixture()
def client(db_engine, monkeypatch):
    def override_get_session():
        with Session(db_engine) as session:
            yield session

    # Avoid any real Redis traffic in tests: stub the stream publisher.
    published: list[tuple[str, dict]] = []

    async def fake_publish_event(event_type: str, payload: dict) -> str:
        published.append((event_type, payload))
        return f"{event_type}:test-1"

    import app.api.routes.webhooks as webhooks_module

    monkeypatch.setattr(webhooks_module, "publish_event", fake_publish_event)

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        test_client.published_events = published  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
