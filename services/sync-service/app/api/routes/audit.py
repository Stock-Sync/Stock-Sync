"""
Rotas para consulta de logs de auditoria de sincronização.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlmodel import Session

from app.db.session import get_session
from app.models.sync import SyncAuditLog

router = APIRouter()


@router.get("/logs")
def list_audit_logs(
    user_id: Optional[str] = Query(None, description="Filtrar por user_id"),
    platform: Optional[str] = Query(None, description="Filtrar por plataforma"),
    event_type: Optional[str] = Query(None, description="Filtrar por tipo de evento"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    sku: Optional[str] = Query(None, description="Filtrar por SKU"),
    order_id: Optional[str] = Query(None, description="Filtrar por order_id"),
    item_id: Optional[str] = Query(None, description="Filtrar por item_id"),
    start_date: Optional[datetime] = Query(None, description="Data inicial (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Data final (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
    session: Session = Depends(get_session),
):
    """
    Lista logs de auditoria com filtros e paginação.
    """
    query = select(SyncAuditLog)

    if user_id:
        try:
            query = query.where(SyncAuditLog.user_id == uuid.UUID(user_id))
        except ValueError:
            return {"error": "user_id inválido", "items": [], "total": 0}

    if platform:
        query = query.where(SyncAuditLog.platform == platform)

    if event_type:
        query = query.where(SyncAuditLog.event_type == event_type)

    if status:
        query = query.where(SyncAuditLog.status == status)

    if sku:
        query = query.where(SyncAuditLog.sku == sku)

    if order_id:
        query = query.where(SyncAuditLog.order_id == order_id)

    if item_id:
        query = query.where(SyncAuditLog.item_id == item_id)

    if start_date:
        query = query.where(SyncAuditLog.created_at >= start_date)

    if end_date:
        query = query.where(SyncAuditLog.created_at <= end_date)

    # Total para paginação
    total = session.exec(select(func.count()).select_from(query.subquery())).one()

    # Ordenação e paginação
    query = query.order_by(SyncAuditLog.created_at.desc()).offset(offset).limit(limit)

    logs = session.exec(query).all()

    return {
        "items": [
            {
                "id": str(log.id),
                "user_id": str(log.user_id),
                "platform": log.platform,
                "event_type": log.event_type,
                "order_id": log.order_id,
                "item_id": log.item_id,
                "sku": log.sku,
                "old_quantity": log.old_quantity,
                "new_quantity": log.new_quantity,
                "status": log.status,
                "error_message": log.error_message,
                "original_event_id": log.original_event_id,
                "metadata": log.metadata,
                "created_at": log.created_at,
                "completed_at": log.completed_at,
            }
            for log in logs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/logs/{log_id}")
def get_audit_log(log_id: str, session: Session = Depends(get_session)):
    """
    Retorna detalhes de um log de auditoria específico.
    """
    try:
        log_uuid = uuid.UUID(log_id)
    except ValueError:
        return {"error": "log_id inválido"}

    log = session.get(SyncAuditLog, log_uuid)
    if not log:
        return {"error": "Log não encontrado"}

    return {
        "id": str(log.id),
        "user_id": str(log.user_id),
        "platform": log.platform,
        "event_type": log.event_type,
        "order_id": log.order_id,
        "item_id": log.item_id,
        "sku": log.sku,
        "old_quantity": log.old_quantity,
        "new_quantity": log.new_quantity,
        "status": log.status,
        "error_message": log.error_message,
        "original_event_id": log.original_event_id,
        "metadata": log.metadata,
        "created_at": log.created_at,
        "completed_at": log.completed_at,
    }


@router.get("/stats/{user_id}")
def get_audit_stats(
    user_id: str,
    platform: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_session),
):
    """
    Retorna estatísticas de sincronização para um tenant.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return {"error": "user_id inválido"}

    from datetime import timedelta
    start_date = datetime.utcnow() - timedelta(days=days)

    base_query = select(SyncAuditLog).where(
        SyncAuditLog.user_id == user_uuid,
        SyncAuditLog.created_at >= start_date,
    )
    if platform:
        base_query = base_query.where(SyncAuditLog.platform == platform)

    # Total por status
    status_counts = {}
    for status in ["pending", "published", "completed", "failed"]:
        count = session.exec(
            select(func.count()).select_from(
                base_query.where(SyncAuditLog.status == status).subquery()
            )
        ).one()
        status_counts[status] = count

    # Total por tipo de evento
    event_types = session.exec(
        select(SyncAuditLog.event_type, func.count())
        .select_from(base_query.subquery())
        .group_by(SyncAuditLog.event_type)
    ).all()
    event_type_counts = {et: c for et, c in event_types}

    # Total por plataforma
    platforms = session.exec(
        select(SyncAuditLog.platform, func.count())
        .select_from(base_query.subquery())
        .group_by(SyncAuditLog.platform)
    ).all()
    platform_counts = {p: c for p, c in platforms}

    return {
        "user_id": user_id,
        "period_days": days,
        "by_status": status_counts,
        "by_event_type": event_type_counts,
        "by_platform": platform_counts,
        "total": sum(status_counts.values()),
    }