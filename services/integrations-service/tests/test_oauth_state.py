"""OAuth state and public-authentication contract tests."""

from datetime import UTC, datetime, timedelta

import pytest
from app.services.oauth_state import (
    OAUTH_STATE_AUDIENCE,
    OAUTH_STATE_TYPE,
    OAuthStateError,
    consume_oauth_state,
    create_oauth_state,
)
from jose import jwt


def _access_cookie(tenant_id: str = "tenant-1", token_type: str = "access") -> dict[str, str]:
    from app.core.config import settings

    token = jwt.encode(
        {"tenant_id": tenant_id, "type": token_type},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"access_token": token}


def _signed_state(**overrides) -> str:
    from app.core.config import settings

    now = datetime.now(UTC)
    payload = {
        "tenant_id": "tenant-1",
        "nonce": "nonce-1",
        "aud": OAUTH_STATE_AUDIENCE,
        "type": OAUTH_STATE_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=600),
    }
    payload.update(overrides)
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture()
def state_store(monkeypatch):
    """In-memory replacement for the Redis-backed nonce store."""
    stored: dict[str, str] = {}

    async def fake_save(nonce: str, tenant_id: str, ttl_seconds: int) -> None:
        stored[nonce] = tenant_id

    async def fake_pop(nonce: str) -> str | None:
        return stored.pop(nonce, None)

    import app.services.oauth_state as oauth_state_module

    monkeypatch.setattr(oauth_state_module, "save_oauth_state", fake_save)
    monkeypatch.setattr(oauth_state_module, "pop_oauth_state", fake_pop)
    return stored


@pytest.mark.asyncio
async def test_state_round_trip_is_single_use(state_store):
    state, cookie_digest = await create_oauth_state("tenant-1")
    assert state_store  # nonce persisted

    assert await consume_oauth_state(state, cookie_digest) == "tenant-1"
    with pytest.raises(OAuthStateError):
        await consume_oauth_state(state, cookie_digest)


@pytest.mark.asyncio
async def test_raw_tenant_state_is_rejected(state_store):
    with pytest.raises(OAuthStateError):
        await consume_oauth_state("tenant-1", None)


@pytest.mark.asyncio
async def test_missing_cookie_digest_is_rejected(state_store):
    """Missing binding cookie must be rejected before touching Redis."""
    state, _cookie_digest = await create_oauth_state("tenant-1")
    assert state_store  # nonce persisted

    with pytest.raises(OAuthStateError, match="Missing OAuth session binding cookie"):
        await consume_oauth_state(state, None)
    # Nonce must still be intact (not consumed)
    assert await consume_oauth_state(state, _cookie_digest) == "tenant-1"


@pytest.mark.asyncio
async def test_mismatched_cookie_digest_is_rejected(state_store):
    """Mismatched binding cookie must be rejected and nonce left intact."""
    state, cookie_digest = await create_oauth_state("tenant-1")
    assert state_store  # nonce persisted

    with pytest.raises(OAuthStateError, match="OAuth session binding cookie mismatch"):
        await consume_oauth_state(state, "wrong-digest")
    # Nonce must still be intact (not consumed)
    assert await consume_oauth_state(state, cookie_digest) == "tenant-1"


@pytest.mark.asyncio
async def test_tampered_state_is_rejected(state_store):
    state = _signed_state()
    cookie_digest = "irrelevant"
    with pytest.raises(OAuthStateError):
        await consume_oauth_state(state + "x", cookie_digest)


@pytest.mark.asyncio
async def test_expired_state_is_rejected(state_store):
    state = _signed_state(exp=datetime.now(UTC) - timedelta(seconds=1))
    cookie_digest = "irrelevant"
    with pytest.raises(OAuthStateError):
        await consume_oauth_state(state, cookie_digest)


@pytest.mark.asyncio
async def test_wrong_audience_is_rejected(state_store):
    state = _signed_state(aud="other-audience")
    cookie_digest = "irrelevant"
    with pytest.raises(OAuthStateError):
        await consume_oauth_state(state, cookie_digest)


@pytest.mark.asyncio
async def test_wrong_type_is_rejected(state_store):
    state = _signed_state(type="access")
    state_store["nonce-1"] = "tenant-1"
    cookie_digest = "irrelevant"
    with pytest.raises(OAuthStateError):
        await consume_oauth_state(state, cookie_digest)


@pytest.mark.asyncio
async def test_tenant_mismatch_is_rejected(state_store):
    state = _signed_state()
    state_store["nonce-1"] = "tenant-2"
    cookie_digest = "irrelevant"
    with pytest.raises(OAuthStateError):
        await consume_oauth_state(state, cookie_digest)


def test_connect_requires_access_token(client):
    response = client.get("/api/v1/auth/mercadolivre/connect")
    assert response.status_code == 401

    response = client.get(
        "/api/v1/auth/mercadolivre/connect",
        headers={"X-Tenant-ID": "tenant-1"},
    )
    assert response.status_code == 401

    response = client.get(
        "/api/v1/auth/mercadolivre/connect",
        cookies=_access_cookie(token_type="refresh"),
    )
    assert response.status_code == 401


def test_connect_issues_signed_state(client, monkeypatch):
    import app.api.routes.auth as auth_module

    async def fake_create_state(tenant_id: str) -> tuple[str, str]:
        assert tenant_id == "tenant-1"
        return "signed-state-token", "cookie-digest-token"

    monkeypatch.setattr(auth_module, "create_oauth_state", fake_create_state)

    response = client.get(
        "/api/v1/auth/mercadolivre/connect",
        cookies=_access_cookie(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant-1"
    assert "state=signed-state-token" in body["auth_url"]

    # The binding cookie must be set with HttpOnly and path scoped to OAuth.
    cookies = response.headers.get_list("set-cookie")
    assert any("ml_oauth_nonce=cookie-digest-token" in c for c in cookies)
    assert any("HttpOnly" in c for c in cookies)
    assert any("Path=/api/v1/auth/mercadolivre" in c for c in cookies)


def test_connect_returns_503_when_redis_is_down(client, monkeypatch):
    import app.api.routes.auth as auth_module
    from redis.exceptions import RedisError

    async def failing_create_state(tenant_id: str) -> tuple[str, str]:
        raise RedisError("redis down")

    monkeypatch.setattr(auth_module, "create_oauth_state", failing_create_state)

    response = client.get(
        "/api/v1/auth/mercadolivre/connect",
        cookies=_access_cookie(),
    )
    assert response.status_code == 503


def test_callback_rejects_invalid_state(client):
    response = client.get(
        "/api/v1/auth/mercadolivre/callback",
        params={"code": "abc", "state": "tenant-1"},
    )
    assert response.status_code == 401


def test_callback_rejects_missing_binding_cookie(client):
    """Callback without the binding cookie must be rejected with 401.

    The cookie check happens before Redis access, so no Redis stubbing needed.
    """
    state = _signed_state()
    response = client.get(
        "/api/v1/auth/mercadolivre/callback",
        params={"code": "abc", "state": state},
    )
    assert response.status_code == 401


def test_callback_rejects_mismatched_binding_cookie(client):
    """Callback with a mismatched binding cookie must be rejected with 401.

    The cookie digest check happens before Redis access, so no Redis
    stubbing needed.
    """
    state = _signed_state()
    response = client.get(
        "/api/v1/auth/mercadolivre/callback",
        params={"code": "abc", "state": state},
        cookies={"ml_oauth_nonce": "wrong-digest"},
    )
    assert response.status_code == 401


def test_callback_returns_503_when_redis_is_down(client, monkeypatch):
    import app.api.routes.auth as auth_module
    from redis.exceptions import RedisError

    async def failing_consume_state(state: str, cookie_digest: str | None) -> str:
        raise RedisError("redis down")

    monkeypatch.setattr(auth_module, "consume_oauth_state", failing_consume_state)

    response = client.get(
        "/api/v1/auth/mercadolivre/callback",
        params={"code": "abc", "state": "state"},
        cookies={"ml_oauth_nonce": "some-digest"},
    )
    assert response.status_code == 503


def test_public_route_rejects_standalone_tenant_header(client):
    response = client.get(
        "/api/v1/integrations/mercadolivre/credentials",
        headers={"X-Tenant-ID": "tenant-1"},
    )
    assert response.status_code == 401


def test_public_route_rejects_legacy_cookie_and_refresh(client):
    response = client.get(
        "/api/v1/integrations/mercadolivre/credentials",
        cookies={"tenant_id": "tenant-1"},
    )
    assert response.status_code == 401

    response = client.get(
        "/api/v1/integrations/mercadolivre/credentials",
        cookies=_access_cookie(token_type="refresh"),
    )
    assert response.status_code == 401
