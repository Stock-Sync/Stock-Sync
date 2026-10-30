"""Business processing of stream events.

Two pipelines:
- ``order_created``: fetch the full ML order, resolve SKUs, deduct stock via
  the atomic catalog endpoint, persist the sale in sales-service and enqueue
  the marketplace quantity refresh (3s batched by the flusher).
- ``stock_adjust``: user-driven stock change; enqueue quantity refreshes for
  every ML listing mapped to the SKU.
"""

import json
import logging

import httpx
from app.core.config import settings
from app.core.redis import get_redis
from app.models import StockUpdateLog
from app.services.clients import CatalogClient, IntegrationsClient, SalesClient
from app.streams.consts import PENDING_STOCK_KEY
from sqlmodel import Session

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


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

    def _log_stock_change(
        self,
        internal_sku: str,
        previous: int,
        new: int,
        source: str,
        status: str = "success",
        error: str | None = None,
    ) -> None:
        self.session.add(
            StockUpdateLog(
                internal_sku=internal_sku,
                previous_quantity=previous,
                new_quantity=new,
                source_platform=source,
                status=status,
                error_message=error,
            )
        )
        self.session.commit()

    # ------------------------------------------------------------------ #
    # order_created
    # ------------------------------------------------------------------ #

    async def process_order(self, tenant_id: str, order_id: str) -> dict:
        order = await self.integrations.get_order(tenant_id, order_id)
        buyer = order.get("buyer") or {}
        currency = order.get("currency", "BRL")
        order_status = order.get("status", "paid")
        ordered_at = order.get("date_created")
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

            sku = await self._resolve_sku(tenant_id, ml_item_id, item)
            sku_id = sku["id"] if sku else None
            internal_sku = sku["internal_sku"] if sku else None
            sku_deleted = bool(sku and sku.get("is_deleted"))

            # 1. Deduct stock (atomic in the catalog), unless the SKU was
            # soft-deleted. Archived products still keep their sales history.
            if sku is not None and not sku_deleted:
                try:
                    adjust = await self.catalog.adjust_stock(
                        sku["id"], -quantity, source="ml_sale", tenant_id=tenant_id
                    )
                    self._log_stock_change(
                        internal_sku=internal_sku,
                        previous=adjust["previous_quantity"],
                        new=adjust["new_quantity"],
                        source="ml_sale",
                        status="clamped" if adjust.get("clamped") else "success",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("stock_deduct_failed", extra={"sku_id": sku["id"]})
                    self._log_stock_change(
                        internal_sku=internal_sku,
                        previous=sku.get("stock_quantity", 0),
                        new=sku.get("stock_quantity", 0),
                        source="ml_sale",
                        status="failed",
                        error=str(exc)[:2000],
                    )
                    raise
            elif sku_deleted:
                logger.warning(
                    "sale_for_deleted_sku_skipping_deduction",
                    extra={
                        "ml_item_id": ml_item_id,
                        "sku_id": sku_id,
                        "order_id": order_id,
                    },
                )

            # 2. Persist the sale (idempotent upsert on the sales side).
            await self.sales.record_order(
                {
                    "marketplace": "mercado_livre",
                    "marketplace_order_id": str(order.get("id", order_id)),
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
                    "ordered_at": ordered_at,
                }
            )

            # 3. Queue the marketplace quantity refresh (3s batch).
            if sku_id is not None and not sku_deleted:
                await self.enqueue_quantity_update(tenant_id, ml_item_id, sku_id)

            results.append(
                {
                    "ml_item_id": ml_item_id,
                    "sku_id": sku_id,
                    "quantity": quantity,
                    "mapped": sku is not None,
                }
            )

        logger.info(
            "order_processed",
            extra={"order_id": order_id, "tenant_id": tenant_id, "items": len(results)},
        )
        return {"order_id": str(order.get("id", order_id)), "items": results}

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
            sku = await self.catalog.find_sku_by_internal_sku(custom_field, tenant_id=tenant_id)
            if sku is not None:
                return sku
        mapping = await self.catalog.find_mapping_by_product_id(ml_item_id, tenant_id=tenant_id)
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
        """User changed stock in the program → refresh linked ML listings."""
        sku_id = payload.get("sku_id")
        new_quantity = payload.get("new_quantity")
        tenant_id = payload.get("tenant_id")
        if sku_id is None or new_quantity is None:
            raise ValueError("stock_adjust payload requires sku_id and new_quantity")

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
            tenant_id = await self._tenant_for_item(item_id)
            if tenant_id is None:
                logger.warning(
                    "stock_adjust_tenant_unknown", extra={"ml_item_id": item_id}
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
