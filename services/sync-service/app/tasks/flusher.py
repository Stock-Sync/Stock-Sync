"""3-second batch flusher for Mercado Livre quantity updates.

Sale processing and user stock changes don't call the ML API directly.
They write the affected item into the ``pending:stock`` Redis hash (last
write wins per item). This background task drains the hash every N seconds:

1. read all pending entries
2. look up the CURRENT local stock for each SKU (self-healing: multiple
   sales inside the window collapse into one API call with the final value)
3. PUT available_quantity on each ML item
4. delete the hash entry on success; keep it on retryable failure

Rejections (4xx: paused/closed item, variation-only listing) are dropped
with a warning so one bad item never blocks the batch.
"""

import asyncio
import json
import logging

from app.core.config import settings
from app.core.redis import get_redis
from app.services.clients import CatalogClient, IntegrationsClient
from app.streams.consts import PENDING_STOCK_KEY

logger = logging.getLogger(__name__)


class QuantityFlusher:
    def __init__(
        self,
        redis_client=None,
        catalog: CatalogClient | None = None,
        integrations: IntegrationsClient | None = None,
        interval: float | None = None,
    ):
        self.redis = redis_client or get_redis()
        self.catalog = catalog or CatalogClient()
        self.integrations = integrations or IntegrationsClient()
        self.interval = interval or settings.flusher_interval_seconds
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        logger.info("flusher_started", extra={"interval": self.interval})
        while not self._stopping.is_set():
            try:
                await self.flush_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("flusher_cycle_error")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stopping.set()

    async def flush_once(self) -> dict:
        pending = await self.redis.hgetall(PENDING_STOCK_KEY)
        if not pending:
            return {"flushed": 0, "failed": 0, "dropped": 0}

        flushed = failed = dropped = 0
        # Cache local SKU lookups: several items may share one SKU.
        sku_cache: dict[int, dict] = {}

        for field, raw in pending.items():
            try:
                entry = json.loads(raw)
                tenant_id = entry["tenant_id"]
                item_id = entry["ml_item_id"]
                sku_id = entry.get("sku_id")
            except (json.JSONDecodeError, KeyError):
                logger.warning("pending_entry_malformed", extra={"field": field})
                await self.redis.hdel(PENDING_STOCK_KEY, field)
                dropped += 1
                continue

            if sku_id is None:
                # Nothing to sync (unmapped item) — clear the entry.
                await self.redis.hdel(PENDING_STOCK_KEY, field)
                dropped += 1
                continue

            if sku_id not in sku_cache:
                sku = await self.catalog.get_sku(int(sku_id), tenant_id=tenant_id)
                if sku is None:
                    logger.warning("flusher_sku_missing", extra={"sku_id": sku_id})
                    await self.redis.hdel(PENDING_STOCK_KEY, field)
                    dropped += 1
                    continue
                sku_cache[sku_id] = sku

            sku = sku_cache[sku_id]
            if sku.get("is_deleted"):
                logger.info(
                    "flusher_sku_deleted_zerando_estoque_ml",
                    extra={"sku_id": sku_id, "item_id": item_id},
                )
                try:
                    # Zero the marketplace quantity so the listing stops
                    # selling an archived product. A rejection here (already
                    # paused/closed, variations) is not worth retrying.
                    await self.integrations.update_item_quantity(
                        tenant_id, item_id, 0
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "flusher_zerar_quantidade_falhou",
                        extra={"item_id": item_id, "error": str(exc)},
                    )
                finally:
                    await self.redis.hdel(PENDING_STOCK_KEY, field)
                    dropped += 1
                continue

            quantity = int(sku["stock_quantity"])

            try:
                await self.integrations.update_item_quantity(tenant_id, item_id, quantity)
            except Exception as exc:  # noqa: BLE001
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and 400 <= status < 500:
                    # Permanent rejection (paused/closed/variations): drop.
                    logger.warning(
                        "flusher_quantity_rejected",
                        extra={"item_id": item_id, "quantity": quantity, "error": str(exc)},
                    )
                    await self.redis.hdel(PENDING_STOCK_KEY, field)
                    dropped += 1
                else:
                    # Transient failure: keep the entry for the next cycle.
                    logger.warning(
                        "flusher_quantity_retry",
                        extra={"item_id": item_id, "error": str(exc)},
                    )
                    failed += 1
                continue

            await self.redis.hdel(PENDING_STOCK_KEY, field)
            flushed += 1
            logger.info(
                "flusher_quantity_updated",
                extra={"item_id": item_id, "sku_id": sku_id, "quantity": quantity},
            )

        return {"flushed": flushed, "failed": failed, "dropped": dropped}
