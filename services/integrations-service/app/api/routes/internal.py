"""Internal service-to-service endpoints consumed by sync-service.

Guarded by ``app.api.deps``: secret-only routes use ``require_internal_secret``;
tenant-scoped routes use ``get_internal_tenant_id`` (valid secret +
``X-Tenant-ID``).
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import get_internal_tenant_id, require_internal_secret
from app.db.session import get_session
from app.models.marketplace_credential import (
    Marketplace,
    MarketplaceCredential,
    MarketplaceItem,
)
from app.services.mercadolibre import MercadoLivreService, item_has_variations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/internal", tags=["integrations-internal"])


@router.get("/mercadolivre/orders/{order_id}")
async def get_ml_order(
    order_id: str,
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Fetch full order details from Mercado Livre."""
    ml_service = MercadoLivreService(session)
    try:
        return await ml_service.get_order(tenant_id, order_id)
    except Exception as exc:
        logger.error("internal_get_order_failed", extra={"order_id": order_id, "error": str(exc)})
        raise HTTPException(status_code=502, detail=f"Failed to fetch order: {exc}") from exc


@router.get("/mercadolivre/items/{item_id}")
async def get_ml_item(
    item_id: str,
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Fetch full item details from Mercado Livre."""
    ml_service = MercadoLivreService(session)
    try:
        return await ml_service.get_item(tenant_id, item_id)
    except Exception as exc:
        logger.error("internal_get_item_failed", extra={"item_id": item_id, "error": str(exc)})
        raise HTTPException(status_code=502, detail=f"Failed to fetch item: {exc}") from exc


@router.get("/mercadolivre/items")
async def list_ml_item_ids(
    page_size: int = Query(50, ge=1, le=50),
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """List ALL item ids of the connected seller (scroll search).

    The response includes ``reported_total`` and ``truncated`` so the caller
    can abort reconciliation instead of interpreting a partial page as a mass
    deletion.
    """
    ml_service = MercadoLivreService(session)
    try:
        result = await ml_service.search_all_items_with_metadata(
            tenant_id, page_size=page_size
        )
        return {
            "item_ids": result["item_ids"],
            "total": len(result["item_ids"]),
            "reported_total": result["reported_total"],
            "truncated": result["truncated"],
        }
    except Exception as exc:
        logger.error("internal_list_items_failed", extra={"error": str(exc)})
        raise HTTPException(status_code=502, detail=f"Failed to list items: {exc}") from exc


@router.get("/mercadolivre/local-items/ids")
def list_local_item_ids(
    synced_before: datetime | None = Query(default=None),
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Return the local active mirror split into normal and variation ids."""
    ml_service = MercadoLivreService(session)
    active_item_ids, variation_item_ids = ml_service.list_local_active_items(
        tenant_id, synced_before=synced_before
    )
    return {
        "item_ids": active_item_ids,
        "variation_item_ids": variation_item_ids,
        "total": len(active_item_ids),
    }


class ListingsReconcileRequest(BaseModel):
    """Item ids returned by the last full Mercado Livre search."""

    seen_item_ids: list[str] = []
    # Explicit set computed by sync-service after the safety threshold check.
    missing_item_ids: list[str] | None = None
    # Pull start time: protects rows touched while the pull was running.
    synced_before: datetime | None = None


@router.post("/mercadolivre/items/reconcile")
def reconcile_local_items(
    payload: ListingsReconcileRequest,
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Soft delete local items that no longer exist in Mercado Livre.

    Called by sync-service after the catalog mappings were unbound. Rows are
    kept for historical orders/audit but hidden from the listings UI. When
    ``missing_item_ids`` is provided only that exact set is touched
    (idempotent retries), otherwise the legacy query-based path is used.
    """
    ml_service = MercadoLivreService(session)
    if payload.missing_item_ids is not None:
        deleted_item_ids = ml_service.soft_delete_items(
            tenant_id,
            list(dict.fromkeys(payload.missing_item_ids)),
        )
    else:
        deleted_item_ids = ml_service.soft_delete_missing_items(
            tenant_id,
            list(dict.fromkeys(payload.seen_item_ids)),
            synced_before=payload.synced_before,
        )
    logger.info(
        "listings_reconcile_completed",
        extra={
            "tenant_id": tenant_id,
            "seen": len(payload.seen_item_ids),
            "missing": len(payload.missing_item_ids or []),
            "deleted": len(deleted_item_ids),
        },
    )
    return {
        "deleted_item_ids": deleted_item_ids,
        "deleted": len(deleted_item_ids),
    }


@router.get("/mercadolivre/items/{item_id}/owner")
def get_ml_item_owner(
    item_id: str,
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """Resolve which tenant owns a locally-synced ML item."""
    item = session.exec(
        select(MarketplaceItem)
        .where(MarketplaceItem.item_id == item_id)
        .order_by(MarketplaceItem.id.asc())
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found locally")
    return {"tenant_id": item.tenant_id, "item_id": item.item_id, "sku_id": item.sku_id}


class ItemBatchDetailsRequest(BaseModel):
    """Plan 10: enrich the catalog ``409`` with listing status/permalink."""

    item_ids: list[str] = []


@router.post("/mercadolivre/items/batch-details")
def get_ml_items_batch_details(
    payload: ItemBatchDetailsRequest,
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Return local mirror metadata for a batch of listing ids.

    The response preserves the request order and includes a ``found`` flag so
    the catalog can distinguish "unknown locally" from "closed".
    """
    item_ids = list(dict.fromkeys(item_id for item_id in payload.item_ids if item_id))
    if not item_ids:
        return {"items": []}

    rows = session.exec(
        select(MarketplaceItem)
        .where(
            MarketplaceItem.tenant_id == tenant_id,
            MarketplaceItem.item_id.in_(item_ids),
        )
        .order_by(MarketplaceItem.id.desc())
    ).all()
    by_id: dict[str, MarketplaceItem] = {}
    for row in rows:
        by_id.setdefault(row.item_id, row)

    items = []
    for item_id in item_ids:
        row = by_id.get(item_id)
        if row is None:
            items.append(
                {
                    "id": item_id,
                    "status": None,
                    "permalink": None,
                    "is_active": False,
                    "is_deleted": False,
                    "available_quantity": None,
                    "has_variations": False,
                    "found": False,
                }
            )
            continue
        items.append(
            {
                "id": row.item_id,
                "status": row.status,
                "permalink": row.permalink,
                "is_active": row.is_active,
                "is_deleted": row.is_deleted,
                "available_quantity": row.available_quantity,
                "has_variations": item_has_variations(row.raw_payload),
                "found": True,
            }
        )
    return {"items": items}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.post("/mercadolivre/items/local-sync")
async def sync_item_local(
    item_data: dict,
    event_timestamp: datetime | None = Query(default=None),
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Upsert an ML item payload into the local MarketplaceItem table.

    ``event_timestamp`` (webhook ``sent``/``received``) is compared with the
    local ``updated_at``: an out-of-order event never overwrites newer state.
    The item lifecycle is mirrored into ``is_active`` and propagated to the
    catalog mapping (best-effort).
    """
    existing = session.exec(
        select(MarketplaceItem)
        .where(
            MarketplaceItem.tenant_id == tenant_id,
            MarketplaceItem.item_id == item_data.get("id"),
        )
        .order_by(MarketplaceItem.id.asc())
    ).first()
    event_ts = _as_utc(event_timestamp)
    if existing is not None and event_ts is not None:
        local_ts = _as_utc(existing.updated_at)
        if local_ts is not None and local_ts > event_ts:
            logger.info(
                "stale_item_event_discarded",
                extra={
                    "tenant_id": tenant_id,
                    "item_id": existing.item_id,
                    "event_timestamp": event_ts.isoformat(),
                    "updated_at": local_ts.isoformat(),
                },
            )
            return {
                "item_id": existing.item_id,
                "sku_id": existing.sku_id,
                "product_id": existing.product_id,
                "is_active": existing.is_active,
                "applied": False,
                "reason": "stale_event",
            }

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
    # Only webhook deliveries carry a timestamp. The periodic pull must stay
    # O(N) and not issue one extra catalog call per item.
    if event_ts is not None:
        await ml_service.sync_catalog_mapping_state(
            tenant_id,
            item.item_id,
            bool(item.is_active),
            event_timestamp=event_ts,
        )
    return {
        "item_id": item.item_id,
        "sku_id": item.sku_id,
        "product_id": item.product_id,
        "is_active": item.is_active,
        "applied": True,
    }


@router.post("/mercadolivre/items/{item_id}/unlink")
async def prepare_ml_item_unlink(
    item_id: str,
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Pause and zero an ML listing before an orchestrated local unbind."""
    ml_service = MercadoLivreService(session)
    return await ml_service.prepare_item_unlink(tenant_id, item_id)


class SellerCustomFieldRequest(BaseModel):
    seller_custom_field: str


@router.post("/mercadolivre/items/{item_id}/seller-custom-field")
async def update_ml_item_seller_custom_field(
    item_id: str,
    payload: SellerCustomFieldRequest,
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Update the ML seller SKU used by the controlled re-link flow."""
    ml_service = MercadoLivreService(session)
    result = await ml_service.update_seller_custom_field(
        tenant_id, item_id, payload.seller_custom_field
    )
    return {
        "item_id": item_id,
        "seller_custom_field": result.get(
            "seller_custom_field", payload.seller_custom_field
        ),
    }


@router.put("/mercadolivre/items/{item_id}/quantity")
async def update_ml_item_quantity(
    item_id: str,
    payload: dict,
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """Update only the available_quantity of an ML item (batch flush target)."""
    quantity = payload.get("available_quantity")
    if not isinstance(quantity, int) or quantity < 0:
        raise HTTPException(status_code=422, detail="available_quantity must be >= 0")

    # Multi-variation listings are managed exclusively in Mercado Livre's
    # Application Manager. Never touch their parent quantity, even if a stale
    # mapping still points at it.
    local_item = session.exec(
        select(MarketplaceItem).where(
            MarketplaceItem.tenant_id == tenant_id,
            MarketplaceItem.item_id == item_id,
        )
    ).first()
    if local_item is not None and item_has_variations(local_item.raw_payload):
        raise HTTPException(
            status_code=409,
            detail="ML item has variations; stock synchronization is disabled",
        )

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
    tenant_id: str = Depends(get_internal_tenant_id),
    session: Session = Depends(get_session),
):
    """List ML credentials of the tenant (used to resolve ml_user_id → tenant)."""
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
