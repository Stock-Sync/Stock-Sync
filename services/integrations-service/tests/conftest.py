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

    # Avoid any real Redis traffic in tests: stub the stream publisher and the
    # dedupe cache with in-memory equivalents.
    published: list[tuple[str, dict, str | None]] = []
    seen: set[str] = set()

    async def fake_publish_event(
        event_type: str, payload: dict, event_id: str | None = None
    ) -> str:
        published.append((event_type, payload, event_id))
        return event_id or f"{event_type}:test-1"

    async def fake_is_notification_seen(dedupe_key: str) -> bool:
        return dedupe_key in seen

    async def fake_mark_notification_seen(dedupe_key: str, ttl_seconds: int | None = None) -> None:
        seen.add(dedupe_key)

    import app.api.routes.webhooks as webhooks_module
    import app.core.config as config_module

    monkeypatch.setattr(webhooks_module, "publish_event", fake_publish_event)
    monkeypatch.setattr(webhooks_module, "is_notification_seen", fake_is_notification_seen)
    monkeypatch.setattr(webhooks_module, "mark_notification_seen", fake_mark_notification_seen)
    # Webhook tests need a configured secret; individual tests override it.
    monkeypatch.setattr(config_module.settings, "ml_webhook_secret", "test-secret")
    monkeypatch.setattr(config_module.settings, "debug", True)

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        test_client.published_events = published  # type: ignore[attr-defined]
        test_client.seen_notifications = seen  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
