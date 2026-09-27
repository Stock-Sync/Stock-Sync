"""
Jobs periódicos do sync-service (APScheduler).

Inclui:
  - Limpeza de logs de auditoria antigos
  - Verificação de saúde dos serviços dependentes
  - Métricas e estatísticas
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import delete, func, select
from sqlmodel import Session

from app.db.session import SessionLocal
from app.models.sync import IdempotencyKey, SyncAuditLog

logger = logging.getLogger(__name__)


def cleanup_old_audit_logs() -> None:
    """
    Remove logs de auditoria antigos (mais de 90 dias) com status completed/failed.
    Mantém logs 'pending' e 'published' para não perder rastreamento.
    """
    logger.info("Iniciando limpeza de logs de auditoria antigos...")
    cutoff_date = datetime.utcnow() - timedelta(days=90)

    with SessionLocal() as db:
        try:
            # Deleta logs completed/failed antigos
            stmt = delete(SyncAuditLog).where(
                SyncAuditLog.created_at < cutoff_date,
                SyncAuditLog.status.in_(["completed", "failed"]),
            )
            result = db.execute(stmt)
            db.commit()
            logger.info("Limpeza concluída: %d logs antigos removidos", result.rowcount)
        except Exception as exc:
            logger.error("Erro na limpeza de logs: %s", exc, exc_info=True)
            db.rollback()


def cleanup_expired_idempotency_keys() -> None:
    """
    Remove chaves de idempotência expiradas do banco.
    """
    logger.info("Iniciando limpeza de chaves de idempotência expiradas...")

    with SessionLocal() as db:
        try:
            stmt = delete(IdempotencyKey).where(IdempotencyKey.expires_at < datetime.utcnow())
            result = db.execute(stmt)
            db.commit()
            logger.info("Limpeza concluída: %d chaves expiradas removidas", result.rowcount)
        except Exception as exc:
            logger.error("Erro na limpeza de chaves: %s", exc, exc_info=True)
            db.rollback()


def log_sync_metrics() -> None:
    """
    Loga métricas de sincronização das últimas 24h.
    """
    logger.info("Coletando métricas de sincronização...")
    since = datetime.utcnow() - timedelta(hours=24)

    with SessionLocal() as db:
        try:
            # Conta por status
            status_counts = db.exec(
                select(SyncAuditLog.status, func.count())
                .where(SyncAuditLog.created_at >= since)
                .group_by(SyncAuditLog.status)
            ).all()

            # Conta por plataforma
            platform_counts = db.exec(
                select(SyncAuditLog.platform, func.count())
                .where(SyncAuditLog.created_at >= since)
                .group_by(SyncAuditLog.platform)
            ).all()

            # Conta por tipo de evento
            event_counts = db.exec(
                select(SyncAuditLog.event_type, func.count())
                .where(SyncAuditLog.created_at >= since)
                .group_by(SyncAuditLog.event_type)
            ).all()

            metrics = {
                "period": "24h",
                "by_status": dict(status_counts),
                "by_platform": dict(platform_counts),
                "by_event_type": dict(event_counts),
                "total": sum(c for _, c in status_counts),
            }
            logger.info("Métricas de sincronização (24h): %s", metrics)
        except Exception as exc:
            logger.error("Erro ao coletar métricas: %s", exc, exc_info=True)


def create_scheduler() -> BackgroundScheduler:
    """
    Cria e configura o APScheduler com os jobs periódicos.
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    # Limpeza diária às 03:00 UTC
    scheduler.add_job(
        cleanup_old_audit_logs,
        "cron",
        hour=3,
        minute=0,
        id="cleanup_audit_logs",
        replace_existing=True,
    )

    # Limpeza de chaves de idempotência a cada 6 horas
    scheduler.add_job(
        cleanup_expired_idempotency_keys,
        "cron",
        hour="*/6",
        minute=0,
        id="cleanup_idempotency_keys",
        replace_existing=True,
    )

    # Métricas a cada hora
    scheduler.add_job(
        log_sync_metrics,
        "cron",
        minute=0,
        id="log_sync_metrics",
        replace_existing=True,
    )

    return scheduler