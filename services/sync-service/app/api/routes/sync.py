"""
Rotas para operações de sincronização manual e status.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlmodel import Session

logger = logging.getLogger(__name__)

from app.db.session import get_session
from app.models.sync import SyncAuditLog, SyncState
from app.schemas.sync import (
    ManualSyncRequest,
    ManualSyncResponse,
    SyncStatusResponse,
)
from app.services.catalog_client import catalog_client
from app.services.redis_stream import publish_stock_update
from app.services.sync_engine import SyncEngine

router = APIRouter()


@router.post("/manual", response_model=ManualSyncResponse)
def manual_sync(request: ManualSyncRequest):
    """
    Dispara uma sincronização manual de estoque para um SKU específico.

    Útil para correções, setup inicial ou recuperação de falhas.
    """
    # Valida se produto existe no catálogo
    product = catalog_client.get_product_by_sku(request.user_id, request.sku)
    if not product:
        raise HTTPException(status_code=404, detail=f"Produto não encontrado: SKU={request.sku}")

    # Busca mapeamento para validar item_id
    mapping = catalog_client.get_mapping_by_external_id(
        user_id=request.user_id,
        platform=request.platform,
        external_item_id=request.item_id,
        external_model_id=request.model_id,
    )
    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Mapeamento não encontrado para item_id={request.item_id} na plataforma {request.platform}",
        )

    # Publica evento de atualização de estoque
    event_id = str(uuid.uuid4())
    stock_event = {
        "user_id": request.user_id,
        "platform": request.platform,
        "sku": request.sku,
        "item_id": request.item_id,
        "model_id": request.model_id,
        "shop_id": request.shop_id,
        "quantity": request.quantity,
        "sync_reason": "manual",
        "original_event_id": event_id,
    }

    try:
        publish_stock_update(stock_event)
        logger_info = f"Sincronização manual publicada — user_id={request.user_id} sku={request.sku} qty={request.quantity}"
        return ManualSyncResponse(
            status="accepted",
            message=logger_info,
            event_id=event_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao publicar evento: {exc}")


@router.get("/status/{user_id}", response_model=SyncStatusResponse)
def get_sync_status(
    user_id: str,
    platform: Optional[str] = Query(None, description="Filtrar por plataforma"),
    session: Session = Depends(get_session),
):
    """
    Retorna status de sincronização para um tenant.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="user_id inválido")

    # Conta sincronizações pendentes (audit logs com status pending)
    query = select(func.count(SyncAuditLog.id)).where(
        SyncAuditLog.user_id == user_uuid,
        SyncAuditLog.status == "pending",
    )
    if platform:
        query = query.where(SyncAuditLog.platform == platform)

    pending_syncs = session.exec(query).one()

    # Última sincronização concluída
    last_sync_query = (
        select(SyncAuditLog)
        .where(
            SyncAuditLog.user_id == user_uuid,
            SyncAuditLog.status.in_(["completed", "published"]),
        )
        .order_by(SyncAuditLog.completed_at.desc())
        .limit(1)
    )
    if platform:
        last_sync_query = last_sync_query.where(SyncAuditLog.platform == platform)

    last_sync = session.exec(last_sync_query).first()

    # Último erro
    last_error_query = (
        select(SyncAuditLog)
        .where(
            SyncAuditLog.user_id == user_uuid,
            SyncAuditLog.status == "failed",
        )
        .order_by(SyncAuditLog.created_at.desc())
        .limit(1)
    )
    if platform:
        last_error_query = last_error_query.where(SyncAuditLog.platform == platform)

    last_error_log = session.exec(last_error_query).first()

    return SyncStatusResponse(
        user_id=user_id,
        platform=platform or "all",
        pending_syncs=pending_syncs,
        last_sync_at=last_sync.completed_at if last_sync else None,
        last_error=last_error_log.error_message if last_error_log else None,
    )


@router.get("/state/{user_id}/{platform}/{sku}")
def get_sync_state(
    user_id: str,
    platform: str,
    sku: str,
    item_id: str = Query(..., description="ID do item no marketplace"),
    model_id: int = Query(0, description="ID da variação (Shopee)"),
    session: Session = Depends(get_session),
):
    """
    Retorna o estado de sincronização para um SKU específico.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="user_id inválido")

    state = session.exec(
        select(SyncState).where(
            SyncState.user_id == user_uuid,
            SyncState.platform == platform,
            SyncState.sku == sku,
            SyncState.item_id == item_id,
            SyncState.model_id == model_id,
        )
    ).first()

    if not state:
        raise HTTPException(status_code=404, detail="Estado de sincronização não encontrado")

    return {
        "user_id": str(state.user_id),
        "platform": state.platform,
        "sku": state.sku,
        "item_id": state.item_id,
        "model_id": state.model_id,
        "current_quantity": state.current_quantity,
        "pending_quantity": state.pending_quantity,
        "last_event_id": state.last_event_id,
        "last_event_type": state.last_event_type,
        "locked": state.locked,
        "locked_at": state.locked_at,
        "updated_at": state.updated_at,
    }


@router.post("/reprocess/{event_id}")
def reprocess_event(event_id: str, session: Session = Depends(get_session)):
    """
    Reprocessa um evento específico pelo event_id.
    Remove a chave de idempotência e republica o evento.
    """
    # Remove chave de idempotência do banco
    idempotency = session.exec(
        select(SyncAuditLog).where(SyncAuditLog.original_event_id == event_id)
    ).first()

    if not idempotency:
        raise HTTPException(status_code=404, detail="Evento não encontrado nos logs de auditoria")

    # Busca o evento original no Redis seria necessário, mas por simplicidade
    # apenas marcamos para reprocessamento
    idempotency.status = "pending"
    idempotency.error_message = None
    idempotency.completed_at = None
    session.add(idempotency)
    session.commit()

    # TODO: Em produção, buscar o evento original do Redis e republicar
    # Por enquanto, retorna sucesso indicando que foi marcado para reprocessamento

    return {
        "status": "accepted",
        "message": f"Evento {event_id} marcado para reprocessamento. O worker processará na próxima iteração.",
    }