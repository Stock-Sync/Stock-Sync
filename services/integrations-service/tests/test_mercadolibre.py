"""Mercado Livre token refresh: distributed lock and concurrency tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import app.core.config as config_module
import app.core.redis as redis_module
import app.services.mercadolibre as mercadolibre_module
import httpx
import pytest
from app.core.errors import APIError
from app.core.redis import ML_REFRESH_LOCK_KEY_PREFIX, release_refresh_lock
from app.models.marketplace_credential import Marketplace, MarketplaceCredential
from app.services.mercadolibre import ML_TOKEN_URL, MercadoLivreService
from jose import jwt
from sqlalchemy import create_engine
from sqlmodel import Session, select

TENANT_ID = "tenant-1"
LOCK_KEY = f"{ML_REFRESH_LOCK_KEY_PREFIX}{TENANT_ID}"


class FakeRedis:
    """Minimal async Redis with the commands used by the refresh lock."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        px: int | None = None,
    ) -> bool | None:
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        # Equivalent to the Lua script in app.core.redis._RELEASE_LOCK_SCRIPT.
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeMLClient:
    """Stand-in for ``httpx.AsyncClient`` recording ML token requests."""

    def __init__(self, calls: list[dict], *, delay: float = 0.0, fail: bool = False) -> None:
        self.calls = calls
        self.delay = delay
        self.fail = fail

    async def __aenter__(self) -> "FakeMLClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, url: str, data: dict | None = None, headers: dict | None = None):
        assert url == ML_TOKEN_URL
        self.calls.append(dict(data or {}))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            request = httpx.Request("POST", url)
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError("token refresh failed", request=request, response=response)
        return FakeResponse(
            {
                "access_token": f"access-new-{len(self.calls)}",
                "refresh_token": "refresh-new",
                "expires_in": 21600,
            }
        )


class SessionSpy:
    """Session proxy that counts rollbacks without changing SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.rollbacks = 0

    def __getattr__(self, name: str):
        return getattr(self._session, name)

    def rollback(self):
        self.rollbacks += 1
        return self._session.rollback()


@pytest.fixture()
def engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/integrations.db",
        connect_args={"check_same_thread": False},
    )
    # Only this table is needed; MarketplaceItem uses PostgreSQL-only JSONB.
    MarketplaceCredential.__table__.create(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(redis_module, "_client", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def lock_settings(monkeypatch):
    monkeypatch.setattr(config_module.settings, "ml_refresh_lock_ttl_seconds", 15)
    monkeypatch.setattr(config_module.settings, "ml_refresh_lock_timeout_seconds", 2)
    monkeypatch.setattr(config_module.settings, "ml_refresh_buffer_seconds", 600)


def _install_ml_client(monkeypatch, *, delay: float = 0.0, fail: bool = False):
    calls: list[dict] = []
    client = FakeMLClient(calls, delay=delay, fail=fail)
    monkeypatch.setattr(mercadolibre_module.httpx, "AsyncClient", lambda *a, **k: client)
    return calls


def _seed_credential(engine, *, expires_in_seconds: int, access_token: str = "access-old"):
    with Session(engine) as session:
        credential = MarketplaceCredential(
            tenant_id=TENANT_ID,
            marketplace=Marketplace.mercadolivre,
            account_name="Test seller",
            access_token=access_token,
            refresh_token="refresh-old",
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
            is_active=True,
        )
        session.add(credential)
        session.commit()
        session.refresh(credential)
        session.expunge(credential)
        return credential.id


def _load_credential(engine) -> MarketplaceCredential:
    with Session(engine) as session:
        credential = session.exec(
            select(MarketplaceCredential).where(
                MarketplaceCredential.tenant_id == TENANT_ID
            )
        ).one()
        session.expunge(credential)
        return credential


@pytest.mark.asyncio
async def test_sequential_refresh_updates_credential(engine, fake_redis, monkeypatch):
    _seed_credential(engine, expires_in_seconds=-60)
    calls = _install_ml_client(monkeypatch)

    with Session(engine) as session:
        credential = await MercadoLivreService(session).get_valid_credential(TENANT_ID)

    assert credential is not None
    assert credential.access_token == "access-new-1"
    assert credential.refresh_token == "refresh-new"
    assert len(calls) == 1
    # Lock is always released after the refresh finishes.
    assert LOCK_KEY not in fake_redis.values

    persisted = _load_credential(engine)
    assert persisted.access_token == "access-new-1"
    assert persisted.refresh_token == "refresh-new"


@pytest.mark.asyncio
async def test_concurrent_refresh_only_calls_ml_once(engine, fake_redis, monkeypatch):
    _seed_credential(engine, expires_in_seconds=-60)
    calls = _install_ml_client(monkeypatch, delay=0.05)

    async def refresh_once() -> MarketplaceCredential | None:
        # Each concurrent worker uses its own SQLAlchemy session, mirroring
        # separate service processes.
        with Session(engine) as session:
            return await MercadoLivreService(session).get_valid_credential(TENANT_ID)

    first, second = await asyncio.gather(refresh_once(), refresh_once())

    assert len(calls) == 1, "refresh token must be rotated by a single worker"
    assert first is not None and second is not None
    assert first.access_token == "access-new-1"
    assert second.access_token == "access-new-1"
    assert LOCK_KEY not in fake_redis.values


@pytest.mark.asyncio
async def test_expired_lock_owner_cannot_release_new_owner(fake_redis):
    await fake_redis.set(LOCK_KEY, "new-owner", nx=True, px=15000)

    assert await release_refresh_lock(LOCK_KEY, "old-owner") is False
    assert await fake_redis.get(LOCK_KEY) == "new-owner"

    assert await release_refresh_lock(LOCK_KEY, "new-owner") is True
    assert await fake_redis.get(LOCK_KEY) is None


@pytest.mark.asyncio
async def test_api_failure_rolls_back_and_releases_lock(engine, fake_redis, monkeypatch):
    _seed_credential(engine, expires_in_seconds=-60)
    _install_ml_client(monkeypatch, fail=True)

    with Session(engine) as session:
        spy = SessionSpy(session)
        credential = await MercadoLivreService(spy).get_valid_credential(TENANT_ID)

    assert credential is None
    assert spy.rollbacks == 1
    assert LOCK_KEY not in fake_redis.values

    # The previous tokens remain persisted so the next call can retry.
    persisted = _load_credential(engine)
    assert persisted.access_token == "access-old"
    assert persisted.refresh_token == "refresh-old"


# =============================================================================
# Orchestrated listing creation (Plan 7)
# =============================================================================


class FakeListingSession:
    """Session spy for the orchestration unit tests (no real DB access)."""

    def __init__(self) -> None:
        self.rollbacks = 0
        self.commits = 0
        self.refreshed: list[object] = []

    def rollback(self) -> None:
        self.rollbacks += 1

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, item: object) -> None:
        self.refreshed.append(item)


def _item_stub(
    item_id: str = "MLB1",
    *,
    sku_id: int | None = 1,
    product_id: int | None = 2,
    description: str | None = "desc",
) -> SimpleNamespace:
    return SimpleNamespace(
        item_id=item_id,
        title="Produto teste",
        price=10.0,
        available_quantity=1,
        status="active",
        thumbnail=None,
        permalink=None,
        category_id="MLB-CAT",
        condition="new",
        listing_type_id="gold_special",
        family_name="Produto teste",
        sku_id=sku_id,
        product_id=product_id,
        description=description,
        attributes=[],
        updated_at=datetime.now(UTC),
    )


def _install_orchestration(
    monkeypatch,
    *,
    existing: SimpleNamespace | None = None,
    create_error: Exception | None = None,
    description_error: Exception | None = None,
    sync_error: Exception | None = None,
    mapping_error: Exception | None = None,
):
    calls: dict[str, list] = {
        "create": [],
        "description": [],
        "sync": [],
        "mapping": [],
        "compensate": [],
        "unbind": [],
    }
    session = FakeListingSession()
    mapping_result = {
        "id": 9,
        "sku_id": 1,
        "platform": "mercado_livre",
        "platform_product_id": "MLB1",
        "is_active": True,
    }

    async def fake_get_valid_credential(self, tenant_id: str):
        return SimpleNamespace(
            tenant_id=tenant_id, access_token="access-token", ml_user_id=321
        )

    async def fake_create_item_v3(self, tenant_id: str, item_data: dict):
        calls["create"].append((tenant_id, dict(item_data)))
        if create_error is not None:
            raise create_error
        return {
            "id": "MLB1",
            "title": item_data.get("title") or "Produto teste",
            "price": item_data.get("price", 10.0),
            "available_quantity": item_data.get("available_quantity", 1),
            "status": "active",
            "_sku_id": item_data.get("sku_id"),
            "_product_id": item_data.get("product_id"),
        }

    async def fake_create_description(
        self, access_token: str, item_id: str, description: str
    ):
        calls["description"].append((access_token, item_id, description))
        if description_error is not None:
            raise description_error
        return {"plain_text": description}

    def fake_sync(
        self, tenant_id, item_data, ml_user_id, *, commit: bool = True
    ):
        calls["sync"].append(
            {
                "tenant_id": tenant_id,
                "item_data": dict(item_data),
                "ml_user_id": ml_user_id,
                "commit": commit,
            }
        )
        if sync_error is not None:
            raise sync_error
        return _item_stub(
            item_data.get("id", "MLB1"),
            sku_id=item_data.get("_sku_id"),
            product_id=item_data.get("_product_id"),
            description=item_data.get("_description"),
        )

    async def fake_create_mapping(
        self, tenant_id, sku_id, platform_sku, platform_product_id
    ):
        calls["mapping"].append(
            (tenant_id, sku_id, platform_sku, platform_product_id)
        )
        if mapping_error is not None:
            raise mapping_error
        return mapping_result

    async def fake_fetch_mapping(self, tenant_id, platform_product_id):
        return mapping_result

    async def fake_compensate(self, tenant_id, item_id):
        calls["compensate"].append((tenant_id, item_id))

    async def fake_unbind(self, tenant_id, platform_product_id, reason="listing_deleted"):
        calls["unbind"].append((tenant_id, platform_product_id, reason))
        return {"unbound": 1}

    monkeypatch.setattr(
        MercadoLivreService, "get_valid_credential", fake_get_valid_credential
    )
    monkeypatch.setattr(MercadoLivreService, "create_item_v3", fake_create_item_v3)
    monkeypatch.setattr(
        MercadoLivreService, "create_item_description", fake_create_description
    )
    monkeypatch.setattr(MercadoLivreService, "sync_item_to_local", fake_sync)
    monkeypatch.setattr(
        MercadoLivreService, "_create_catalog_mapping", fake_create_mapping
    )
    monkeypatch.setattr(
        MercadoLivreService, "_fetch_catalog_mapping", fake_fetch_mapping
    )
    monkeypatch.setattr(
        MercadoLivreService, "_compensate_created_item", fake_compensate
    )
    monkeypatch.setattr(MercadoLivreService, "unbind_catalog_mapping", fake_unbind)
    monkeypatch.setattr(
        MercadoLivreService,
        "find_existing_listing",
        lambda self, tenant_id, sku_id: existing,
    )
    return MercadoLivreService(session), session, calls


def _listing_payload(**overrides) -> dict:
    payload = {
        "title": "Produto teste",
        "family_name": "Produto teste",
        "category_id": "MLB-CAT",
        "listing_type_id": "gold_special",
        "condition": "new",
        "currency_id": "BRL",
        "buying_mode": "buy_it_now",
        "price": 10.0,
        "available_quantity": 1,
        "pictures": [
            {
                "source": (
                    "https://res.cloudinary.com/demo/image/upload/v1/listing.jpg"
                )
            }
        ],
        "attributes": [],
        "description": "Descrição do anúncio",
        "sku_id": 1,
        "product_id": 2,
        "platform_sku": "SKU-1",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_orchestrated_listing_creates_item_description_and_mapping(monkeypatch):
    service, session, calls = _install_orchestration(monkeypatch)

    item, mapping, existing = await service.create_orchestrated_listing(
        TENANT_ID, _listing_payload()
    )

    assert existing is False
    assert item["id"] == "MLB1"
    assert item["description"] == "Descrição do anúncio"
    assert mapping["platform_product_id"] == "MLB1"
    assert len(calls["create"]) == 1
    # Description is sent by the saga (step 3), never inside POST /items.
    assert "description" not in calls["create"][0][1]
    assert "platform_sku" not in calls["create"][0][1]
    assert calls["description"] == [
        ("access-token", "MLB1", "Descrição do anúncio")
    ]
    assert calls["sync"][0]["commit"] is False
    assert calls["mapping"] == [(TENANT_ID, 1, "SKU-1", "MLB1")]
    assert calls["compensate"] == []
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_orchestrated_listing_is_idempotent_per_sku(monkeypatch):
    existing_item = _item_stub("MLB-EXISTING")
    service, session, calls = _install_orchestration(
        monkeypatch, existing=existing_item
    )

    item, mapping, existing = await service.create_orchestrated_listing(
        TENANT_ID, _listing_payload()
    )

    assert existing is True
    assert item["id"] == "MLB-EXISTING"
    assert mapping is not None
    assert calls["create"] == []
    assert calls["description"] == []
    assert calls["mapping"] == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_orchestrated_listing_rejects_variations(monkeypatch):
    service, session, calls = _install_orchestration(monkeypatch)

    with pytest.raises(APIError) as exc:
        await service.create_orchestrated_listing(
            TENANT_ID, _listing_payload(variations=[{"id": "variation-1"}])
        )

    assert exc.value.status_code == 422
    assert exc.value.code == "variations_not_supported"
    assert calls["create"] == []
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_orchestrated_listing_rejects_non_cloudinary_pictures(monkeypatch):
    service, _session, calls = _install_orchestration(monkeypatch)

    with pytest.raises(APIError) as exc:
        await service.create_orchestrated_listing(
            TENANT_ID,
            _listing_payload(pictures=[{"source": "https://mlstatic.com/a.jpg"}]),
        )

    assert exc.value.status_code == 422
    assert exc.value.code == "invalid_picture_source"
    assert calls["create"] == []


@pytest.mark.asyncio
async def test_orchestrated_listing_preserves_ml_creation_error(monkeypatch):
    error = APIError(
        status_code=422,
        code="item_creation_failed",
        message="Mercado Livre rejected the item",
    )
    service, session, calls = _install_orchestration(
        monkeypatch, create_error=error
    )

    with pytest.raises(APIError) as exc:
        await service.create_orchestrated_listing(TENANT_ID, _listing_payload())

    # Nothing was created remotely, so there is nothing to compensate.
    assert exc.value is error
    assert calls["compensate"] == []
    assert session.commits == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_step"),
    [
        ("description", "description"),
        ("local", "local_persistence"),
        ("mapping", "catalog_mapping"),
    ],
)
async def test_orchestrated_listing_compensates_and_rolls_back(
    monkeypatch, failure, expected_step
):
    failure_kwargs = {
        "description": {
            "description_error": APIError(
                status_code=422,
                code="item_description_failed",
                message="description failed",
            )
        },
        "local": {"sync_error": RuntimeError("database unavailable")},
        "mapping": {
            "mapping_error": APIError(
                status_code=502,
                code="catalog_mapping_failed",
                message="catalog unavailable",
            )
        },
    }[failure]

    service, session, calls = _install_orchestration(
        monkeypatch, **failure_kwargs
    )

    with pytest.raises(APIError) as exc:
        await service.create_orchestrated_listing(TENANT_ID, _listing_payload())

    assert exc.value.status_code == 500
    assert exc.value.code == "listing_creation_failed"
    assert exc.value.details["step"] == expected_step
    assert exc.value.details["item_id"] == "MLB1"
    # Remote item must be deleted/paused, local transaction rolled back and
    # the catalog mapping skipped (mapping step may have been attempted).
    assert calls["compensate"] == [(TENANT_ID, "MLB1")]
    assert session.rollbacks == 1
    assert session.commits == 0
    assert calls["unbind"] == []
    if failure in {"description", "local"}:
        assert calls["mapping"] == []


@pytest.mark.asyncio
async def test_update_item_rejects_variations():
    service = MercadoLivreService(FakeListingSession())

    with pytest.raises(APIError) as exc:
        await service.update_item(
            TENANT_ID, "MLB1", {"variations": [{"id": "variation-1"}]}
        )

    assert exc.value.status_code == 422
    assert exc.value.code == "variations_not_supported"


class _FakeHTTPResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("DELETE", "https://api.mercadolibre.com/items/MLB1")
            raise httpx.HTTPStatusError(
                "request failed",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )

    def json(self) -> dict:
        return {"id": "MLB1", "status": "closed"}


class _FakeDeleteClient:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def delete(self, *args, **kwargs):
        return _FakeHTTPResponse(self.status_code)


class _FakeCompensationClient:
    def __init__(self, delete_status: int, put_status: int = 200) -> None:
        self.delete_status = delete_status
        self.put_status = put_status
        self.calls: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def delete(self, *args, **kwargs):
        self.calls.append(("delete", args[0] if args else kwargs.get("url")))
        return _FakeHTTPResponse(self.delete_status)

    async def put(self, url, json=None, headers=None):
        self.calls.append(("put", json))
        return _FakeHTTPResponse(self.put_status)


@pytest.mark.asyncio
async def test_delete_item_treats_ml_404_as_already_deleted(monkeypatch):
    async def fake_get_valid_credential(self, tenant_id: str):
        return SimpleNamespace(
            tenant_id=tenant_id, access_token="access-token", ml_user_id=321
        )

    monkeypatch.setattr(
        MercadoLivreService, "get_valid_credential", fake_get_valid_credential
    )
    monkeypatch.setattr(
        mercadolibre_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeDeleteClient(404),
    )

    result = await MercadoLivreService(FakeListingSession()).delete_item(
        TENANT_ID, "MLB1"
    )

    assert result["already_deleted"] is True
    assert result["id"] == "MLB1"


@pytest.mark.asyncio
async def test_compensation_pauses_listing_when_delete_fails(monkeypatch):
    async def fake_get_valid_credential(self, tenant_id: str):
        return SimpleNamespace(
            tenant_id=tenant_id, access_token="access-token", ml_user_id=321
        )

    client = _FakeCompensationClient(delete_status=500, put_status=200)
    monkeypatch.setattr(
        MercadoLivreService, "get_valid_credential", fake_get_valid_credential
    )
    monkeypatch.setattr(
        mercadolibre_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: client,
    )

    await MercadoLivreService(FakeListingSession())._compensate_created_item(
        TENANT_ID, "MLB1"
    )

    assert [call[0] for call in client.calls] == ["delete", "put"]
    assert client.calls[1][1] == {"status": "paused"}


# =============================================================================
# Public listing route (Plan 7)
# =============================================================================


def _auth_headers(tenant_id: str = "tenant-1") -> dict[str, str]:
    token = jwt.encode(
        {"tenant_id": tenant_id, "type": "access"},
        config_module.settings.jwt_secret_key,
        algorithm=config_module.settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def test_create_listing_route_rejects_variations(client):
    response = client.post(
        "/api/v1/integrations/mercadolivre/listings",
        json=_listing_payload(variations=[{"id": "variation-1"}]),
        headers=_auth_headers(),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "variations_not_supported"


def test_legacy_post_items_route_is_gone(client):
    response = client.post(
        "/api/v1/integrations/mercadolivre/items",
        json=_listing_payload(),
        headers=_auth_headers(),
    )

    assert response.status_code == 405


def test_create_listing_route_returns_201_and_200_on_replay(client, monkeypatch):
    import app.api.routes.products as products_module

    state = {"existing": False}

    async def fake_create_orchestrated(self, tenant_id, item_data):
        assert tenant_id == "tenant-1"
        assert item_data["sku_id"] == 1
        return (
            {"id": "MLB1", "title": "Produto teste"},
            {"id": 9, "platform_product_id": "MLB1"},
            state["existing"],
        )

    monkeypatch.setattr(
        products_module.MercadoLivreService,
        "create_orchestrated_listing",
        fake_create_orchestrated,
    )

    created = client.post(
        "/api/v1/integrations/mercadolivre/listings",
        json=_listing_payload(),
        headers=_auth_headers(),
    )
    assert created.status_code == 201
    assert created.json()["item"]["id"] == "MLB1"
    assert created.json()["existing"] is False

    state["existing"] = True
    replay = client.post(
        "/api/v1/integrations/mercadolivre/listings",
        json=_listing_payload(),
        headers=_auth_headers(),
    )
    assert replay.status_code == 200
    assert replay.json()["existing"] is True


class _DeleteRouteSession:
    """Minimal session used by the DELETE route test."""

    def __init__(self, item: SimpleNamespace | None) -> None:
        self.item = item
        self.added: list[object] = []
        self.commits = 0

    def exec(self, statement):
        return SimpleNamespace(first=lambda: self.item)

    def add(self, obj) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commits += 1


def _override_delete_session(app, session):
    from app.db.session import get_session

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session


def test_delete_route_soft_deletes_local_item_and_unbinds(client, monkeypatch):
    import app.api.routes.products as products_module
    from app.main import app

    calls: dict[str, tuple] = {}
    item = SimpleNamespace(is_deleted=False, updated_at=None)

    async def fake_delete_item(self, tenant_id, item_id):
        calls["delete"] = (tenant_id, item_id)

    async def fake_unbind(self, tenant_id, item_id, reason="listing_deleted"):
        calls["unbind"] = (tenant_id, item_id, reason)

    monkeypatch.setattr(
        products_module.MercadoLivreService, "delete_item", fake_delete_item
    )
    monkeypatch.setattr(
        products_module.MercadoLivreService, "unbind_catalog_mapping", fake_unbind
    )
    session = _DeleteRouteSession(item)
    _override_delete_session(app, session)

    response = client.delete(
        "/api/v1/integrations/mercadolivre/items/MLB1",
        headers=_auth_headers("tenant-1"),
    )

    assert response.status_code == 200
    assert calls["delete"] == ("tenant-1", "MLB1")
    assert calls["unbind"] == ("tenant-1", "MLB1", "listing_deleted")
    assert item.is_deleted is True
    assert item.updated_at is not None
    assert session.commits == 1


def test_delete_route_keeps_local_item_when_ml_fails(client, monkeypatch):
    import app.api.routes.products as products_module
    from app.main import app

    calls: dict[str, tuple] = {}
    item = SimpleNamespace(is_deleted=False, updated_at=None)

    async def fake_delete_item(self, tenant_id, item_id):
        raise RuntimeError("ML unavailable")

    async def fake_unbind(self, tenant_id, item_id, reason="listing_deleted"):
        calls["unbind"] = (tenant_id, item_id, reason)

    monkeypatch.setattr(
        products_module.MercadoLivreService, "delete_item", fake_delete_item
    )
    monkeypatch.setattr(
        products_module.MercadoLivreService, "unbind_catalog_mapping", fake_unbind
    )
    session = _DeleteRouteSession(item)
    _override_delete_session(app, session)

    response = client.delete(
        "/api/v1/integrations/mercadolivre/items/MLB1",
        headers=_auth_headers("tenant-1"),
    )

    assert response.status_code == 500
    assert calls == {}
    assert item.is_deleted is False
    assert session.commits == 0


# =============================================================================
# Scroll search and variation filtering (Plan 8)
# =============================================================================


class FakeSearchResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.mercadolibre.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "search failed", request=request, response=response
            )

    def json(self) -> dict:
        return self._payload


class FakeSearchClient:
    def __init__(self, pages: list[FakeSearchResponse]) -> None:
        self.pages = pages
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": headers})
        return self.pages.pop(0)


def _install_search_client(monkeypatch, pages: list[FakeSearchResponse]):
    fake = FakeSearchClient(pages)
    monkeypatch.setattr(
        mercadolibre_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: fake,
    )

    async def fake_credential(self, tenant_id: str):
        return SimpleNamespace(
            tenant_id=tenant_id, access_token="access-token", ml_user_id=321
        )

    monkeypatch.setattr(
        MercadoLivreService, "get_valid_credential", fake_credential
    )
    return fake


@pytest.mark.asyncio
async def test_search_all_items_uses_scroll_pagination(monkeypatch):
    fake = _install_search_client(
        monkeypatch,
        [
            FakeSearchResponse(
                {
                    "results": ["MLB1", "MLB2"],
                    "paging": {"total": 5},
                    "scroll_id": "scroll-1",
                }
            ),
            FakeSearchResponse(
                {
                    "results": ["MLB3", "MLB4"],
                    "paging": {"total": 5},
                    "scroll_id": "scroll-2",
                }
            ),
            FakeSearchResponse(
                {
                    "results": ["MLB5"],
                    "paging": {"total": 5},
                    "scroll_id": "scroll-3",
                }
            ),
        ],
    )

    result = await MercadoLivreService(
        SimpleNamespace()
    ).search_all_items_with_metadata(TENANT_ID, page_size=2)

    assert result == {
        "item_ids": ["MLB1", "MLB2", "MLB3", "MLB4", "MLB5"],
        "reported_total": 5,
        "truncated": False,
    }
    assert all(call["params"]["search_type"] == "scan" for call in fake.calls)
    # The scroll id is only sent after the first page.
    assert "scroll_id" not in fake.calls[0]["params"]
    assert fake.calls[1]["params"]["scroll_id"] == "scroll-1"
    assert fake.calls[2]["params"]["scroll_id"] == "scroll-2"


@pytest.mark.asyncio
async def test_search_all_items_detects_truncated_pagination(monkeypatch):
    _install_search_client(
        monkeypatch,
        [
            FakeSearchResponse(
                {
                    "results": ["MLB1", "MLB2"],
                    "paging": {"total": 5},
                    "scroll_id": "scroll-1",
                }
            ),
            # The scroll ends early: only 2 of the 5 reported items were seen.
            FakeSearchResponse(
                {"results": [], "paging": {"total": 5}, "scroll_id": None}
            ),
        ],
    )

    result = await MercadoLivreService(
        SimpleNamespace()
    ).search_all_items_with_metadata(TENANT_ID, page_size=2)

    assert result["item_ids"] == ["MLB1", "MLB2"]
    assert result["reported_total"] == 5
    assert result["truncated"] is True


def test_item_has_variations_flags_children_and_variations():
    from app.services.mercadolibre import item_has_variations

    assert item_has_variations({"id": "MLB1"}) is False
    assert item_has_variations({"id": "MLB1", "children": []}) is False
    assert item_has_variations({"id": "MLB1", "children": [{"id": "c1"}]}) is True
    assert item_has_variations(
        {"id": "MLB1", "variations": [{"id": "v1"}]}
    ) is True


# =============================================================================
# Plan 9 — orchestrated unbind (pause + zero)
# =============================================================================


class _FakeUnlinkResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.mercadolibre.com/items/MLB1")
            raise httpx.HTTPStatusError(
                "request failed",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )

    def json(self) -> dict:
        return self._payload


class _FakeUnlinkClient:
    def __init__(
        self,
        *,
        get_status: int = 200,
        item: dict | None = None,
        put_status: int = 200,
    ) -> None:
        self.get_status = get_status
        self.item = item or {"id": "MLB1", "status": "active"}
        self.put_status = put_status
        self.calls: list[tuple[str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, headers=None):
        self.calls.append(("get", None))
        return _FakeUnlinkResponse(self.get_status, self.item)

    async def put(self, url, json=None, headers=None):
        self.calls.append(("put", json))
        return _FakeUnlinkResponse(self.put_status, {"id": "MLB1", **(json or {})})


def _patch_unlink_http(monkeypatch, client) -> None:
    async def fake_get_valid_credential(self, tenant_id: str):
        return SimpleNamespace(
            tenant_id=tenant_id, access_token="access-token", ml_user_id=321
        )

    monkeypatch.setattr(
        MercadoLivreService, "get_valid_credential", fake_get_valid_credential
    )
    monkeypatch.setattr(
        mercadolibre_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: client,
    )


@pytest.mark.asyncio
async def test_prepare_unlink_pauses_and_zeroes_active_item(monkeypatch):
    client = _FakeUnlinkClient(item={"id": "MLB1", "status": "active"})
    _patch_unlink_http(monkeypatch, client)

    result = await MercadoLivreService(FakeListingSession()).prepare_item_unlink(
        TENANT_ID, "MLB1"
    )

    assert result["remote_action"] == "paused_and_zeroed"
    assert client.calls == [("get", None), ("put", {"available_quantity": 0, "status": "paused"})]


@pytest.mark.asyncio
async def test_prepare_unlink_only_zeroes_paused_item(monkeypatch):
    client = _FakeUnlinkClient(item={"id": "MLB1", "status": "paused"})
    _patch_unlink_http(monkeypatch, client)

    result = await MercadoLivreService(FakeListingSession()).prepare_item_unlink(
        TENANT_ID, "MLB1"
    )

    assert result["remote_action"] == "zeroed"
    assert client.calls == [("get", None), ("put", {"available_quantity": 0})]


@pytest.mark.asyncio
async def test_prepare_unlink_skips_closed_item(monkeypatch):
    client = _FakeUnlinkClient(item={"id": "MLB1", "status": "closed"})
    _patch_unlink_http(monkeypatch, client)

    result = await MercadoLivreService(FakeListingSession()).prepare_item_unlink(
        TENANT_ID, "MLB1"
    )

    assert result["remote_action"] == "skipped"
    assert result["reason"] == "already_closed"
    assert [call[0] for call in client.calls] == ["get"]


@pytest.mark.asyncio
async def test_prepare_unlink_treats_404_as_deleted(monkeypatch):
    client = _FakeUnlinkClient(get_status=404)
    _patch_unlink_http(monkeypatch, client)

    result = await MercadoLivreService(FakeListingSession()).prepare_item_unlink(
        TENANT_ID, "MLB1"
    )

    assert result["remote_action"] == "skipped"
    assert result["reason"] == "not_found"


@pytest.mark.asyncio
async def test_prepare_unlink_aborts_on_remote_failure(monkeypatch):
    client = _FakeUnlinkClient(put_status=500)
    _patch_unlink_http(monkeypatch, client)

    with pytest.raises(APIError) as exc:
        await MercadoLivreService(FakeListingSession()).prepare_item_unlink(
            TENANT_ID, "MLB1"
        )

    assert exc.value.status_code == 503
    assert exc.value.code == "remote_unlink_failed"
