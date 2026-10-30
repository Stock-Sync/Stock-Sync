"""Internal service-to-service endpoints consumed by sync-service.

Guarded by the X-Internal-Secret shared secret; tenant is passed via the
X-Tenant-ID header (get_tenant_id already supports it as first priority).
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlmodel import Session, select

from app.api.routes.products import get_tenant_id
from app.core.config import settings
from app.db.session import get_session
from app.models.marketplace_credential import (
    Marketplace,
    MarketplaceCredential,
    MarketplaceItem,
)
from app.services.mercadolibre import MercadoLivreService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/internal", tags=["integrations-internal"])


def require_internal_secret(
    request: Request,
    x_internal_secret: str | None = Header(default=None),
) -> None:
    if not x_internal_secret or x_internal_secret != settings.internal_service_secret:
        raise HTTPException(status_code=401, detail="Invalid internal service secret")


@router.get("/mercadolivre/orders/{order_id}")
async def get_ml_order(
    order_id: str,
    request: Request,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """Fetch full order details from Mercado Livre."""
    tenant_id = get_tenant_id(request)
    ml_service = MercadoLivreService(session)
    try:
        return await ml_service.get_order(tenant_id, order_id)
    except Exception as exc:
        logger.error("internal_get_order_failed", extra={"order_id": order_id, "error": str(exc)})
        raise HTTPException(status_code=502, detail=f"Failed to fetch order: {exc}") from exc


@router.get("/mercadolivre/items/{item_id}")
async def get_ml_item(
    item_id: str,
    request: Request,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """Fetch full item details from Mercado Livre."""
    tenant_id = get_tenant_id(request)
    ml_service = MercadoLivreService(session)
    try:
        return await ml_service.get_item(tenant_id, item_id)
    except Exception as exc:
        logger.error("internal_get_item_failed", extra={"item_id": item_id, "error": str(exc)})
        raise HTTPException(status_code=502, detail=f"Failed to fetch item: {exc}") from exc


@router.get("/mercadolivre/items")
async def list_ml_item_ids(
    request: Request,
    page_size: int = Query(50, ge=1, le=50),
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """List ALL item ids of the connected seller (for the manual pull sync)."""
    tenant_id = get_tenant_id(request)
    ml_service = MercadoLivreService(session)
    try:
        item_ids = await ml_service.search_all_items(tenant_id, page_size=page_size)
        return {"item_ids": item_ids, "total": len(item_ids)}
    except Exception as exc:
        logger.error("internal_list_items_failed", extra={"error": str(exc)})
        raise HTTPException(status_code=502, detail=f"Failed to list items: {exc}") from exc


@router.get("/mercadolivre/items/{item_id}/owner")
def get_ml_item_owner(
    item_id: str,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """Resolve which tenant owns a locally-synced ML item."""
    item = session.exec(
        select(MarketplaceItem).where(MarketplaceItem.item_id == item_id)
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found locally")
    return {"tenant_id": item.tenant_id, "item_id": item.item_id, "sku_id": item.sku_id}


@router.post("/mercadolivre/items/local-sync")
async def sync_item_local(
    request: Request,
    item_data: dict,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """Upsert an ML item payload into the local MarketplaceItem table."""
    tenant_id = get_tenant_id(request)
    ml_user_id = item_data.get("seller_id")
    if not ml_user_id:
        credential = session.exec(
            select(MarketplaceCredential).where(
                MarketplaceCredential.tenant_id == tenant_id,
                MarketplaceCredential.marketplace == Marketplace.mercadolivre,
                MarketplaceCredential.is_active == True,  # noqa: E712
            )
        ).first()
        ml_user_id = credential.ml_user_id if credential else 0

    ml_service = MercadoLivreService(session)
    item = ml_service.sync_item_to_local(tenant_id, dict(item_data), ml_user_id)
    return {"item_id": item.item_id, "sku_id": item.sku_id, "product_id": item.product_id}


@router.put("/mercadolivre/items/{item_id}/quantity")
async def update_ml_item_quantity(
    item_id: str,
    payload: dict,
    request: Request,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """Update only the available_quantity of an ML item (batch flush target)."""
    quantity = payload.get("available_quantity")
    if not isinstance(quantity, int) or quantity < 0:
        raise HTTPException(status_code=422, detail="available_quantity must be >= 0")

    tenant_id = get_tenant_id(request)
    ml_service = MercadoLivreService(session)
    try:
        result = await ml_service.update_item(
            tenant_id, item_id, {"available_quantity": quantity}
        )
        return {
            "item_id": item_id,
            "available_quantity": result.get("available_quantity", quantity),
        }
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning(
            "internal_update_quantity_failed",
            extra={
                "item_id": item_id,
                "quantity": quantity,
                "error": str(exc),
                "upstream_status": status,
            },
        )
        # 4xx (paused/closed item, variation-only item, etc.) → 409 so the
        # caller drops the pending update instead of retrying forever.
        if status is not None and 400 <= status < 500:
            raise HTTPException(
                status_code=409, detail=f"ML rejected quantity update: {exc}"
            ) from exc
        raise HTTPException(status_code=502, detail=f"Failed to update quantity: {exc}") from exc


@router.get("/mercadolivre/credentials")
def list_credentials_internal(
    request: Request,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """List ML credentials of the tenant (used to resolve ml_user_id → tenant)."""
    tenant_id = get_tenant_id(request)
    credentials = session.exec(
        select(MarketplaceCredential).where(
            MarketplaceCredential.tenant_id == tenant_id,
            MarketplaceCredential.marketplace == Marketplace.mercadolivre,
        )
    ).all()
    return [
        {
            "id": c.id,
            "ml_user_id": c.ml_user_id,
            "ml_nickname": c.ml_nickname,
            "is_active": c.is_active,
        }
        for c in credentials
    ]


@router.get("/mercadolivre/credentials/by-ml-user/{ml_user_id}")
def get_credential_by_ml_user(
    ml_user_id: int,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """Resolve an ML seller id to the tenant that connected it."""
    credential = session.exec(
        select(MarketplaceCredential).where(
            MarketplaceCredential.ml_user_id == ml_user_id,
            MarketplaceCredential.marketplace == Marketplace.mercadolivre,
            MarketplaceCredential.is_active == True,  # noqa: E712
        )
    ).first()
    if credential is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {
        "tenant_id": credential.tenant_id,
        "ml_user_id": credential.ml_user_id,
        "ml_nickname": credential.ml_nickname,
    }
