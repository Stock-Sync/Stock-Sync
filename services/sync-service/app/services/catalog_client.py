"""
Cliente HTTP para o catalog-service.

Usado pelo sync-service para buscar informações de produtos/SKUs
e mapear itens de marketplace para SKUs internos.
"""

import logging
from typing import Optional

import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class CatalogProduct(BaseModel):
    """Produto retornado pelo catalog-service."""

    id: str
    user_id: str
    sku: str
    name: str
    description: Optional[str] = None
    is_active: bool = True
    created_at: str
    updated_at: str


class CatalogMapping(BaseModel):
    """Mapeamento de item de marketplace para produto do catálogo."""

    id: str
    user_id: str
    platform: str  # mercadolivre, shopee
    external_item_id: str
    external_model_id: Optional[int] = 0
    product_id: str
    sku: str
    is_active: bool = True


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

    def get_product_by_sku(self, user_id: str, sku: str) -> Optional[CatalogProduct]:
        """
        Busca produto no catálogo pelo SKU.

        Args:
            user_id: ID do tenant.
            sku: SKU do produto.

        Returns:
            Produto se encontrado, None caso contrário.
        """
        url = f"{self.base_url}/api/v1/products/by-sku"
        params = {"user_id": user_id, "sku": sku}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, headers=self._get_headers())
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return CatalogProduct(**response.json())
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Erro HTTP ao buscar produto por SKU — user_id=%s sku=%s: %s",
                user_id,
                sku,
                exc,
            )
            return None
        except Exception as exc:
            logger.error(
                "Erro inesperado ao buscar produto por SKU — user_id=%s sku=%s: %s",
                user_id,
                sku,
                exc,
            )
            return None

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
        url = f"{self.base_url}/api/v1/mappings/by-external-id"
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
                return CatalogMapping(**response.json())
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

    def get_stock_quantity(self, user_id: str, sku: str) -> Optional[int]:
        """
        Busca a quantidade atual em estoque de um SKU.

        Args:
            user_id: ID do tenant.
            sku: SKU do produto.

        Returns:
            Quantidade em estoque ou None se erro.
        """
        url = f"{self.base_url}/api/v1/stock/{user_id}/{sku}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers())
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
                return data.get("quantity")
        except Exception as exc:
            logger.error(
                "Erro ao buscar estoque — user_id=%s sku=%s: %s",
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