import hashlib

import pytest
from pydantic import ValidationError

WEBHOOK_URL = "/api/v1/integrations/webhooks/mercadolivre/test-secret"
LEGACY_URL = "/api/v1/integrations/webhooks/mercadolivre"


def _notification(topic="items", resource="/items/MLB1", user_id=123, **extra):
    """Build a notification shaped like the official ML examples.

    ``orders_v2`` and ``items`` payloads have no notification id; callers add
    ``id``/``_id`` only when testing that path.
    """
    payload = {
        "user_id": user_id,
        "resource": resource,
        "topic": topic,
        "application_id": 5503910054141466,
        "received": "2026-10-23T12:00:00",
        "sent": "2026-10-23T12:00:00",
        "attempts": 1,
    }
    payload.update(extra)
    return payload


def test_webhook_secret_must_be_url_path_safe():
    from app.core.config import Settings

    assert Settings(ml_webhook_secret="abc-123_X.Y~z").ml_webhook_secret
    with pytest.raises(ValidationError):
        Settings(ml_webhook_secret="bad/secret")


def test_item_notification_without_id_is_queued(client):
    response = client.post(WEBHOOK_URL, json=_notification())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"

    events = client.published_events
    assert len(events) == 1
    event_type, payload, event_id = events[0]
    assert event_type == "items_changed"
    assert payload["ml_user_id"] == 123
    assert payload["resource"] == "/items/MLB1"
    assert payload["notification_id"] is None
    # Plan 9: the event timestamp is forwarded for out-of-order protection.
    assert payload["sent"] == "2026-10-23T12:00:00"
    assert payload["received"] == "2026-10-23T12:00:00"
    # Deterministic key is derived from topic + seller + resource.
    assert event_id.startswith("mlwh:items:")
    assert event_id == body["event_id"]


def test_order_notification_v2_without_id_is_queued(client):
    response = client.post(
        WEBHOOK_URL, json=_notification(topic="orders_v2", resource="/orders/99")
    )

    assert response.status_code == 200
    event_type, payload, _event_id = client.published_events[0]
    assert event_type == "order_created"
    assert payload["resource"] == "/orders/99"


def test_legacy_orders_topic_is_queued(client):
    response = client.post(WEBHOOK_URL, json=_notification(topic="orders", resource="/orders/100"))

    assert response.status_code == 200
    assert client.published_events[0][0] == "order_created"


def test_id_and_underscore_id_are_equivalent_for_deduplication(client):
    first = client.post(
        WEBHOOK_URL,
        json=_notification(topic="orders_v2", resource="/orders/1", id="notif-1"),
    )
    second = client.post(
        WEBHOOK_URL,
        json=_notification(topic="orders_v2", resource="/orders/1", _id="notif-1"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert len(client.published_events) == 1
    expected = "mlwh:orders_v2:" + hashlib.sha256(b"id:notif-1").hexdigest()
    assert client.published_events[0][2] == expected


def test_unknown_topic_is_ignored(client):
    response = client.post(WEBHOOK_URL, json=_notification(topic="questions"))

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert client.published_events == []


def test_malformed_payload_is_rejected(client):
    response = client.post(WEBHOOK_URL, content=b"not-json")

    assert response.status_code == 400


def test_missing_secret_is_rejected_when_configured(client):
    response = client.post(LEGACY_URL, json=_notification())

    assert response.status_code == 401
    assert client.published_events == []


def test_wrong_secret_is_rejected(client):
    response = client.post(
        "/api/v1/integrations/webhooks/mercadolivre/wrong",
        json=_notification(),
    )

    assert response.status_code == 401
    assert client.published_events == []


def test_unconfigured_secret_is_rejected_outside_debug(client, monkeypatch):
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "ml_webhook_secret", "")
    monkeypatch.setattr(config_module.settings, "debug", False)

    response = client.post(LEGACY_URL, json=_notification())

    assert response.status_code == 503
    assert client.published_events == []


def test_unconfigured_secret_is_allowed_in_debug(client, monkeypatch):
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "ml_webhook_secret", "")
    monkeypatch.setattr(config_module.settings, "debug", True)

    response = client.post(LEGACY_URL, json=_notification())

    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_duplicate_notification_is_not_republished(client):
    payload = _notification(topic="orders_v2", resource="/orders/99")

    first = client.post(WEBHOOK_URL, json=payload)
    second = client.post(WEBHOOK_URL, json=payload)

    assert first.json() == {
        "status": "queued",
        "event_id": client.published_events[0][2],
    }
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert len(client.published_events) == 1


def test_changed_retry_timestamp_still_deduplicates_without_id(client):
    first = client.post(
        WEBHOOK_URL,
        json=_notification(topic="items", resource="/items/MLB1", sent="2026-10-23T12:00:00"),
    )
    # A redelivery may carry a different `sent`/`attempts`, but the resource is
    # the same and sync-service would refetch the same state anyway.
    second = client.post(
        WEBHOOK_URL,
        json=_notification(
            topic="items",
            resource="/items/MLB1",
            sent="2026-10-23T12:05:00",
            attempts=2,
        ),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert len(client.published_events) == 1


def test_publish_failure_returns_503_and_allows_retry(client, monkeypatch):
    import app.api.routes.webhooks as webhooks_module

    async def failing_publish(event_type, payload, event_id=None):
        return None

    monkeypatch.setattr(webhooks_module, "publish_event", failing_publish)
    response = client.post(WEBHOOK_URL, json=_notification())

    assert response.status_code == 503
    # Nothing was marked as seen, so ML's retry can enqueue the event.
    assert client.seen_notifications == set()

    async def succeeding_publish(event_type, payload, event_id=None):
        client.published_events.append((event_type, payload, event_id))
        return event_id or f"{event_type}:test-1"

    monkeypatch.setattr(webhooks_module, "publish_event", succeeding_publish)

    retry = client.post(WEBHOOK_URL, json=_notification())
    assert retry.status_code == 200
    assert retry.json()["status"] == "queued"
    assert len(client.published_events) == 1
