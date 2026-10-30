"""ListingsSyncService (manual pull) tests."""

from app.models import ListingsSyncRun
from app.services.listings_sync import ListingsSyncService


class FakeIntegrations:
    def __init__(self, items=None):
        self.items = items if items is not None else {}
        self.fail_ids: set[str] = set()

    async def list_item_ids(self, tenant_id):
        ids = list(self.items)
        ids.extend(self.fail_ids)
        return ids

    async def get_item(self, tenant_id, item_id):
        if item_id in self.fail_ids:
            raise RuntimeError("ML 500")
        return self.items[item_id]

    async def upsert_local_item(self, tenant_id, item_data):
        return {"item_id": item_data["id"], "sku_id": item_data.get("_local_sku_id")}


class FakeCatalog:
    def __init__(self, skus_by_field=None, mappings=None):
        self.skus_by_field = skus_by_field or {}
        self.mappings = mappings or {}  # platform_product_id -> mapping
        self.created: list[tuple[int, str, str]] = []

    async def find_mapping_by_product_id(self, item_id, tenant_id=None):
        return self.mappings.get(item_id)

    async def find_sku_by_internal_sku(self, internal_sku, tenant_id=None):
        return self.skus_by_field.get(internal_sku)

    async def get_sku(self, sku_id, tenant_id=None):
        return {"id": sku_id, "internal_sku": f"SKU-{sku_id}", "stock_quantity": 1}

    async def create_mapping_if_missing(self, sku_id, platform_sku, item_id, tenant_id=None):
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
    catalog = FakeCatalog(skus_by_field={"SKU-1": {"id": 7, "internal_sku": "SKU-1"}})

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


async def test_pull_skips_existing_mapping(db_session):
    integrations = FakeIntegrations(
        items={"MLB-1": {"id": "MLB-1", "seller_custom_field": "SKU-1"}}
    )
    catalog = FakeCatalog(
        skus_by_field={"SKU-1": {"id": 7, "internal_sku": "SKU-1"}},
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


async def test_pull_skips_deleted_sku_for_mapping(db_session):
    integrations = FakeIntegrations(
        items={"MLB-1": {"id": "MLB-1", "seller_custom_field": "SKU-1"}}
    )
    catalog = FakeCatalog(
        skus_by_field={
            "SKU-1": {"id": 7, "internal_sku": "SKU-1", "is_deleted": True}
        }
    )

    service = ListingsSyncService(
        db_session, tenant_id="tenant-1", catalog=catalog, integrations=integrations
    )
    result = await service.pull()

    assert result["mappings_created"] == 0
    assert result["errors"] == []
    assert catalog.created == []
