"""Business processing of stream events.

Two pipelines:
- ``order_created``: fetch the full ML order, record the sale in sales-service,
  then apply the stock movement exactly once per (order, item), and enqueue the
  marketplace quantity refresh (3s batched by the flusher).
- ``stock_adjust``: user-driven stock change; enqueue quantity refreshes for
  every ML listing mapped to the SKU.

Stock rules:
- Only paid/approved orders (``paid``, ``confirmed``) deduct stock.
- Cancellations/refunds return exactly the quantity that was deducted, never
  the marketplace quantity (a sale clamped at zero deducts less than ordered).
- A sale is recorded even when its stock movement fails; the event is retried
  and only the failed movement is replayed (claims are idempotent).
- Archived SKUs never deduct; the listing is zeroed/paused through the flusher.
- Variations are unsupported and never deduct the parent SKU. The sale is
  recorded with ``is_variation=True`` so the item can be reviewed.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
from app.core.config import settings
from app.core.redis import get_redis
from app.models import StockUpdateLog
from app.services.clients import CatalogClient, IntegrationsClient, SalesClient
from app.streams.consts import PENDING_STOCK_KEY
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

TIMEOUT = 30.0

# Marketplace order statuses that approve the sale and therefore move stock.
PAID_STATUSES = {"paid", "confirmed"}
# A cancellation/refund never reactivates the listing on Mercado Livre; it only
# fixes the local quantity (the flusher pushes available_quantity).
CANCELLATION_STATUSES = {"cancelled", "refunded"}
DEDUCTION_SOURCE = "ml_sale"
CANCELLATION_SOURCE = "ml_cancellation"

# Explicit claim states. ``in_progress`` is leased; ``applied``/``skipped`` are
# terminal; ``failed`` can be retried by a later delivery.
STATUS_IN_PROGRESS = "in_progress"
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
TERMINAL_STATUSES = {STATUS_APPLIED, STATUS_SKIPPED}


class StockProcessingError(RuntimeError):
    """The sale was recorded but at least one stock movement failed.

    Raising this after the sale is persisted makes the stream consumer retry
    the event. Re-delivery is safe: the sale upsert is idempotent and already
    applied stock claims are skipped.
    """


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _truncate_description(text: str | None, max_length: int = 2000) -> tuple[str | None, bool]:
    """Truncate description and return (truncated_text, is_truncated)."""
    if not text:
        return None, False
    is_truncated = len(text) > max_length
    return (text[:max_length], is_truncated) if is_truncated else (text, False)


def _internal_headers(tenant_id: str | None = None) -> dict[str, str]:
    headers = {"X-Internal-Secret": settings.internal_service_secret}
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    return headers


class OrderProcessor:
    def __init__(
        self,
        session: Session,
        catalog: CatalogClient | None = None,
        integrations: IntegrationsClient | None = None,
        sales: SalesClient | None = None,
        redis_client=None,
    ):
        self.session = session
        self.catalog = catalog or CatalogClient()
        self.integrations = integrations or IntegrationsClient()
        self.sales = sales or SalesClient()
        self.redis = redis_client or get_redis()

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    async def enqueue_quantity_update(
        self, tenant_id: str, ml_item_id: str, sku_id: int | None
    ) -> None:
        """Register a pending ML quantity update (consumed by the 3s flusher)."""
        field = f"{tenant_id}:{ml_item_id}"
        value = json.dumps(
            {"tenant_id": tenant_id, "ml_item_id": ml_item_id, "sku_id": sku_id}
        )
        # Hash semantics: last write wins, one entry per (tenant, item).
        await self.redis.hset(PENDING_STOCK_KEY, field, value)

    def _find_stock_log(
        self, order_id: str, item_id: str, source: str
    ) -> StockUpdateLog | None:
        return self.session.exec(
            select(StockUpdateLog).where(
                StockUpdateLog.marketplace_order_id == order_id,
                StockUpdateLog.marketplace_item_id == item_id,
                StockUpdateLog.source_platform == source,
            )
        ).first()

    @staticmethod
    def _lease_seconds() -> float:
        # Must outlive an in-flight HTTP adjustment so a live worker is never
        # mistaken for a crashed one.
        return max(float(settings.claim_lease_seconds), TIMEOUT * 2)

    def _lease_is_active(self, claim: StockUpdateLog) -> bool:
        expires = _as_utc(claim.lease_expires_at)
        return expires is not None and expires > datetime.now(UTC)

    def _claim_stock_adjust(
        self, order_id: str, item_id: str, internal_sku: str, source: str
    ) -> StockUpdateLog | None:
        """Reserve the (order, item, source) adjustment; None means duplicate.

        The INSERT is the idempotency lock: the unique constraint on
        ``StockUpdateLog`` makes concurrent/redelivered notifications lose the
        race instead of moving stock twice. A ``failed`` claim or an expired
        ``in_progress`` lease is reused for a retry.
        """
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=self._lease_seconds())

        existing = self._find_stock_log(order_id, item_id, source)
        if existing is not None:
            if existing.status in TERMINAL_STATUSES:
                return None
            if existing.status == STATUS_IN_PROGRESS and self._lease_is_active(
                existing
            ):
                return None
            if existing.status not in {STATUS_IN_PROGRESS, STATUS_FAILED}:
                # Unknown legacy state: never risk double-moving stock.
                return None

            existing.status = STATUS_IN_PROGRESS
            existing.previous_quantity = 0
            existing.new_quantity = 0
            existing.deducted_quantity = 0
            existing.clamped = False
            existing.attempts = (existing.attempts or 0) + 1
            existing.error_message = None
            existing.heartbeat_at = now
            existing.lease_expires_at = lease_until
            existing.updated_at = now
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing

        claim = StockUpdateLog(
            internal_sku=internal_sku,
            previous_quantity=0,
            new_quantity=0,
            source_platform=source,
            marketplace_order_id=order_id,
            marketplace_item_id=item_id,
            status=STATUS_IN_PROGRESS,
            attempts=1,
            heartbeat_at=now,
            lease_expires_at=lease_until,
            updated_at=now,
        )
        self.session.add(claim)
        try:
            self.session.commit()
            self.session.refresh(claim)
            return claim
        except IntegrityError:
            # Another worker/notification already claimed this adjustment.
            self.session.rollback()
            return None

    def _renew_claim_lease(self, claim_id: int) -> None:
        claim = self.session.get(StockUpdateLog, claim_id)
        if claim is None or claim.status != STATUS_IN_PROGRESS:
            return
        now = datetime.now(UTC)
        claim.heartbeat_at = now
        claim.lease_expires_at = now + timedelta(seconds=self._lease_seconds())
        claim.updated_at = now
        self.session.add(claim)
        self.session.commit()

    async def _heartbeat_claim_loop(self, claim_id: int) -> None:
        """Extend the lease while a slow external call is in flight."""
        interval = max(0.05, float(settings.claim_heartbeat_seconds))
        while True:
            await asyncio.sleep(interval)
            try:
                self._renew_claim_lease(claim_id)
            except Exception:  # noqa: BLE001 - never crash the processor
                logger.exception(
                    "stock_claim_heartbeat_failed", extra={"claim_id": claim_id}
                )
                return

    async def _apply_stock_adjust(
        self,
        tenant_id: str,
        order_id: str,
        item_id: str,
        sku: dict,
        delta: int,
        source: str,
        success_status: str,
    ) -> StockUpdateLog | None:
        """Atomically apply one idempotent stock adjustment.

        Returns the applied claim, or None when the adjustment was already
        handled (terminal claim or a live lease owned by another worker).
        """
        claim = self._claim_stock_adjust(
            order_id, item_id, sku["internal_sku"], source
        )
        if claim is None:
            logger.info(
                "stock_adjust_duplicate_skipped",
                extra={
                    "order_id": order_id,
                    "item_id": item_id,
                    "source": source,
                },
            )
            return None

        heartbeat = asyncio.create_task(self._heartbeat_claim_loop(claim.id))
        try:
            adjust = await self.catalog.adjust_stock(
                sku["id"], delta, source=source, tenant_id=tenant_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "stock_adjust_failed",
                extra={"sku_id": sku["id"], "source": source},
            )
            claim.status = STATUS_FAILED
            claim.error_message = str(exc)[:2000]
            claim.heartbeat_at = datetime.now(UTC)
            claim.lease_expires_at = None
            claim.updated_at = datetime.now(UTC)
            self.session.add(claim)
            self.session.commit()
            raise
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

        previous = int(adjust["previous_quantity"])
        new = int(adjust["new_quantity"])
        claim.previous_quantity = previous
        claim.new_quantity = new
        claim.clamped = bool(adjust.get("clamped"))
        claim.deducted_quantity = (
            max(0, previous - new) if source == DEDUCTION_SOURCE else 0
        )
        claim.status = success_status
        claim.error_message = None
        claim.heartbeat_at = datetime.now(UTC)
        claim.lease_expires_at = None
        claim.updated_at = datetime.now(UTC)
        self.session.add(claim)
        self.session.commit()
        return claim

    async def _deduct_sale(
        self, tenant_id: str, order_id: str, item_id: str, sku: dict, quantity: int
    ) -> StockUpdateLog | None:
        # A cancellation may be delivered before the paid notification. In
        # that case the cancellation tombstone wins and no stock is deducted.
        if self._find_stock_log(order_id, item_id, CANCELLATION_SOURCE) is not None:
            logger.info(
                "sale_ignored_after_cancellation",
                extra={"order_id": order_id, "item_id": item_id},
            )
            return None
        return await self._apply_stock_adjust(
            tenant_id,
            order_id,
            item_id,
            sku,
            delta=-quantity,
            source=DEDUCTION_SOURCE,
            success_status=STATUS_APPLIED,
        )

    def _mark_cancellation_skipped(
        self, order_id: str, item_id: str, sku: dict
    ) -> StockUpdateLog | None:
        """Leave a tombstone so a late paid event cannot deduct stock."""
        claim = self._claim_stock_adjust(
            order_id, item_id, sku["internal_sku"], CANCELLATION_SOURCE
        )
        if claim is None:
            return None
        now = datetime.now(UTC)
        claim.previous_quantity = 0
        claim.new_quantity = 0
        claim.deducted_quantity = 0
        claim.clamped = False
        claim.status = STATUS_SKIPPED
        claim.heartbeat_at = now
        claim.lease_expires_at = None
        claim.updated_at = now
        self.session.add(claim)
        self.session.commit()
        return claim

    async def _reverse_sale(
        self, tenant_id: str, order_id: str, item_id: str, sku: dict
    ) -> StockUpdateLog | None:
        """Return the quantity actually deducted for a cancelled/refunded order."""
        existing_cancellation = self._find_stock_log(
            order_id, item_id, CANCELLATION_SOURCE
        )
        if existing_cancellation is not None:
            if existing_cancellation.status in TERMINAL_STATUSES:
                return None
            if (
                existing_cancellation.status == STATUS_IN_PROGRESS
                and self._lease_is_active(existing_cancellation)
            ):
                return None
            # A failed/expired cancellation claim is retried below.

        deduction = self._find_stock_log(order_id, item_id, DEDUCTION_SOURCE)
        if (
            deduction is not None
            and deduction.status == STATUS_IN_PROGRESS
            and self._lease_is_active(deduction)
        ):
            # Another worker is still deducting. Do not tombstone yet: retry
            # later so the restock sees the final deducted quantity.
            raise StockProcessingError(
                f"deduction still in progress for order={order_id} item={item_id}"
            )

        actual_deducted = 0
        if deduction is not None and deduction.status == STATUS_APPLIED:
            actual_deducted = deduction.deducted_quantity or max(
                0, deduction.previous_quantity - deduction.new_quantity
            )

        if actual_deducted <= 0:
            # Nothing was deducted (or the deduction failed). Keep a
            # cancellation tombstone and don't call the catalog.
            self._mark_cancellation_skipped(order_id, item_id, sku)
            logger.info(
                "sale_cancellation_without_deduction",
                extra={"order_id": order_id, "item_id": item_id},
            )
            return None

        return await self._apply_stock_adjust(
            tenant_id,
            order_id,
            item_id,
            sku,
            delta=actual_deducted,
            source=CANCELLATION_SOURCE,
            success_status=STATUS_APPLIED,
        )

    # ------------------------------------------------------------------ #
    # order_created
    # ------------------------------------------------------------------ #

    async def process_order(self, tenant_id: str, order_id: str) -> dict:
        order = await self.integrations.get_order(tenant_id, order_id)
        buyer = order.get("buyer") or {}
        currency = order.get("currency", "BRL")
        order_status = order.get("status") or ""
        ordered_at = order.get("date_created")
        order_ref = str(order.get("id", order_id))
        is_cancellation = order_status in CANCELLATION_STATUSES
        is_paid = order_status in PAID_STATUSES
        failures: list[tuple[str, Exception]] = []
        results = []

        for order_item in order.get("order_items", []):
            item = order_item.get("item", {})
            ml_item_id = item.get("id", "")
            title = item.get("title")
            quantity = int(order_item.get("quantity", 1))
            unit_price = float(order_item.get("unit_price", 0) or 0)
            total_amount = float(
                order_item.get("full_unit_price") or (unit_price * quantity)
            )
            # A variation lives under a parent ML listing. Variations are not
            # supported by this system; the parent SKU must never move.
            variation_id = item.get("variation_id") or order_item.get("variation_id")
            is_variation = bool(variation_id)

            sku = await self._resolve_sku(tenant_id, ml_item_id, item)
            sku_id = sku["id"] if sku else None
            internal_sku = sku["internal_sku"] if sku else None
            sku_deleted = bool(
                sku and (sku.get("is_deleted") or sku.get("product_is_deleted"))
            )
            stock_action = "none"

            # 1. Persist the sale first. A stock failure must never lose the
            #    order history; the event retry only re-runs the movement.
            await self.sales.record_order(
                {
                    "tenant_id": tenant_id,
                    "marketplace": "mercado_livre",
                    "marketplace_order_id": order_ref,
                    "marketplace_item_id": ml_item_id,
                    "internal_sku": internal_sku,
                    "sku_id": sku_id,
                    "item_title": title,
                    "thumbnail_url": None,
                    "buyer_nickname": buyer.get("nickname"),
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total_amount": total_amount,
                    "currency": currency,
                    "status": order_status,
                    "is_variation": is_variation,
                    "ordered_at": ordered_at,
                },
                tenant_id=tenant_id,
            )

            # 2. Apply the stock movement exactly once per (order, item).
            try:
                if is_variation:
                    stock_action = "variation_skipped"
                    logger.warning(
                        "sale_for_variation_no_deduction",
                        extra={
                            "ml_item_id": ml_item_id,
                            "variation_id": variation_id,
                            "order_id": order_id,
                            "tenant_id": tenant_id,
                        },
                    )
                elif sku is None:
                    stock_action = "unmapped"
                elif sku_deleted:
                    # Never deduct an archived SKU. The flusher receives an
                    # update for this item and zeroes/pauses the listing.
                    stock_action = "deleted_sku_paused"
                    logger.warning(
                        "sale_for_deleted_sku_zeroing_listing",
                        extra={
                            "ml_item_id": ml_item_id,
                            "sku_id": sku_id,
                            "order_id": order_id,
                            "tenant_id": tenant_id,
                        },
                    )
                elif is_cancellation:
                    reversed_claim = await self._reverse_sale(
                        tenant_id, order_ref, ml_item_id, sku
                    )
                    stock_action = (
                        "restocked" if reversed_claim is not None else "cancellation_skipped"
                    )
                elif is_paid:
                    deducted = await self._deduct_sale(
                        tenant_id, order_ref, ml_item_id, sku, quantity
                    )
                    stock_action = "deducted" if deducted is not None else "duplicate"
                else:
                    # Pending/in_process/etc. Only record the sale for now. A
                    # later paid/confirmed notification performs the deduction.
                    stock_action = "awaiting_payment"
            except Exception as exc:  # noqa: BLE001
                failures.append((ml_item_id, exc))
                stock_action = "failed"
                logger.exception(
                    "sale_stock_processing_failed",
                    extra={
                        "order_id": order_id,
                        "ml_item_id": ml_item_id,
                        "tenant_id": tenant_id,
                    },
                )

            # 3. Queue the marketplace quantity refresh (3s batch). Archived
            #    SKUs are included so the flusher pushes zero. Variations are
            #    excluded because the parent listing must not be touched.
            if sku_id is not None and not is_variation:
                if sku_deleted or is_cancellation or is_paid:
                    await self.enqueue_quantity_update(tenant_id, ml_item_id, sku_id)

            results.append(
                {
                    "ml_item_id": ml_item_id,
                    "sku_id": sku_id,
                    "quantity": quantity,
                    "mapped": sku is not None,
                    "is_variation": is_variation,
                    "stock_action": stock_action,
                }
            )

        logger.info(
            "order_processed",
            extra={
                "order_id": order_id,
                "tenant_id": tenant_id,
                "items": len(results),
                "cancelled": is_cancellation,
                "paid": is_paid,
                "stock_failures": len(failures),
            },
        )

        if failures:
            ml_item_id, exc = failures[0]
            raise StockProcessingError(
                f"stock movement failed for {len(failures)} item(s); "
                f"first item={ml_item_id}: {exc}"
            ) from exc

        return {"order_id": order_ref, "items": results}

    async def _resolve_sku(
        self, tenant_id: str, ml_item_id: str, item: dict
    ) -> dict | None:
        """Map an ML item to a catalog SKU.

        Order of preference:
        1. seller_custom_field (the internal SKU the seller typed on ML)
        2. platform-mapping by ML item id
        """
        custom_field = item.get("seller_custom_field")
        if custom_field:
            sku = await self.catalog.find_sku_by_internal_sku(
                custom_field, tenant_id=tenant_id
            )
            if sku is not None:
                return sku
        # Include soft-deleted mappings: a sale can arrive after the listing
        # was reconciled away, and the historical link still identifies the SKU.
        mapping = await self.catalog.find_mapping_by_product_id(
            ml_item_id, tenant_id=tenant_id, include_deleted=True
        )
        if mapping is not None:
            sku = await self.catalog.get_sku(mapping["sku_id"], tenant_id=tenant_id)
            if sku is not None:
                return sku
        logger.warning("sale_item_unmapped", extra={"ml_item_id": ml_item_id})
        return None

    # ------------------------------------------------------------------ #
    # stock_adjust (from catalog-service)
    # ------------------------------------------------------------------ #

    async def process_stock_adjust(self, payload: dict) -> dict:
        """User changed stock in the program → refresh linked ML listings.

        ``tenant_id`` is mandatory (Plan 10): the consumer dead-letters events
        without it, and this method refuses to guess the tenant when called
        directly.
        """
        sku_id = payload.get("sku_id")
        new_quantity = payload.get("new_quantity")
        tenant_id = payload.get("tenant_id")
        if sku_id is None or new_quantity is None:
            raise ValueError("stock_adjust payload requires sku_id and new_quantity")
        if not tenant_id:
            raise ValueError("stock_adjust payload requires tenant_id")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{settings.catalog_service_url.rstrip('/')}/api/v1/platform-mappings",
                params={"platform": "mercado_livre"},
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            mappings = [m for m in response.json() if m["sku_id"] == int(sku_id)]

        enqueued = []
        for mapping in mappings:
            item_id = mapping.get("platform_product_id")
            if not item_id:
                continue
            # Plan 10 flusher bypass rules applied at the origin too: inactive
            # mappings and multi-variation listings never enter the batch.
            if not mapping.get("is_active", True):
                continue
            if mapping.get("platform_variant_id"):
                logger.warning(
                    "variation_stock_update_ignored",
                    extra={"ml_item_id": item_id, "sku_id": sku_id},
                )
                continue
            await self.enqueue_quantity_update(tenant_id, item_id, int(sku_id))
            enqueued.append(item_id)

        logger.info(
            "stock_adjust_processed",
            extra={"sku_id": sku_id, "new_quantity": new_quantity, "items": enqueued},
        )
        return {"sku_id": sku_id, "enqueued_items": enqueued}

    async def _tenant_for_item(self, ml_item_id: str) -> str | None:
        """Resolve which tenant owns an ML item (via MarketplaceItem)."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{settings.integrations_service_url.rstrip('/')}"
                f"/api/v1/integrations/internal/mercadolivre/items/{ml_item_id}/owner",
                headers=_internal_headers(),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json().get("tenant_id")

    async def mirror_metadata_from_ml(
        self, tenant_id: str, item_data: dict
    ) -> dict | None:
        """Mirror ML item metadata into catalog Product/SKU (Plan 12).

        Updates Product.name, Product.description, Product.pictures,
        Product.is_description_truncated and SKU.price from the ML item.
        Never overwrites SKU.stock_quantity or SKU.internal_sku.

        Resolves the product_id via the platform mapping, then calls the
        catalog internal endpoint (bypasses UI read-only enforcement).
        """
        item_id = item_data.get("id")
        if not item_id:
            return None

        # Find the mapping → sku → product chain
        mapping = await self.catalog.find_mapping_by_product_id(
            item_id, tenant_id=tenant_id, include_deleted=False
        )
        if not mapping or not mapping.get("sku_id"):
            logger.debug(
                "metadata_mirror_no_mapping",
                extra={"ml_item_id": item_id, "tenant_id": tenant_id},
            )
            return None

        sku_id = mapping["sku_id"]
        sku = await self.catalog.get_sku(sku_id, tenant_id=tenant_id)
        if not sku or sku.get("is_deleted"):
            return None

        product_id = sku.get("product_id")
        if not product_id:
            return None

        # Extract ML fields
        ml_title = item_data.get("title")
        ml_pictures = item_data.get("pictures")
        ml_thumbnail = item_data.get("thumbnail")
        ml_description = item_data.get("description")  # plain_text or truncated

        # Build picture list from ML pictures/thumbnail
        picture_urls: list[str] = []
        if isinstance(ml_pictures, list):
            for pic in ml_pictures:
                if isinstance(pic, dict) and pic.get("secure_url"):
                    picture_urls.append(pic["secure_url"])
                elif isinstance(pic, str):
                    picture_urls.append(pic)
        if ml_thumbnail and ml_thumbnail not in picture_urls:
            picture_urls.insert(0, ml_thumbnail)

        # Truncate description
        truncated_text: str | None = None
        is_truncated = False
        if ml_description is not None:
            truncated_text, is_truncated = _truncate_description(str(ml_description))

        return await self.catalog.mirror_product_metadata_from_ml(
            product_id=product_id,
            tenant_id=tenant_id,
            name=ml_title,
            description=truncated_text,
            pictures=picture_urls if picture_urls else None,
            is_description_truncated=is_truncated if ml_description else None,
        )
