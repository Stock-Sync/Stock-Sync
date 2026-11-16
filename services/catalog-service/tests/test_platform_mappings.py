def _make_sku(client, internal_sku="SKU-1"):
    product = client.post("/api/v1/products", json={"name": "Produto"}).json()
    return client.post(
        "/api/v1/skus",
        json={"product_id": product["id"], "internal_sku": internal_sku},
    ).json()


def _make_mapping(client, sku_id, platform="mercado_livre", platform_sku="ML-1", **extra):
    payload = {"sku_id": sku_id, "platform": platform, "platform_sku": platform_sku, **extra}
    return client.post("/api/v1/platform-mappings", json=payload)


def test_create_platform_mapping(client):
    sku = _make_sku(client)
    response = _make_mapping(client, sku["id"])
    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "mercado_livre"
    assert body["platform_sku"] == "ML-1"


def test_create_platform_mapping_sku_not_found(client):
    response = _make_mapping(client, 999, platform="shopee", platform_sku="SH-1")
    assert response.status_code == 404


def test_create_platform_mapping_deleted_sku_not_found(client):
    sku = _make_sku(client)
    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204

    response = _make_mapping(client, sku["id"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_create_platform_mapping_invalid_platform(client):
    sku = _make_sku(client)
    response = _make_mapping(client, sku["id"], platform="amazon", platform_sku="AM-1")
    assert response.status_code == 422


def test_list_platform_mappings_empty(client):
    response = client.get("/api/v1/platform-mappings")
    assert response.status_code == 200
    assert response.json() == []


def test_filter_by_platform(client):
    sku = _make_sku(client)
    _make_mapping(client, sku["id"], platform="mercado_livre", platform_sku="ML-1")
    _make_mapping(client, sku["id"], platform="shopee", platform_sku="SH-1")

    response = client.get("/api/v1/platform-mappings", params={"platform": "mercado_livre"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["platform_sku"] == "ML-1"


def test_filter_by_platform_product_id(client):
    sku = _make_sku(client)
    _make_mapping(
        client, sku["id"], platform_sku="MLB123", platform_product_id="MLB123"
    )
    _make_mapping(client, sku["id"], platform_sku="MLB456", platform_product_id="MLB456")

    response = client.get(
        "/api/v1/platform-mappings", params={"platform_product_id": "MLB123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["platform_product_id"] == "MLB123"


def test_filter_by_platform_sku(client):
    sku = _make_sku(client)
    _make_mapping(client, sku["id"], platform_sku="SKU-A")
    _make_mapping(client, sku["id"], platform_sku="SKU-B")

    response = client.get("/api/v1/platform-mappings", params={"platform_sku": "SKU-B"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["platform_sku"] == "SKU-B"


def test_delete_mapping_soft_deletes_and_hides_from_ui(client):
    sku = _make_sku(client)
    mapping = _make_mapping(
        client, sku["id"], platform_product_id="MLB123"
    ).json()

    assert client.delete(f"/api/v1/platform-mappings/{mapping['id']}").status_code == 204

    # Hidden from the default (UI) listing...
    assert client.get("/api/v1/platform-mappings").json() == []
    assert (
        client.get(f"/api/v1/platform-mappings/{mapping['id']}").status_code
        == 404
    )

    # ...but preserved for history/order processing.
    history = client.get(
        "/api/v1/platform-mappings",
        params={"platform_product_id": "MLB123", "include_deleted": "true"},
    ).json()
    assert len(history) == 1
    assert history[0]["id"] == mapping["id"]
    assert history[0]["is_deleted"] is True

    # Deleting twice is idempotent.
    assert client.delete(f"/api/v1/platform-mappings/{mapping['id']}").status_code == 204


def test_bulk_soft_delete_hides_only_listed_mappings(client):
    sku = _make_sku(client)
    gone = _make_mapping(
        client, sku["id"], platform_product_id="MLB-GONE", platform_sku="GONE"
    ).json()
    kept = _make_mapping(
        client, sku["id"], platform_product_id="MLB-KEEP", platform_sku="KEEP"
    ).json()

    response = client.post(
        "/api/v1/platform-mappings/soft-delete",
        json={
            "platform": "mercado_livre",
            "platform_product_ids": ["MLB-GONE"],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"deleted": 1}

    visible = client.get("/api/v1/platform-mappings").json()
    assert [item["id"] for item in visible] == [kept["id"]]

    history = client.get(
        "/api/v1/platform-mappings", params={"include_deleted": "true"}
    ).json()
    assert {item["id"] for item in history} == {gone["id"], kept["id"]}


# =============================================================================
# Internal upsert/unbind (Plan 7)
# =============================================================================

INTERNAL_PATH = "/api/v1/internal/platform-mappings"


def _internal_headers(tenant_id="test-tenant", secret=None):
    from app.core.config import settings

    return {
        "X-Internal-Secret": secret or settings.internal_service_secret,
        "X-Tenant-ID": tenant_id,
    }


def _internal_create(client, sku_id, **overrides):
    payload = {
        "sku_id": sku_id,
        "platform": "mercado_livre",
        "platform_sku": "SKU-1",
        "platform_product_id": "MLB123",
        "is_active": True,
        **overrides,
    }
    return client.post(
        INTERNAL_PATH, json=payload, headers=_internal_headers()
    )


def test_internal_upsert_requires_secret(client):
    sku = _make_sku(client)
    payload = {
        "sku_id": sku["id"],
        "platform": "mercado_livre",
        "platform_sku": "SKU-1",
        "platform_product_id": "MLB123",
    }
    assert client.post(INTERNAL_PATH, json=payload).status_code == 401
    assert (
        client.post(
            INTERNAL_PATH,
            json=payload,
            headers=_internal_headers(secret="wrong"),
        ).status_code
        == 401
    )


def test_internal_upsert_creates_mapping(client):
    sku = _make_sku(client)

    response = _internal_create(client, sku["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["sku_id"] == sku["id"]
    assert body["platform"] == "mercado_livre"
    assert body["platform_product_id"] == "MLB123"
    assert body["is_deleted"] is False
    assert body["is_active"] is True

    visible = client.get("/api/v1/platform-mappings").json()
    assert [mapping["id"] for mapping in visible] == [body["id"]]


def test_internal_upsert_is_idempotent(client):
    sku = _make_sku(client)

    first = _internal_create(client, sku["id"]).json()
    second = _internal_create(client, sku["id"], platform_sku="SKU-RENAMED").json()

    assert second["id"] == first["id"]
    assert second["platform_sku"] == "SKU-RENAMED"
    assert len(client.get("/api/v1/platform-mappings").json()) == 1


def test_internal_upsert_reactivates_soft_deleted_mapping(client):
    sku = _make_sku(client)
    created = _internal_create(client, sku["id"]).json()

    assert (
        client.post(
            f"{INTERNAL_PATH}/unbind",
            json={
                "platform_product_id": "MLB123",
                "reason": "listing_deleted",
            },
            headers=_internal_headers(),
        ).status_code
        == 200
    )
    assert client.get("/api/v1/platform-mappings").json() == []

    reactivated = _internal_create(client, sku["id"]).json()

    assert reactivated["id"] == created["id"]
    assert reactivated["is_deleted"] is False
    assert reactivated["is_active"] is True
    assert reactivated["deleted_reason"] is None
    assert len(client.get("/api/v1/platform-mappings").json()) == 1


def test_internal_upsert_rejects_deleted_sku(client):
    sku = _make_sku(client)
    assert client.delete(f"/api/v1/skus/{sku['id']}").status_code == 204

    response = _internal_create(client, sku["id"])

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_reactivated_mapping_publishes_current_stock_once(client, stock_events):
    sku = _make_sku(client)
    assert (
        client.put(
            f"/api/v1/skus/{sku['id']}", json={"stock_quantity": 9}
        ).status_code
        == 200
    )
    _internal_create(
        client, sku["id"], platform_product_id="MLB-REACT"
    )
    assert (
        client.post(
            f"{INTERNAL_PATH}/unbind",
            json={
                "platform_product_id": "MLB-REACT",
                "reason": "listing_deleted",
            },
            headers=_internal_headers(),
        ).status_code
        == 200
    )
    stock_events.clear()

    reactivated = _internal_create(
        client, sku["id"], platform_product_id="MLB-REACT"
    )

    assert reactivated.status_code == 200
    assert stock_events == [
        {
            "sku_id": sku["id"],
            "internal_sku": "SKU-1",
            "previous_quantity": 9,
            "new_quantity": 9,
            "source": "listing_reactivated",
            "tenant_id": "test-tenant",
        }
    ]


def test_manual_relink_reactivation_publishes_current_stock(client, stock_events):
    sku = _make_sku(client)
    mapping = _make_mapping(
        client, sku["id"], platform_product_id="MLB-RELINK"
    ).json()
    assert (
        client.delete(f"/api/v1/platform-mappings/{mapping['id']}").status_code
        == 204
    )
    stock_events.clear()

    response = client.post(
        "/api/v1/platform-mappings/re-link",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "ML-1",
            "platform_product_id": "MLB-RELINK",
        },
    )

    assert response.status_code == 200
    assert stock_events == [
        {
            "sku_id": sku["id"],
            "internal_sku": "SKU-1",
            "previous_quantity": 0,
            "new_quantity": 0,
            "source": "listing_reactivated",
            "tenant_id": "test-tenant",
        }
    ]


def test_mapping_state_transition_to_active_publishes_stock(client, stock_events):
    sku = _make_sku(client)
    _internal_create(client, sku["id"], platform_product_id="MLB-STATE")
    # Pause first so the next event is a real false -> true transition.
    assert (
        client.post(
            f"{INTERNAL_PATH}/state",
            json={
                "platform": "mercado_livre",
                "platform_product_id": "MLB-STATE",
                "is_active": False,
            },
            headers=_internal_headers(),
        ).status_code
        == 200
    )
    stock_events.clear()

    response = client.post(
        f"{INTERNAL_PATH}/state",
        json={
            "platform": "mercado_livre",
            "platform_product_id": "MLB-STATE",
            "is_active": True,
        },
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    assert stock_events == [
        {
            "sku_id": sku["id"],
            "internal_sku": "SKU-1",
            "previous_quantity": 0,
            "new_quantity": 0,
            "source": "listing_reactivated",
            "tenant_id": "test-tenant",
        }
    ]


def test_internal_unbind_soft_deletes_with_reason(client):
    sku = _make_sku(client)
    mapping = _internal_create(client, sku["id"]).json()

    response = client.post(
        f"{INTERNAL_PATH}/unbind",
        json={
            "platform_product_id": "MLB123",
            "reason": "listing_deleted",
        },
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"unbound": 1}

    history = client.get(
        "/api/v1/platform-mappings", params={"include_deleted": "true"}
    ).json()
    stored = next(item for item in history if item["id"] == mapping["id"])
    assert stored["is_deleted"] is True
    assert stored["is_active"] is False
    assert stored["deleted_reason"] == "listing_deleted"

    # Idempotent on retry.
    assert (
        client.post(
            f"{INTERNAL_PATH}/unbind",
            json={"platform_product_id": "MLB123"},
            headers=_internal_headers(),
        ).json()
        == {"unbound": 0}
    )


def test_internal_unbind_requires_secret(client):
    response = client.post(
        f"{INTERNAL_PATH}/unbind",
        json={"platform_product_id": "MLB123"},
    )
    assert response.status_code == 401


def test_internal_unbind_batch_is_idempotent(client):
    sku = _make_sku(client)
    first = _internal_create(
        client, sku["id"], platform_product_id="MLB-A", platform_sku="A"
    ).json()
    second = _internal_create(
        client, sku["id"], platform_product_id="MLB-B", platform_sku="B"
    ).json()

    response = client.post(
        f"{INTERNAL_PATH}/unbind",
        json={
            "platform_product_ids": ["MLB-A", "MLB-B"],
            "reason": "reconciliation_missing",
        },
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"unbound": 2}

    history = client.get(
        "/api/v1/platform-mappings", params={"include_deleted": "true"}
    ).json()
    by_id = {item["id"]: item for item in history}
    assert by_id[first["id"]]["deleted_reason"] == "reconciliation_missing"
    assert by_id[second["id"]]["deleted_reason"] == "reconciliation_missing"

    # A retry (e.g. after a local soft-delete failure) is a no-op.
    retry = client.post(
        f"{INTERNAL_PATH}/unbind",
        json={
            "platform_product_ids": ["MLB-A", "MLB-B"],
            "reason": "reconciliation_missing",
        },
        headers=_internal_headers(),
    )
    assert retry.status_code == 200
    assert retry.json() == {"unbound": 0}


def test_internal_unbind_batch_ignores_other_tenants(client):
    sku = _make_sku(client)
    _internal_create(client, sku["id"], platform_product_id="MLB-A")

    response = client.post(
        f"{INTERNAL_PATH}/unbind",
        json={"platform_product_ids": ["MLB-A"], "reason": "reconciliation_missing"},
        headers=_internal_headers(tenant_id="other-tenant"),
    )

    assert response.status_code == 200
    assert response.json() == {"unbound": 0}
    assert len(client.get("/api/v1/platform-mappings").json()) == 1


# =============================================================================
# Plan 9 — partial uniqueness, deleted_reason matrix, orchestrated unbind,
# re-link and lifecycle state sync
# =============================================================================


def _mapping_row(**overrides):
    from app.models import Platform, PlatformMapping

    payload = {
        "tenant_id": "test-tenant",
        "sku_id": 1,
        "platform": Platform.mercadolivre,
        "platform_sku": "SKU-1",
        "platform_product_id": "MLB-1",
        "is_active": True,
    }
    payload.update(overrides)
    return PlatformMapping(**payload)


def test_partial_unique_index_blocks_two_active_mappings_for_listing(db_engine):
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session

    with Session(db_engine) as session:
        session.add(_mapping_row(platform_sku="A"))
        session.commit()

        session.add(_mapping_row(platform_sku="B"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:  # pragma: no cover - the index must reject this
            raise AssertionError("duplicate active mapping was accepted")


def test_partial_unique_index_blocks_two_active_mappings_for_sku(db_engine):
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session

    with Session(db_engine) as session:
        session.add(_mapping_row(platform_product_id="MLB-1"))
        session.commit()

        session.add(_mapping_row(platform_product_id="MLB-2"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:  # pragma: no cover - the index must reject this
            raise AssertionError("duplicate active SKU mapping was accepted")


def test_partial_unique_index_ignores_soft_deleted_rows(db_engine):
    from app.models import PlatformMapping
    from sqlmodel import Session, select

    with Session(db_engine) as session:
        session.add(_mapping_row(is_deleted=True, is_active=False))
        session.add(_mapping_row())
        session.commit()

        rows = session.exec(select(PlatformMapping)).all()
        assert len(rows) == 2


def test_internal_upsert_does_not_resurrect_user_deleted_mapping(client):
    sku = _make_sku(client)
    mapping = _internal_create(client, sku["id"]).json()

    assert client.delete(f"/api/v1/platform-mappings/{mapping['id']}").status_code == 204

    retry = _internal_create(client, sku["id"])
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "mapping_user_deleted"

    history = client.get(
        "/api/v1/platform-mappings", params={"include_deleted": "true"}
    ).json()
    stored = next(item for item in history if item["id"] == mapping["id"])
    assert stored["is_deleted"] is True
    assert stored["deleted_reason"] == "user"


def test_internal_upsert_reactivates_reconciled_mapping(client):
    sku = _make_sku(client)
    mapping = _internal_create(client, sku["id"]).json()

    client.post(
        f"{INTERNAL_PATH}/unbind",
        json={"platform_product_id": "MLB123", "reason": "reconcile"},
        headers=_internal_headers(),
    )

    reactivated = _internal_create(client, sku["id"]).json()
    assert reactivated["id"] == mapping["id"]
    assert reactivated["is_deleted"] is False
    assert reactivated["deleted_reason"] is None


def test_delete_mapping_pauses_before_soft_delete(client, db_engine, monkeypatch):
    import app.api.routes.platform_mappings as mappings_module
    from app.models import PlatformMapping
    from sqlmodel import Session, select

    calls: list[tuple[str, str]] = []

    async def fake_prepare(tenant_id: str, item_id: str):
        calls.append((tenant_id, item_id))
        # The remote mutation must happen while the local row is still active.
        with Session(db_engine) as session:
            row = session.exec(
                select(PlatformMapping).where(
                    PlatformMapping.platform_product_id == "MLB123"
                )
            ).one()
            assert row.is_deleted is False
            assert row.is_active is True
        return {"item_id": item_id, "remote_action": "paused_and_zeroed"}

    monkeypatch.setattr(
        mappings_module.integrations_client, "prepare_item_unlink", fake_prepare
    )

    sku = _make_sku(client)
    mapping = _internal_create(client, sku["id"]).json()

    assert client.delete(f"/api/v1/platform-mappings/{mapping['id']}").status_code == 204

    assert calls == [("test-tenant", "MLB123")]
    history = client.get(
        "/api/v1/platform-mappings", params={"include_deleted": "true"}
    ).json()
    stored = next(item for item in history if item["id"] == mapping["id"])
    assert stored["deleted_reason"] == "user"


def test_delete_mapping_aborts_on_remote_failure(client, monkeypatch):
    import app.api.routes.platform_mappings as mappings_module
    from app.core.errors import APIError

    async def fake_prepare(tenant_id: str, item_id: str):
        raise APIError(
            status_code=503,
            code="remote_unlink_failed",
            message="integration down",
        )

    monkeypatch.setattr(
        mappings_module.integrations_client, "prepare_item_unlink", fake_prepare
    )

    sku = _make_sku(client)
    mapping = _internal_create(client, sku["id"]).json()

    response = client.delete(f"/api/v1/platform-mappings/{mapping['id']}")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "remote_unlink_failed"

    visible = client.get("/api/v1/platform-mappings").json()
    assert [item["id"] for item in visible] == [mapping["id"]]
    assert visible[0]["is_active"] is True


def test_relink_recovers_user_deleted_mapping_and_warns_on_ml_failure(
    client, monkeypatch
):
    import app.api.routes.platform_mappings as mappings_module
    from app.core.errors import APIError

    calls: list[str] = []

    async def fake_update(tenant_id: str, item_id: str, seller_custom_field: str):
        calls.append(seller_custom_field)
        raise APIError(
            status_code=422,
            code="item_update_failed",
            message="seller_custom_field not editable",
        )

    monkeypatch.setattr(
        mappings_module.integrations_client,
        "update_seller_custom_field",
        fake_update,
    )

    sku = _make_sku(client)
    mapping = _internal_create(client, sku["id"]).json()
    client.delete(f"/api/v1/platform-mappings/{mapping['id']}")

    response = client.post(
        "/api/v1/platform-mappings/re-link",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "SKU-1",
            "platform_product_id": "MLB123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mapping"]["id"] == mapping["id"]
    assert body["mapping"]["is_deleted"] is False
    assert body["mapping"]["is_active"] is True
    assert body["warning"]["code"] == "platform_sku_update_failed"
    assert calls == ["SKU-1"]


def test_relink_is_idempotent_for_same_sku(client):
    sku = _make_sku(client)
    mapping = _internal_create(client, sku["id"]).json()

    first = client.post(
        "/api/v1/platform-mappings/re-link",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "SKU-1",
            "platform_product_id": "MLB123",
        },
    )
    second = client.post(
        "/api/v1/platform-mappings/re-link",
        json={
            "sku_id": sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "SKU-1",
            "platform_product_id": "MLB123",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["mapping"]["id"] == mapping["id"]
    assert second.json()["mapping"]["id"] == mapping["id"]
    assert first.json()["warning"] is None


def test_relink_rejects_listing_linked_to_another_sku(client):
    first_sku = _make_sku(client, internal_sku="SKU-1")
    second_sku = _make_sku(client, internal_sku="SKU-2")
    _internal_create(client, first_sku["id"]).json()

    response = client.post(
        "/api/v1/platform-mappings/re-link",
        json={
            "sku_id": second_sku["id"],
            "platform": "mercado_livre",
            "platform_sku": "SKU-2",
            "platform_product_id": "MLB123",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_internal_state_sync_updates_is_active(client):
    sku = _make_sku(client)
    mapping = _internal_create(client, sku["id"]).json()

    response = client.post(
        f"{INTERNAL_PATH}/state",
        json={
            "platform": "mercado_livre",
            "platform_product_id": "MLB123",
            "is_active": False,
        },
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 1}
    visible = client.get("/api/v1/platform-mappings").json()
    assert visible[0]["id"] == mapping["id"]
    assert visible[0]["is_active"] is False


def test_internal_state_sync_discards_stale_event(client):
    from datetime import UTC, datetime, timedelta

    sku = _make_sku(client)
    _internal_create(client, sku["id"]).json()

    stale = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    response = client.post(
        f"{INTERNAL_PATH}/state",
        json={
            "platform": "mercado_livre",
            "platform_product_id": "MLB123",
            "is_active": False,
            "event_timestamp": stale,
        },
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 0}
    visible = client.get("/api/v1/platform-mappings").json()
    assert visible[0]["is_active"] is True
