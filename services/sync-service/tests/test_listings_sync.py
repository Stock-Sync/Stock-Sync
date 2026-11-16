"""ListingsSyncService (manual pull) tests."""

import pytest
from app.models import ListingsSyncRun
from app.services.listings_sync import ListingsSyncService


def _keepers(count: int = 10) -> list[str]:
    return [f"MLB-KEEP-{i}" for i in range(count)]


def _items(*item_ids: str) -> dict[str, dict]:
    return {item_id: {"id": item_id} for item_id in item_ids}


class FakeIntegrations:
    def __init__(
        self,
        items=None,
        local_active=None,
        local_variations=None,
        reported_total=None,
        truncated=False,
        events=None,
    ):
        self.items = items if items is not None else {}
        self.fail_ids: set[str] = set()
        self.local_active = (
            list(local_active) if local_active is not None else list(self.items)
        )
        self.local_variations = local_variations or []
        self.reported_total = reported_total
        self.truncated = truncated
        self.soft_delete_calls: list[list[str]] = []
        self.events = events if events is not None else []

    async def search_items(self, tenant_id):
        ids = list(self.items)
        ids.extend(self.fail_ids)
        return {
            "item_ids": ids,
            "reported_total": (
                self.reported_total
                if self.reported_total is not None
                else len(ids)
            ),
            "truncated": self.truncated,
        }

    async def list_local_active_item_ids(self, tenant_id, synced_before=None):
        return {
            "item_ids": list(self.local_active),
            "variation_item_ids": list(self.local_variations),
        }

    async def get_item(self, tenant_id, item_id):
        if item_id in self.fail_ids:
            raise RuntimeError("ML 500")
        return self.items[item_id]

    async def upsert_local_item(self, tenant_id, item_data):
        return {"item_id": item_data["id"], "sku_id": item_data.get("_local_sku_id")}

    async def soft_delete_items(self, tenant_id, item_ids):
        self.events.append(("local_soft_delete", list(item_ids)))
        self.soft_delete_calls.append(list(item_ids))
        return list(item_ids)


class FakeCatalog:
    def __init__(self, skus_by_field=None, mappings=None, events=None):
        self.skus_by_field = skus_by_field or {}
        self.mappings = mappings or {}  # platform_product_id -> mapping
        self.created: list[tuple[int, str, str]] = []
        self.unbound: list[tuple[list[str], str]] = []
        self.unbind_error: Exception | None = None
        self.events = events if events is not None else []

    async def unbind_mappings_for_items(
        self,
        platform_product_ids,
        platform="mercado_livre",
        tenant_id=None,
        reason="reconciliation_missing",
    ):
        self.events.append(("catalog_unbind", list(platform_product_ids)))
        if self.unbind_error is not None:
            raise self.unbind_error
        self.unbound.append((list(platform_product_ids), reason))
        return len(platform_product_ids)

    async def find_mapping_by_product_id(self, item_id, tenant_id=None):
        return self.mappings.get(item_id)

    async def find_sku_by_internal_sku(self, internal_sku, tenant_id=None):
        return self.skus_by_field.get(internal_sku)

    async def get_sku(self, sku_id, tenant_id=None):
        return {"id": sku_id, "internal_sku": f"SKU-{sku_id}", "stock_quantity": 1}

    async def create_mapping_if_missing(
        self, sku_id, platform_sku, item_id, tenant_id=None
    ):
        if item_id in self.mappings:
            return False
        self.created.append((sku_id, platform_sku, item_id))
        self.mappings[item_id] = {"sku_id": sku_id}
        return True


async def test_pull_syncs_items_and_creates_mappings(db_session):
    integrations = FakeIntegrations(
        items={
            "MLB-1": {
                "id": "MLB-1",
                "title": "Fone",
                "seller_custom_field": "SKU-1",
            },
            "MLB-2": {"id": "MLB-2", "title": "Sem SKU"},
        }
    )
    catalog = FakeCatalog(
        skus_by_field={
            "SKU-1": {"id": 7, "internal_sku": "SKU-1", "mappable": True}
        }
    )

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["status"] == "completed"
    assert result["items_found"] == 2
    assert result["items_upserted"] == 2
    assert result["mappings_created"] == 1
    assert catalog.created == [(7, "SKU-1", "MLB-1")]

    run = db_session.query(ListingsSyncRun).one()
    assert run.status == "completed"
    assert run.finished_at is not None
    assert run.items_removed == []


async def test_pull_skips_existing_mapping(db_session):
    integrations = FakeIntegrations(
        items={"MLB-1": {"id": "MLB-1", "seller_custom_field": "SKU-1"}}
    )
    catalog = FakeCatalog(
        skus_by_field={
            "SKU-1": {"id": 7, "internal_sku": "SKU-1", "mappable": True}
        },
        mappings={"MLB-1": {"sku_id": 7}},
    )

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["mappings_created"] == 0
    assert catalog.created == []


async def test_pull_records_partial_errors(db_session):
    integrations = FakeIntegrations(items={"MLB-1": {"id": "MLB-1"}})
    integrations.fail_ids.add("MLB-BAD")
    catalog = FakeCatalog()

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["status"] == "completed_with_errors"
    assert result["items_upserted"] == 1
    assert len(result["errors"]) == 1
    assert "MLB-BAD" in result["errors"][0]

    run = db_session.query(ListingsSyncRun).one()
    assert run.status == "completed_with_errors"
    assert "MLB-BAD" in run.error_summary


async def test_pull_soft_deletes_listings_missing_from_ml(db_session):
    events: list[tuple[str, list[str]]] = []
    # 1 missing out of 11 active listings (~9%) is inside the safety margin.
    local_active = ["MLB-1", "MLB-GONE", *_keepers(9)]
    integrations = FakeIntegrations(
        items=_items("MLB-1", *_keepers(9)),
        local_active=local_active,
        events=events,
    )
    catalog = FakeCatalog(events=events)

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["items_removed"] == 1
    assert result["items_removed_ids"] == ["MLB-GONE"]
    # Inverted order: catalog unbind first, local soft delete second.
    assert events == [
        ("catalog_unbind", ["MLB-GONE"]),
        ("local_soft_delete", ["MLB-GONE"]),
    ]
    assert integrations.soft_delete_calls == [["MLB-GONE"]]
    assert catalog.unbound == [(["MLB-GONE"], "reconciliation_missing")]

    run = db_session.query(ListingsSyncRun).one()
    assert run.items_removed == ["MLB-GONE"]


async def test_pull_flags_safety_threshold_without_deleting(db_session):
    events: list[tuple[str, list[str]]] = []
    missing = [f"MLB-GONE-{i}" for i in range(5)]
    local_active = ["MLB-1", *missing, *_keepers(10)]
    integrations = FakeIntegrations(
        items=_items("MLB-1", *_keepers(10)),
        local_active=local_active,
        events=events,
    )
    catalog = FakeCatalog(events=events)

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["status"] == "flagged_safety_threshold"
    assert result["flagged"] is True
    assert result["items_removed"] == 0
    assert result["items_removed_ids"] == sorted(missing)
    # Nothing was touched.
    assert events == []
    assert catalog.unbound == []
    assert integrations.soft_delete_calls == []

    run = db_session.query(ListingsSyncRun).one()
    assert run.status == "flagged_safety_threshold"
    assert run.items_removed == sorted(missing)
    assert run.error_summary is None


async def test_pull_marks_run_failed_when_pagination_is_truncated(db_session):
    events: list[tuple[str, list[str]]] = []
    integrations = FakeIntegrations(
        items={"MLB-1": {"id": "MLB-1"}},
        reported_total=100,
        truncated=True,
        events=events,
    )
    catalog = FakeCatalog(events=events)

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["status"] == "failed"
    assert result["items_upserted"] == 0
    assert result["items_removed"] == 0
    assert result["errors"] == ["pagination_truncated"]
    assert events == []

    run = db_session.query(ListingsSyncRun).one()
    assert run.status == "failed"
    assert run.error_summary == "pagination_truncated"
    assert run.items_removed == []


async def test_pull_catalog_failure_leaves_local_items_untouched(db_session):
    missing = "MLB-GONE"
    integrations = FakeIntegrations(
        items=_items("MLB-1", *_keepers(9)),
        local_active=["MLB-1", missing, *_keepers(9)],
    )
    catalog = FakeCatalog()
    catalog.unbind_error = RuntimeError("catalog down")

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["status"] == "completed_with_errors"
    assert result["items_removed"] == 0
    assert integrations.soft_delete_calls == []
    assert any("reconcile" in error for error in result["errors"])


async def test_pull_skips_deleted_sku_for_mapping(db_session):
    integrations = FakeIntegrations(
        items={"MLB-1": {"id": "MLB-1", "seller_custom_field": "SKU-1"}}
    )
    catalog = FakeCatalog(
        skus_by_field={
            "SKU-1": {
                "id": 7,
                "internal_sku": "SKU-1",
                "is_deleted": True,
                "mappable": False,
            }
        }
    )

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["mappings_created"] == 0
    assert result["errors"] == []
    assert catalog.created == []


async def test_pull_skips_deleted_product_for_mapping(db_session):
    integrations = FakeIntegrations(
        items={"MLB-1": {"id": "MLB-1", "seller_custom_field": "SKU-1"}}
    )
    catalog = FakeCatalog(
        skus_by_field={
            "SKU-1": {
                "id": 7,
                "internal_sku": "SKU-1",
                "is_deleted": False,
                "product_is_deleted": True,
                "mappable": False,
            }
        }
    )

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["mappings_created"] == 0
    assert catalog.created == []


async def test_pull_unbinds_legacy_mapping_when_mapped_sku_was_deleted(db_session):
    class DeletedSkuCatalog(FakeCatalog):
        async def get_sku(self, sku_id, tenant_id=None):
            return {
                "id": sku_id,
                "internal_sku": "SKU-7",
                "is_deleted": True,
                "mappable": False,
            }

        async def find_sku_by_internal_sku(self, internal_sku, tenant_id=None):
            return {
                "id": 7,
                "internal_sku": internal_sku,
                "is_deleted": True,
                "mappable": False,
            }

    integrations = FakeIntegrations(items={"MLB-1": {"id": "MLB-1"}})
    catalog = DeletedSkuCatalog(mappings={"MLB-1": {"sku_id": 7}})

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["mappings_created"] == 0
    assert catalog.unbound == [(["MLB-1"], "sku_deleted")]
    assert catalog.created == []


async def test_pull_excludes_variations_from_mapping_and_reconcile(db_session):
    events: list[tuple[str, list[str]]] = []
    integrations = FakeIntegrations(
        items={
            **_items("MLB-1", *_keepers(10)),
            "MLB-VAR": {
                "id": "MLB-VAR",
                "seller_custom_field": "SKU-1",
                "variations": [{"id": "variation-1"}],
            },
        },
        local_active=["MLB-1", *_keepers(10)],
        local_variations=["MLB-VAR"],
        events=events,
    )
    catalog = FakeCatalog(
        skus_by_field={
            "SKU-1": {"id": 7, "internal_sku": "SKU-1", "mappable": True}
        },
        mappings={"MLB-VAR": {"sku_id": 7}},
        events=events,
    )

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    # The variation listing is persisted but never mapped; a stale legacy
    # mapping is removed so stock flushers ignore it.
    assert result["mappings_created"] == 0
    assert catalog.created == []
    assert catalog.unbound == [(["MLB-VAR"], "variation_not_supported")]
    # It is not part of the reconciliation diff either.
    assert integrations.soft_delete_calls == []
    assert result["items_removed"] == 0


async def test_pull_without_missing_items_does_not_call_reconcile(db_session):
    integrations = FakeIntegrations(
        items={"MLB-1": {"id": "MLB-1"}},
        local_active=["MLB-1"],
    )
    catalog = FakeCatalog()

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["status"] == "completed"
    assert result["items_removed"] == 0
    assert catalog.unbound == []
    assert integrations.soft_delete_calls == []


def test_safety_threshold_default_is_ten_percent():
    # Guard against accidental configuration drift.
    from app.core.config import Settings

    default = Settings.model_fields["sync_safety_threshold_ratio"].default
    assert default == pytest.approx(0.10)
