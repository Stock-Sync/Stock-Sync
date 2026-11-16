"""HTTP client for the integrations-service internal API.

The catalog owns the mappings, but only integrations-service owns the Mercado
Livre credentials. Unbind (pause + zero stock) and manual re-link (update
``seller_custom_field``) therefore need a service-to-service call.

Failures are surfaced as ``APIError(503)`` so callers abort before changing
local state: a remote timeout must never leave an active listing pointing at a
soft-deleted mapping.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import APIError

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


def _headers(tenant_id: str) -> dict[str, str]:
    return {
        "X-Internal-Secret": settings.internal_service_secret,
        "X-Tenant-ID": tenant_id,
    }


def _base_url() -> str:
    return settings.integrations_service_url.rstrip("/")


async def prepare_item_unlink(tenant_id: str, item_id: str) -> dict[str, Any]:
    """Pause/zero an ML listing before the mapping is soft-deleted.

    ``closed``/``404`` are treated as "nothing left to do". Any other upstream
    failure (5xx, timeout, unexpected 4xx) raises ``APIError(503)``.
    """
    url = (
        f"{_base_url()}/api/v1/integrations/internal/mercadolivre"
        f"/items/{item_id}/unlink"
    )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, headers=_headers(tenant_id))
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "remote_unlink_failed",
            extra={
                "tenant_id": tenant_id,
                "item_id": item_id,
                "status_code": exc.response.status_code,
            },
        )
        raise APIError(
            status_code=503,
            code="remote_unlink_failed",
            message="Nao foi possivel pausar/zerar o anuncio no Mercado Livre.",
            details={
                "item_id": item_id,
                "upstream_status": exc.response.status_code,
            },
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "remote_unlink_unreachable",
            extra={"tenant_id": tenant_id, "item_id": item_id, "error": str(exc)},
        )
        raise APIError(
            status_code=503,
            code="remote_unlink_failed",
            message="Servico de integracao indisponivel; o vinculo foi mantido.",
            details={"item_id": item_id, "error": str(exc)},
        ) from exc


async def batch_item_details(
    tenant_id: str, item_ids: list[str]
) -> list[dict[str, Any]]:
    """Fetch status/permalink metadata for marketplace listings (Plan 10).

    The catalog uses it to enrich the ``409 product_has_active_listings``
    payload. Raises ``APIError(503)`` when integrations is unavailable so the
    caller can fall back to mapping-only metadata.
    """
    if not item_ids:
        return []
    url = (
        f"{_base_url()}/api/v1/integrations/internal/mercadolivre"
        "/items/batch-details"
    )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                url,
                json={"item_ids": item_ids},
                headers=_headers(tenant_id),
            )
            response.raise_for_status()
            return list(response.json().get("items", []))
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "listing_details_failed",
            extra={
                "tenant_id": tenant_id,
                "item_ids": item_ids,
                "status_code": exc.response.status_code,
            },
        )
        raise APIError(
            status_code=503,
            code="listing_details_unavailable",
            message="Nao foi possivel consultar os dados dos anuncios.",
            details={
                "item_ids": item_ids,
                "upstream_status": exc.response.status_code,
            },
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "listing_details_unreachable",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        raise APIError(
            status_code=503,
            code="listing_details_unavailable",
            message="Servico de integracao indisponivel.",
            details={"item_ids": item_ids, "error": str(exc)},
        ) from exc


async def update_seller_custom_field(
    tenant_id: str, item_id: str, seller_custom_field: str
) -> dict[str, Any]:
    """Update the ML ``seller_custom_field`` (best-effort on the caller side)."""
    url = (
        f"{_base_url()}/api/v1/integrations/internal/mercadolivre"
        f"/items/{item_id}/seller-custom-field"
    )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                url,
                json={"seller_custom_field": seller_custom_field},
                headers=_headers(tenant_id),
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "seller_custom_field_update_failed",
            extra={
                "tenant_id": tenant_id,
                "item_id": item_id,
                "status_code": exc.response.status_code,
            },
        )
        raise APIError(
            status_code=502,
            code="platform_sku_update_failed",
            message="Nao foi possivel atualizar o seller_custom_field no Mercado Livre.",
            details={
                "item_id": item_id,
                "upstream_status": exc.response.status_code,
            },
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "seller_custom_field_unreachable",
            extra={"tenant_id": tenant_id, "item_id": item_id, "error": str(exc)},
        )
        raise APIError(
            status_code=503,
            code="platform_sku_update_failed",
            message="Servico de integracao indisponivel.",
            details={"item_id": item_id, "error": str(exc)},
        ) from exc
