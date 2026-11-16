"""Sync API: manual listings pull + sync status (frontend "Sincronizar")."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.api.deps import get_tenant_id, require_internal_secret
from app.core.config import settings
from app.db.session import get_session
from app.models import ListingsSyncRun, SyncEvent
from app.services.listings_sync import ListingsSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.post("/listings/pull")
async def pull_listings(
    tenant_id: str = Depends(get_tenant_id),
    session: Session = Depends(get_session),
):
    """Full pull of ML listings → local items + platform mappings."""
    service = ListingsSyncService(session, tenant_id)
    result = await service.pull()
    logger.info("listings_pull_completed", extra={"tenant_id": tenant_id, **result})
    return result


@router.post("/dead-letters/replay")
async def replay_dead_letters(
    limit: int | None = Query(default=None, ge=1, le=1000),
    _: None = Depends(require_internal_secret),
    session: Session = Depends(get_session),
):
    """Move dead-letter entries back to the main stream for another attempt.

    Operational, global route guarded by ``X-Internal-Secret``. The matching
    ``SyncEvent`` is reset to ``pending`` with a clean retry counter. Replay is
    idempotent from the consumer's point of view: if an event had already been
    processed it is ACKed without dispatching again.
    """
    from app.core.redis import get_redis
    from app.streams.consts import DEAD_STREAM_KEY, STREAM_KEY

    redis = get_redis()
    batch = limit or settings.dead_letter_replay_limit

    entries = await redis.xrange(DEAD_STREAM_KEY, count=batch)
    replayed = 0
    for entry_id, fields in entries:
        dedupe_key = fields.get("event_id")
        if dedupe_key:
            record = session.exec(
                select(SyncEvent).where(SyncEvent.dedupe_key == dedupe_key)
            ).first()
            if record is not None:
                record.status = "pending"
                record.retry_count = 0
                record.error_message = None
                record.processed_at = None
                session.add(record)
                session.commit()

        await redis.xadd(STREAM_KEY, fields)
        await redis.xdel(DEAD_STREAM_KEY, entry_id)
        replayed += 1

    logger.info("dead_letters_replayed", extra={"replayed": replayed, "limit": batch})
    return {"replayed": replayed}


@router.get("/status")
async def sync_status(
    tenant_id: str = Depends(get_tenant_id),
    session: Session = Depends(get_session),
):
    """Status of the sync pipeline (last pull, event backlog, dead letters)."""
    from app.core.redis import get_redis
    from app.streams.consts import DEAD_STREAM_KEY, PENDING_STOCK_KEY, STREAM_KEY

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
                "items_removed": len(last_run.items_removed or []),
                "items_removed_ids": last_run.items_removed or [],
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
