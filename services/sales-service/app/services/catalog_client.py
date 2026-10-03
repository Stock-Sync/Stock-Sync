"""
Cliente HTTP para o catalog-service.

Usado pelo sales-service para buscar informações de produtos/SKUs
e mapear itens de marketplace para SKUs internos.
"""

import logging
from typing import Optional
from uuid import UUID

import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class CatalogSKU(BaseModel):
    """SKU retornado pelo catalog-service."""

    id: int
    user_id: UUID
    internal_sku: str
    product_id: int
    price: Optional[float] = None
    stock_quantity: int
    created_at: str
    updated_at: str


class CatalogMapping(BaseModel):
    """Mapeamento de item de marketplace para produto do catálogo."""

    id: int
    user_id: UUID
    platform: str  # mercadolivre, shopee
    external_item_id: str
    external_model_id: int = 0
    product_id: int
    sku: str
    is_active: bool = True
    created_at: str
    updated_at: str


class CatalogClient:
    """Cliente para comunicação com o catalog-service."""

    def __init__(self) -> None:
        self.base_url = settings.catalog_service_url.rstrip("/")
        self.timeout = 10.0

    def _get_headers(self) -> dict:
        """Headers padrão para requisições."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_mapping_by_external_id(
        self, user_id: str, platform: str, external_item_id: str, external_model_id: int = 0
    ) -> Optional[CatalogMapping]:
        """
        Busca mapeamento de item de marketplace para produto do catálogo.

        Args:
            user_id: ID do tenant.
            platform: MercadoLivre ou Shopee.
            external_item_id: ID do item no marketplace.
            external_model_id: ID da variação (Shopee).

        Returns:
            Mapeamento se encontrado, None caso contrário.
        """
        url = f"{self.base_url}/api/v1/platform-mappings/by-external-id"
        params = {
            "user_id": user_id,
            "platform": platform,
            "external_item_id": external_item_id,
            "external_model_id": external_model_id,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, headers=self._get_headers())
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
                return CatalogMapping(
                    id=int(data["id"]),
                    user_id=UUID(data["user_id"]),
                    platform=data["platform"],
                    external_item_id=data["external_item_id"],
                    external_model_id=data["external_model_id"],
                    product_id=int(data["product_id"]),
                    sku=data["sku"],
                    is_active=data["is_active"],
                    created_at=data["created_at"],
                    updated_at=data["updated_at"],
                )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Erro HTTP ao buscar mapeamento — user_id=%s platform=%s item_id=%s: %s",
                user_id,
                platform,
                external_item_id,
                exc,
            )
            return None
        except Exception as exc:
            logger.error(
                "Erro inesperado ao buscar mapeamento — user_id=%s platform=%s item_id=%s: %s",
                user_id,
                platform,
                external_item_id,
                exc,
            )
            return None

    def get_sku_info(self, user_id: str, sku: str) -> Optional[CatalogSKU]:
        """
        Busca informações de um SKU no catálogo.

        Args:
            user_id: ID do tenant.
            sku: SKU interno do produto.

        Returns:
            SKU se encontrado, None caso contrário.
        """
        url = f"{self.base_url}/api/v1/stock/{user_id}/{sku}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers())
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
                # The stock endpoint only returns quantity, we need more info
                # Use by-sku endpoint for full info
                url2 = f"{self.base_url}/api/v1/products/by-sku"
                params = {"user_id": user_id, "sku": sku}
                response2 = client.get(url2, params=params, headers=self._get_headers())
                if response2.status_code == 404:
                    return None
                response2.raise_for_status()
                product_data = response2.json()
                return CatalogSKU(
                    id=int(product_data["id"]),
                    user_id=UUID(product_data["user_id"]),
                    internal_sku=product_data["sku"],
                    product_id=int(product_data["id"]),
                    price=product_data.get("price"),
                    stock_quantity=data.get("quantity", 0),
                    created_at=product_data.get("created_at", ""),
                    updated_at=product_data.get("updated_at", ""),
                )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Erro HTTP ao buscar SKU — user_id=%s sku=%s: %s",
                user_id,
                sku,
                exc,
            )
            return None
        except Exception as exc:
            logger.error(
                "Erro inesperado ao buscar SKU — user_id=%s sku=%s: %s",
                user_id,
                sku,
                exc,
            )
            return None

    def health_check(self) -> bool:
        """Verifica se o catalog-service está acessível."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/health", headers=self._get_headers())
                return response.status_code == 200
        except Exception:
            return False


# Instância singleton
catalog_client = CatalogClient()