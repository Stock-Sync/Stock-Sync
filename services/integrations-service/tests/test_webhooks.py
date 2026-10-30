import json

WEBHOOK_URL = "/api/v1/integrations/webhooks/mercadolivre"


def _notification(topic="items", resource="/items/MLB1", user_id=123):
    return {
        "user_id": user_id,
        "resource": resource,
        "topic": topic,
        "received": "2026-10-23T12:00:00",
        "sent": "2026-10-23T12:00:00",
        "attempts": 1,
        "id": "1",
    }


def test_item_notification_is_queued(client):
    response = client.post(WEBHOOK_URL, json=_notification())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    events = client.published_events
    assert len(events) == 1
    event_type, payload = events[0]
    assert event_type == "items_changed"
    assert payload["ml_user_id"] == 123
    assert payload["resource"] == "/items/MLB1"


def test_order_notification_v2_is_queued(client):
    response = client.post(
        WEBHOOK_URL, json=_notification(topic="orders_v2", resource="/orders/99")
    )
    assert response.status_code == 200
    event_type, payload = client.published_events[0]
    assert event_type == "order_created"
    assert payload["resource"] == "/orders/99"


def test_legacy_orders_topic_is_queued(client):
    response = client.post(
        WEBHOOK_URL, json=_notification(topic="orders", resource="/orders/100")
    )
    assert response.status_code == 200
    assert client.published_events[0][0] == "order_created"


def test_unknown_topic_is_ignored(client):
    response = client.post(WEBHOOK_URL, json=_notification(topic="questions"))
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert client.published_events == []


def test_malformed_payload_is_rejected(client):
    response = client.post(WEBHOOK_URL, content=b"not-json")
    assert response.status_code == 400


def test_signature_required_when_secret_configured(client, monkeypatch):
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "ml_webhook_secret", "topsecret")
    # The route module imported settings by reference (same object), so the
    # monkeypatch applies there too.

    body = json.dumps(_notification())
    # Missing signature → 401
    response = client.post(
        WEBHOOK_URL, content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401

    # Correct HMAC signature → accepted
    import hashlib
    import hmac

    signature = hmac.new(b"topsecret", body.encode(), hashlib.sha256).hexdigest()
    response = client.post(
        WEBHOOK_URL,
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": signature},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_publish_failure_returns_503(client, monkeypatch):
    import app.api.routes.webhooks as webhooks_module

    async def failing_publish(event_type, payload):
        return None

    monkeypatch.setattr(webhooks_module, "publish_event", failing_publish)
    response = client.post(WEBHOOK_URL, json=_notification())
    assert response.status_code == 503
