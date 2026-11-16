"""HTTP clients for service-to-service calls (all guarded by the shared secret)."""

import logging
from datetime import datetime

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


def _internal_headers(tenant_id: str | None = None) -> dict[str, str]:
    headers = {"X-Internal-Secret": settings.internal_service_secret}
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    return headers


class CatalogClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.catalog_service_url).rstrip("/")

    async def adjust_stock(
        self, sku_id: int, delta: int, source: str, tenant_id: str | None = None
    ) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/skus/{sku_id}/adjust",
                json={"delta": delta, "source": source},
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()

    async def get_sku(
        self, sku_id: int, tenant_id: str | None = None
    ) -> dict | None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/skus/{sku_id}",
                headers=_internal_headers(tenant_id),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def find_sku_by_internal_sku(
        self, internal_sku: str, tenant_id: str | None = None
    ) -> dict | None:
        """Resolve an internal SKU including its product deletion state.

        The catalog lookup returns ``mappable=False`` when either the SKU or
        its product is soft-deleted. Callers must not create a new marketplace
        mapping for such listings.
        """
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/internal/skus/lookup",
                params={"internal_sku": internal_sku},
                headers=_internal_headers(tenant_id),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def find_mapping_by_product_id(
        self,
        platform_product_id: str,
        tenant_id: str | None = None,
        include_deleted: bool = False,
    ) -> dict | None:
        """Resolve an ML item id to a platform mapping (which carries sku_id).

        ``include_deleted`` is used by order processing: a sale may arrive
        after the listing was reconciled away, and its SKU must still resolve.
        """
        params = {
            "platform": "mercado_livre",
            "platform_product_id": platform_product_id,
        }
        if include_deleted:
            params["include_deleted"] = "true"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/platform-mappings",
                params=params,
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            mappings = response.json()
            # Prefer the live mapping over a historical tombstone.
            for mapping in mappings:
                if not mapping.get("is_deleted"):
                    return mapping
            return mappings[0] if mappings else None

    async def unbind_mappings_for_items(
        self,
        platform_product_ids: list[str],
        platform: str = "mercado_livre",
        tenant_id: str | None = None,
        reason: str = "reconciliation_missing",
    ) -> int:
        """Unbind mappings whose marketplace listing vanished (batch, idempotent).

        Uses the internal endpoint so the sync-service does not need a user JWT.
        A repeated call after a partial failure returns 0 instead of erroring.
        """
        if not platform_product_ids:
            return 0
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/internal/platform-mappings/unbind",
                json={
                    "platform_product_ids": platform_product_ids,
                    "reason": reason,
                },
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return int(response.json().get("unbound", 0))

    async def soft_delete_mappings_for_items(
        self,
        platform_product_ids: list[str],
        platform: str = "mercado_livre",
        tenant_id: str | None = None,
    ) -> int:
        """Hide mappings whose marketplace listing no longer exists.

        Soft delete keeps the historical rows (and past sales) intact while
        removing the listings from the UI.
        """
        if not platform_product_ids:
            return 0
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/platform-mappings/soft-delete",
                json={
                    "platform": platform,
                    "platform_product_ids": platform_product_ids,
                },
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return int(response.json().get("deleted", 0))

    async def create_mapping_if_missing(
        self,
        sku_id: int,
        platform_sku: str,
        platform_product_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Create the ML mapping when absent. Returns True when created."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/platform-mappings",
                params={
                    "platform": "mercado_livre",
                    "platform_product_id": platform_product_id,
                },
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            if response.json():
                return False
            create = await client.post(
                f"{self.base_url}/api/v1/platform-mappings",
                json={
                    "sku_id": sku_id,
                    "platform": "mercado_livre",
                    "platform_sku": platform_sku,
                    "platform_product_id": platform_product_id,
                    "is_active": True,
                },
                headers=_internal_headers(tenant_id),
            )
            if create.status_code == 409:
                return False
            create.raise_for_status()
            return True

    async def mirror_product_metadata_from_ml(
        self,
        product_id: int,
        tenant_id: str,
        name: str | None = None,
        description: str | None = None,
        pictures: list[str] | None = None,
        is_description_truncated: bool | None = None,
    ) -> dict:
        """Mirror ML metadata into catalog Product (internal endpoint).

        Bypasses UI read-only enforcement because this is a server sync.
        Only ML-managed fields are updated.
        """
        params: dict[str, str] = {}
        if name is not None:
            params["name"] = name
        if description is not None:
            params["description"] = description
        if pictures is not None:
            params["pictures"] = ",".join(pictures)
        if is_description_truncated is not None:
            params["is_description_truncated"] = str(is_description_truncated).lower()

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.put(
                f"{self.base_url}/api/v1/internal/products/{product_id}/metadata-from-ml",
                params=params,
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()


class IntegrationsClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.integrations_service_url).rstrip("/")

    async def resolve_tenant_by_ml_user(self, ml_user_id: int) -> dict | None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre"
                f"/credentials/by-ml-user/{ml_user_id}",
                headers=_internal_headers(),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def get_order(self, tenant_id: str, order_id: str) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre/orders/{order_id}",
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()

    async def get_item(self, tenant_id: str, item_id: str) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre/items/{item_id}",
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()

    async def search_items(self, tenant_id: str) -> dict:
        """Return the full scroll search result (item ids + truncation data)."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre/items",
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()

    async def list_item_ids(self, tenant_id: str) -> list[str]:
        """Backwards-compatible id list; prefer ``search_items``."""
        return (await self.search_items(tenant_id)).get("item_ids", [])

    async def list_local_active_item_ids(
        self, tenant_id: str, synced_before: datetime | None = None
    ) -> dict:
        """Local mirror split into normal and variation listings."""
        params: dict = {}
        if synced_before is not None:
            params["synced_before"] = synced_before.isoformat()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre"
                "/local-items/ids",
                params=params,
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()

    async def soft_delete_items(
        self, tenant_id: str, item_ids: list[str]
    ) -> list[str]:
        """Soft delete an explicit set of local listings (idempotent)."""
        if not item_ids:
            return []
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/integrations/internal"
                "/mercadolivre/items/reconcile",
                json={"missing_item_ids": item_ids},
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json().get("deleted_item_ids", [])

    async def upsert_local_item(
        self,
        tenant_id: str,
        item_data: dict,
        event_timestamp: datetime | None = None,
    ) -> dict:
        params: dict = {}
        if event_timestamp is not None:
            params["event_timestamp"] = event_timestamp.isoformat()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre/items/local-sync",
                params=params,
                json=item_data,
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()

    async def reconcile_items(
        self,
        tenant_id: str,
        seen_item_ids: list[str],
        synced_before=None,
    ) -> list[str]:
        """Soft delete local items that are absent from the latest ML payload.

        Returns the item ids that were removed so the caller can also hide the
        matching catalog mappings.
        """
        payload: dict = {"seen_item_ids": seen_item_ids}
        if synced_before is not None:
            payload["synced_before"] = synced_before.isoformat()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/integrations/internal"
                "/mercadolivre/items/reconcile",
                json=payload,
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json().get("deleted_item_ids", [])

    async def get_item_details_batch(
        self, tenant_id: str, item_ids: list[str]
    ) -> dict[str, dict]:
        """Fetch status/permalink/has_variations for the flusher guard.

        Returns a dict keyed by item id. Raises on transport/HTTP errors so the
        flusher can keep the pending entries for a later retry.
        """
        if not item_ids:
            return {}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre"
                "/items/batch-details",
                json={"item_ids": item_ids},
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            items = response.json().get("items", [])
        return {
            item["id"]: item
            for item in items
            if isinstance(item, dict) and item.get("id")
        }

    async def update_item_quantity(self, tenant_id: str, item_id: str, quantity: int) -> None:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.put(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre"
                f"/items/{item_id}/quantity",
                json={"available_quantity": quantity},
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()


class SalesClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.sales_service_url).rstrip("/")

    async def record_order(self, payload: dict, tenant_id: str) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/orders/internal",
                json=payload,
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()
