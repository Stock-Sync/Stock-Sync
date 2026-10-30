"""Manual "Sincronizar Anúncios" pull: full import from Mercado Livre.

For every listing of the connected seller:
1. fetch the item and upsert it into the local MarketplaceItem table
2. when the item's seller_custom_field matches an internal SKU, create the
   missing platform mapping (idempotent)

Writes a ListingsSyncRun audit row so the UI can show the last run summary.
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.models.listings_sync_run import ListingsSyncRun, SyncRunStatus
from app.services.clients import CatalogClient, IntegrationsClient
from sqlmodel import Session

logger = logging.getLogger(__name__)

CONCURRENCY = 5


class ListingsSyncService:
    def __init__(
        self,
        session: Session,
        tenant_id: str,
        catalog: CatalogClient | None = None,
        integrations: IntegrationsClient | None = None,
    ):
        self.session = session
        self.tenant_id = tenant_id
        self.catalog = catalog or CatalogClient()
        self.integrations = integrations or IntegrationsClient()

    async def pull(self) -> dict:
        tenant_id = self.tenant_id
        run = ListingsSyncRun(tenant_id=tenant_id, status=SyncRunStatus.RUNNING)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        errors: list[str] = []
        upserted = 0
        mappings = 0

        try:
            item_ids = await self.integrations.list_item_ids(tenant_id)
            run.items_found = len(item_ids)
            self.session.commit()

            semaphore = asyncio.Semaphore(CONCURRENCY)

            async def _sync_one(item_id: str) -> tuple[bool, bool]:
                async with semaphore:
                    try:
                        item_data = await self.integrations.get_item(tenant_id, item_id)
                        local = await self.integrations.upsert_local_item(
                            tenant_id, item_data
                        )
                        mapping_created = await self._ensure_mapping(
                            item_data, local.get("sku_id")
                        )
                        return True, mapping_created
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "listings_pull_item_failed",
                            extra={"item_id": item_id, "error": str(exc)},
                        )
                        errors.append(f"{item_id}: {exc}")
                        return False, False

            results = await asyncio.gather(*(_sync_one(i) for i in item_ids))
            upserted = sum(1 for ok, _ in results if ok)
            mappings = sum(1 for _, created in results if created)

            run.status = (
                SyncRunStatus.COMPLETED
                if not errors
                else SyncRunStatus.COMPLETED_WITH_ERRORS
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("listings_pull_failed", extra={"tenant_id": tenant_id})
            run.status = SyncRunStatus.FAILED
            errors.append(str(exc))
        finally:
            run.items_upserted = upserted
            run.mappings_created = mappings
            run.error_summary = "; ".join(errors)[:2000] if errors else None
            run.finished_at = datetime.now(UTC)
            self.session.commit()
            self.session.refresh(run)

        return {
            "run_id": run.id,
            "status": run.status,
            "items_found": run.items_found,
            "items_upserted": run.items_upserted,
            "mappings_created": run.mappings_created,
            "errors": errors[:20],
        }

    async def _ensure_mapping(self, item_data: dict, local_sku_id: int | None) -> bool:
        """Create a platform mapping when the item links to a known SKU."""
        item_id = item_data.get("id")
        if not item_id:
            return False

        tenant_id = self.tenant_id
        existing = await self.catalog.find_mapping_by_product_id(
            item_id, tenant_id=tenant_id
        )
        if existing is not None:
            return False

        sku = None
        custom_field = item_data.get("seller_custom_field")
        if custom_field:
            sku = await self.catalog.find_sku_by_internal_sku(
                custom_field, tenant_id=tenant_id
            )
        if sku is None and local_sku_id is not None:
            sku = await self.catalog.get_sku(int(local_sku_id), tenant_id=tenant_id)
        if sku is None or sku.get("is_deleted"):
            # Unmapped listing or a SKU that was soft-deleted; don't create
            # a new marketplace mapping for an archived product.
            logger.info(
                "listing_mapping_skipped_deleted_or_unmapped_sku",
                extra={"item_id": item_id, "custom_field": custom_field},
            )
            return False

        created = await self.catalog.create_mapping_if_missing(
            sku["id"], sku["internal_sku"], item_id, tenant_id=tenant_id
        )
        if created:
            logger.info(
                "listing_mapping_created",
                extra={"item_id": item_id, "sku_id": sku["id"]},
            )
        return created
