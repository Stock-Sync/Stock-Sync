"""Listings reconciliation: full import from Mercado Livre.

For every listing of the connected seller:
1. fetch the item and upsert it into the local MarketplaceItem table
2. when the item's seller_custom_field matches an active internal SKU, create
   the missing platform mapping (idempotent)

The import is followed by a destructive reconciliation of listings that
vanished from Mercado Livre. Plan 8 makes it safe and idempotent:

* the search is a full scroll search; a truncated/incomplete search aborts the
  run before any delete (``pagination_truncated``);
* multi-variation listings are persisted but excluded from mapping and from
  both sides of the reconciliation diff;
* a safety circuit breaker flags the run instead of deleting when too many
  local listings would disappear at once;
* the catalog mappings are unbound first, then the local items are soft
  deleted, so a catalog failure never loses local data and a retry is safe.

Writes a ListingsSyncRun audit row so the UI can show the last run summary.
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.core.config import settings
from app.models.listings_sync_run import ListingsSyncRun, SyncRunStatus
from app.services.clients import CatalogClient, IntegrationsClient
from sqlmodel import Session

logger = logging.getLogger(__name__)

CONCURRENCY = 5


class PaginationTruncatedError(Exception):
    """The marketplace search did not return the full listings payload."""


def _has_variations(item_data: dict | None) -> bool:
    if not isinstance(item_data, dict):
        return False
    return bool(item_data.get("children")) or bool(item_data.get("variations"))


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
        removed = 0
        removed_ids_audit: list[str] = []
        flagged = False
        search_phase = True

        try:
            # 1. Full scroll search. Reject a partial payload before touching
            #    the local mirror: a timeout/rate-limit must never look like a
            #    seller deleting most of its listings.
            search = await self.integrations.search_items(tenant_id)
            item_ids = list(dict.fromkeys(search.get("item_ids") or []))
            reported_total = search.get("reported_total")
            if search.get("truncated") or (
                reported_total is not None
                and len(item_ids) < int(reported_total)
            ):
                raise PaginationTruncatedError(
                    "pagination_truncated: "
                    f"fetched={len(item_ids)} reported={reported_total}"
                )
            search_phase = False

            run.items_found = len(item_ids)
            self.session.commit()

            # 2. Snapshot the local active mirror BEFORE the upserts. Rows
            #    created locally while the pull runs are therefore never
            #    candidates for deletion.
            local_mirror = await self.integrations.list_local_active_item_ids(
                tenant_id
            )
            local_active_ids = set(local_mirror.get("item_ids") or [])
            local_variation_ids = set(
                local_mirror.get("variation_item_ids") or []
            )

            semaphore = asyncio.Semaphore(CONCURRENCY)

            async def _sync_one(item_id: str) -> tuple[bool, bool, str | None]:
                async with semaphore:
                    try:
                        item_data = await self.integrations.get_item(
                            tenant_id, item_id
                        )
                        local = await self.integrations.upsert_local_item(
                            tenant_id, item_data
                        )
                        if _has_variations(item_data):
                            # Persisted for audit/history, but never mapped or
                            # stock-synced. Remove any legacy mapping too.
                            await self._exclude_variation_listing(item_id)
                            return True, False, item_id
                        mapping_created = await self._ensure_mapping(
                            item_data, local.get("sku_id")
                        )
                        return True, mapping_created, None
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "listings_pull_item_failed",
                            extra={"item_id": item_id, "error": str(exc)},
                        )
                        errors.append(f"{item_id}: {exc}")
                        return False, False, None

            results = await asyncio.gather(*(_sync_one(i) for i in item_ids))
            upserted = sum(1 for ok, _, _ in results if ok)
            mappings = sum(1 for _, created, _ in results if created)
            current_variation_ids = {
                variation_id
                for _, _, variation_id in results
                if variation_id is not None
            }

            # 3. Reconciliation diff. Variation listings are excluded from
            #    both sides (Plan 8, decision B).
            variation_ids = local_variation_ids | current_variation_ids
            local_active_ids -= variation_ids
            ml_seen_ids = set(item_ids) - variation_ids
            missing_ids = sorted(local_active_ids - ml_seen_ids)
            removed_ids_audit = missing_ids

            active_count = len(local_active_ids)
            missing_count = len(missing_ids)
            threshold = settings.sync_safety_threshold_ratio
            if active_count > 0 and missing_count > active_count * threshold:
                # Safety circuit breaker: do not touch catalog or local rows.
                flagged = True
                removed = 0
                run.status = SyncRunStatus.FLAGGED_SAFETY_THRESHOLD
                logger.warning(
                    "syncevent_safety_threshold_exceeded",
                    extra={
                        "tenant_id": tenant_id,
                        "missing_count": missing_count,
                        "active_count": active_count,
                        "ratio": threshold,
                    },
                )
            else:
                removed = await self._reconcile_missing(missing_ids, errors)
                run.status = (
                    SyncRunStatus.COMPLETED
                    if not errors
                    else SyncRunStatus.COMPLETED_WITH_ERRORS
                )
        except PaginationTruncatedError as exc:
            logger.error(
                "listings_pull_pagination_truncated",
                extra={"tenant_id": tenant_id, "error": str(exc)},
            )
            errors.append("pagination_truncated")
            run.status = SyncRunStatus.FAILED
        except Exception as exc:  # noqa: BLE001
            if search_phase:
                # A network/rate-limit failure while scrolling is equivalent
                # to a truncated pagination: never reconcile against it.
                logger.exception(
                    "listings_pull_search_failed",
                    extra={"tenant_id": tenant_id, "error": str(exc)},
                )
                errors.append("pagination_truncated")
            else:
                logger.exception(
                    "listings_pull_failed", extra={"tenant_id": tenant_id}
                )
                errors.append(str(exc))
            run.status = SyncRunStatus.FAILED
        finally:
            run.items_upserted = upserted
            run.mappings_created = mappings
            run.items_removed = removed_ids_audit
            if run.status == SyncRunStatus.FAILED and "pagination_truncated" in errors:
                # Keep the failure reason stable for logs/UI and retries.
                run.error_summary = "pagination_truncated"
            else:
                run.error_summary = "; ".join(errors)[:2000] if errors else None
            run.finished_at = datetime.now(UTC)
            self.session.add(run)
            self.session.commit()
            self.session.refresh(run)

        return {
            "run_id": run.id,
            "status": run.status,
            "items_found": run.items_found,
            "items_upserted": run.items_upserted,
            "mappings_created": run.mappings_created,
            "items_removed": removed,
            "items_removed_ids": run.items_removed,
            "flagged": flagged,
            "errors": errors[:20],
        }

    async def _exclude_variation_listing(self, item_id: str) -> None:
        """Remove any legacy mapping of a multi-variation listing."""
        existing = await self.catalog.find_mapping_by_product_id(
            item_id, tenant_id=self.tenant_id
        )
        if existing is None:
            return
        await self.catalog.unbind_mappings_for_items(
            [item_id],
            tenant_id=self.tenant_id,
            reason="variation_not_supported",
        )
        logger.info(
            "listing_variation_unmapped",
            extra={"item_id": item_id, "tenant_id": self.tenant_id},
        )

    async def _reconcile_missing(
        self, missing_ids: list[str], errors: list[str]
    ) -> int:
        """Unbind catalog mappings first, then soft delete local items.

        Failures are non-fatal for the pull itself: the run is reported as
        ``completed_with_errors`` and the next pull retries the cleanup. The
        inverted order makes that retry idempotent: catalog unbind returns 0
        for mappings that were already unbound.
        """
        if not missing_ids:
            return 0

        try:
            await self.catalog.unbind_mappings_for_items(
                missing_ids,
                tenant_id=self.tenant_id,
                reason="reconciliation_missing",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "listings_reconcile_catalog_failed",
                extra={"tenant_id": self.tenant_id, "error": str(exc)},
            )
            errors.append(f"reconcile: {exc}")
            return 0

        try:
            deleted_item_ids = await self.integrations.soft_delete_items(
                self.tenant_id, missing_ids
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "listings_reconcile_local_failed",
                extra={"tenant_id": self.tenant_id, "error": str(exc)},
            )
            errors.append(f"reconcile: {exc}")
            return 0

        logger.info(
            "listings_reconciled",
            extra={
                "tenant_id": self.tenant_id,
                "items_removed": len(deleted_item_ids),
            },
        )
        return len(deleted_item_ids)

    async def _ensure_mapping(self, item_data: dict, local_sku_id: int | None) -> bool:
        """Create a platform mapping when the item links to an active SKU."""
        item_id = item_data.get("id")
        if not item_id:
            return False

        tenant_id = self.tenant_id
        custom_field = item_data.get("seller_custom_field")

        # Resolve the SKU first so deleted SKU/product rows are detected even
        # when a stale mapping still exists.
        sku = None
        if custom_field:
            sku = await self.catalog.find_sku_by_internal_sku(
                custom_field, tenant_id=tenant_id
            )
        if sku is None and local_sku_id is not None:
            local_sku = await self.catalog.get_sku(
                int(local_sku_id), tenant_id=tenant_id
            )
            if local_sku is not None and local_sku.get("internal_sku"):
                # Strict lookup also verifies the owning product is active.
                sku = await self.catalog.find_sku_by_internal_sku(
                    local_sku["internal_sku"], tenant_id=tenant_id
                )
            elif local_sku is not None:
                sku = local_sku

        existing = await self.catalog.find_mapping_by_product_id(
            item_id, tenant_id=tenant_id
        )

        # A listing imported before its SKU/product was archived has no
        # seller_custom_field and no local sku_id. Resolve the existing
        # mapping's SKU so the safeguard also removes that stale link.
        if sku is None and existing is not None and existing.get("sku_id"):
            mapped_sku = await self.catalog.get_sku(
                int(existing["sku_id"]), tenant_id=tenant_id
            )
            if mapped_sku is not None and mapped_sku.get("internal_sku"):
                sku = await self.catalog.find_sku_by_internal_sku(
                    mapped_sku["internal_sku"], tenant_id=tenant_id
                )
            elif mapped_sku is not None:
                sku = mapped_sku
            else:
                # The SKU was hard-removed: the mapping is orphaned.
                await self.catalog.unbind_mappings_for_items(
                    [item_id],
                    tenant_id=tenant_id,
                    reason="sku_deleted",
                )
                logger.info(
                    "unmapped_deleted_sku",
                    extra={
                        "item_id": item_id,
                        "custom_field": custom_field,
                        "sku_id": existing.get("sku_id"),
                    },
                )
                return False

        if sku is not None and (
            sku.get("is_deleted")
            or sku.get("product_is_deleted")
            or sku.get("mappable") is False
        ):
            if existing is not None:
                await self.catalog.unbind_mappings_for_items(
                    [item_id],
                    tenant_id=tenant_id,
                    reason="sku_deleted",
                )
            logger.info(
                "unmapped_deleted_sku",
                extra={
                    "item_id": item_id,
                    "custom_field": custom_field,
                    "sku_id": sku.get("id"),
                    "sku_deleted": sku.get("is_deleted"),
                    "product_deleted": sku.get("product_is_deleted"),
                },
            )
            return False

        if existing is not None:
            return False
        if sku is None:
            # Unmapped listing, or a SKU that was already hard-removed from the
            # catalog. Never create a new link in that case.
            logger.info(
                "listing_mapping_skipped_unmapped_sku",
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
