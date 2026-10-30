"""HTTP clients for service-to-service calls (all guarded by the shared secret)."""

import logging

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
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/skus",
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            for sku in response.json():
                if sku["internal_sku"] == internal_sku:
                    return sku
        return None

    async def find_mapping_by_product_id(
        self, platform_product_id: str, tenant_id: str | None = None
    ) -> dict | None:
        """Resolve an ML item id to a platform mapping (which carries sku_id)."""
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
            mappings = response.json()
            return mappings[0] if mappings else None

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

    async def list_item_ids(self, tenant_id: str) -> list[str]:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre/items",
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json().get("item_ids", [])

    async def upsert_local_item(self, tenant_id: str, item_data: dict) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/integrations/internal/mercadolivre/items/local-sync",
                json=item_data,
                headers=_internal_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()

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

    async def record_order(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/orders/internal",
                json=payload,
                headers=_internal_headers(),
            )
            response.raise_for_status()
            return response.json()
