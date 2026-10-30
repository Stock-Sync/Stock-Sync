"""Sync API route tests (pull and status both require a tenant)."""


import fakeredis.aioredis
from jose import jwt


def _tenant_cookie(tenant_id="tenant-1"):
    from app.core.config import settings

    token = jwt.encode(
        {"tenant_id": tenant_id}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return {"access_token": token}


def test_pull_requires_tenant(client):
    response = client.post("/api/v1/sync/listings/pull")
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
