"""Sync API route tests (pull, status and dead-letter replay)."""

import fakeredis.aioredis
from app.models import SyncEvent
from app.streams.consts import DEAD_STREAM_KEY, STREAM_KEY
from jose import jwt

INTERNAL_HEADERS = {"X-Internal-Secret": "test-secret"}


def _tenant_cookie(tenant_id="tenant-1", token_type="access"):
    from app.core.config import settings

    token = jwt.encode(
        {"tenant_id": tenant_id, "type": token_type},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"access_token": token}


def test_pull_requires_tenant(client):
    response = client.post("/api/v1/sync/listings/pull")
    assert response.status_code == 401


def test_pull_rejects_standalone_tenant_header(client):
    response = client.post(
        "/api/v1/sync/listings/pull", headers={"X-Tenant-ID": "tenant-1"}
    )
    assert response.status_code == 401


def test_pull_rejects_legacy_tenant_cookie(client):
    response = client.post(
        "/api/v1/sync/listings/pull", cookies={"tenant_id": "tenant-1"}
    )
    assert response.status_code == 401


def test_pull_rejects_refresh_token(client):
    response = client.post(
        "/api/v1/sync/listings/pull", cookies=_tenant_cookie(token_type="refresh")
    )
    assert response.status_code == 401


def test_pull_returns_summary(client, monkeypatch):
    import app.api.routes.sync as sync_module

    class FakeService:
        def __init__(self, session, tenant_id):
            self.tenant_id = tenant_id

        async def pull(self):
            assert self.tenant_id == "tenant-1"
            return {
                "run_id": 1,
                "status": "completed",
                "items_found": 2,
                "items_upserted": 2,
                "mappings_created": 1,
                "errors": [],
            }

    monkeypatch.setattr(sync_module, "ListingsSyncService", FakeService)

    response = client.post(
        "/api/v1/sync/listings/pull", cookies=_tenant_cookie()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items_found"] == 2
    assert body["mappings_created"] == 1


def test_status_reports_empty_pipeline(client, monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

    import app.core.redis as redis_module

    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)

    response = client.get("/api/v1/sync/status", cookies=_tenant_cookie())
    assert response.status_code == 200
    body = response.json()
    assert body["last_pull"] is None
    assert body["stream"]["pending_events"] == 0
    assert body["stream"]["dead_letters"] == 0


def test_status_survives_redis_outage(client, monkeypatch):
    import app.core.redis as redis_module

    class BrokenRedis:
        async def xlen(self, *a):
            raise RuntimeError("redis down")

        async def hlen(self, *a):
            raise RuntimeError("redis down")

    monkeypatch.setattr(redis_module, "get_redis", lambda: BrokenRedis())

    response = client.get("/api/v1/sync/status", cookies=_tenant_cookie())
    assert response.status_code == 200
    body = response.json()
    assert body["stream"] == {
        "pending_events": None,
        "pending_quantity_updates": None,
        "dead_letters": None,
    }


def test_replay_dead_letters_requires_internal_secret(client):
    response = client.post("/api/v1/sync/dead-letters/replay")
    assert response.status_code == 401


def test_replay_dead_letters_rejects_standalone_tenant_header(client):
    response = client.post(
        "/api/v1/sync/dead-letters/replay",
        headers={"X-Tenant-ID": "tenant-1"},
    )
    assert response.status_code == 401


def test_replay_dead_letters_moves_entries_and_resets_event(
    client, db_session, monkeypatch
):
    import asyncio

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    asyncio.run(
        fake.xadd(
            DEAD_STREAM_KEY,
            {
                "event_type": "stock_adjust",
                "event_id": "sa-dead",
                "payload": '{"sku_id": 1, "new_quantity": 5}',
            },
        )
    )
    db_session.add(
        SyncEvent(
            event_type="stock_adjust",
            dedupe_key="sa-dead",
            payload={"sku_id": 1, "new_quantity": 5},
            status="failed",
            retry_count=5,
            error_message="boom",
        )
    )
    db_session.commit()

    import app.core.redis as redis_module

    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)

    response = client.post(
        "/api/v1/sync/dead-letters/replay",
        cookies=_tenant_cookie(),
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["replayed"] == 1

    assert asyncio.run(fake.xlen(DEAD_STREAM_KEY)) == 0
    entries = asyncio.run(fake.xrange(STREAM_KEY))
    assert len(entries) == 1
    assert entries[0][1]["event_id"] == "sa-dead"

    record = db_session.query(SyncEvent).filter_by(dedupe_key="sa-dead").one()
    db_session.refresh(record)
    assert record.status == "pending"
    assert record.retry_count == 0
    assert record.error_message is None
    assert record.processed_at is None
