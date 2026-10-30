"""Sync API: manual listings pull + sync status (frontend "Sincronizar")."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.core.config import settings
from app.db.session import get_session
from app.models import ListingsSyncRun
from app.services.listings_sync import ListingsSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


def get_tenant_id(request: Request) -> str:
    """Resolve the tenant from the auth-service JWT cookie (same contract as
    the other services' public endpoints)."""
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = jwt.decode(
                access_token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            tenant_id = payload.get("tenant_id")
            if tenant_id:
                return tenant_id
        except JWTError:
            pass
    tenant_id = request.cookies.get("tenant_id") or request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id
    raise HTTPException(status_code=401, detail="Tenant ID not found")


@router.post("/listings/pull")
async def pull_listings(
    request: Request,
    session: Session = Depends(get_session),
):
    """Full pull of ML listings → local items + platform mappings."""
    tenant_id = get_tenant_id(request)
    service = ListingsSyncService(session, tenant_id)
    result = await service.pull()
    logger.info("listings_pull_completed", extra={"tenant_id": tenant_id, **result})
    return result


@router.get("/status")
async def sync_status(
    request: Request,
    session: Session = Depends(get_session),
):
    """Status of the sync pipeline (last pull, event backlog, dead letters)."""
    from app.core.redis import get_redis
    from app.streams.consts import DEAD_STREAM_KEY, PENDING_STOCK_KEY, STREAM_KEY

    tenant_id = get_tenant_id(request)

    last_run = session.exec(
        select(ListingsSyncRun)
        .where(ListingsSyncRun.tenant_id == tenant_id)
        .order_by(ListingsSyncRun.started_at.desc())
    ).first()

    redis = get_redis()
    try:
        pending_events = await redis.xlen(STREAM_KEY)
        dead_letters = await redis.xlen(DEAD_STREAM_KEY)
        pending_quantities = await redis.hlen(PENDING_STOCK_KEY)
    except Exception:  # noqa: BLE001 - status must work even if Redis is down
        pending_events = dead_letters = pending_quantities = None

    return {
        "last_pull": (
            {
                "run_id": last_run.id,
                "status": last_run.status,
                "items_found": last_run.items_found,
                "items_upserted": last_run.items_upserted,
                "mappings_created": last_run.mappings_created,
                "started_at": last_run.started_at.isoformat(),
                "finished_at": (
                    last_run.finished_at.isoformat() if last_run.finished_at else None
                ),
                "error_summary": last_run.error_summary,
            }
            if last_run
            else None
        ),
        "stream": {
            "pending_events": pending_events,
            "pending_quantity_updates": pending_quantities,
            "dead_letters": dead_letters,
        },
    }
