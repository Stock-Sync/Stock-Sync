"""
Motor de sincronização de estoque — Core logic do sync-service.

Responsabilidades:
  - Processar eventos do marketplaces:events
  - Determinar quando o estoque deve ser sincronizado
  - Calcular nova quantidade baseada no tipo de evento
  - Publicar eventos no stock:updates
  - Gerenciar deduplicação, retries e auditoria
  - Coordenar locks para prevenir race conditions
"""

import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.sync import IdempotencyKey, SyncAuditLog, SyncState
from app.schemas.sync import MarketplaceEvent, StockUpdateEvent
from app.services.catalog_client import catalog_client
from app.services.redis_stream import (
    publish_stock_update,
    is_duplicate_sync_event,
)

logger = logging.getLogger(__name__)

# TTL para locks de sincronização (segundos)
SYNC_LOCK_TTL_SECONDS = settings.sync_lock_ttl_seconds
# TTL para chaves de idempotência no banco (dias)
IDEMPOTENCY_TTL_DAYS = settings.idempotency_ttl_days


class SyncEngine:
    """Motor principal de processamento de sincronização."""

    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db
        self._owns_session = db is None

    @contextmanager
    def _session(self):
        """Context manager para sessão de banco."""
        if self.db:
            yield self.db
        else:
            session = SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    def process_event(self, event: MarketplaceEvent) -> bool:
        """
        Processa um evento do marketplace e determina se deve sincronizar estoque.

        Returns:
            True se processado com sucesso, False se ignorado/duplicado.
        """
        # Verifica idempotência no Redis (rápido)
        idempotency_key = f"sync:event:{event.event_id}"
        if is_duplicate_sync_event(idempotency_key):
            logger.info("Evento duplicado ignorado (Redis): event_id=%s", event.event_id)
            return True  # Considera sucesso para ack a mensagem

        # Verifica idempotência no banco (persistente)
        if self._is_duplicate_in_db(event.event_id):
            logger.info("Evento duplicado ignorado (DB): event_id=%s", event.event_id)
            return True

        with self._session() as db:
            try:
                # Registra início da auditoria
                audit = self._create_audit_log(db, event, "pending")
                db.add(audit)
                db.flush()

                # Processa baseado no tipo de evento
                success = False
                if event.event_type == "order.created":
                    success = self._handle_order_created(db, event, audit)
                elif event.event_type == "order.updated":
                    success = self._handle_order_updated(db, event, audit)
                elif event.event_type == "order.cancelled":
                    success = self._handle_order_cancelled(db, event, audit)
                elif event.event_type == "item.updated":
                    success = self._handle_item_updated(db, event, audit)
                else:
                    logger.warning("Tipo de evento não suportado: %s", event.event_type)
                    self._update_audit_log(db, audit, "failed", f"Event type not supported: {event.event_type}")
                    return False

                if success:
                    self._mark_idempotency_in_db(db, event.event_id, uuid.UUID(event.user_id))
                    self._update_audit_log(db, audit, "published")
                    return True
                else:
                    self._update_audit_log(db, audit, "failed", "Failed to process event")
                    return False

            except Exception as exc:
                logger.error("Erro ao processar evento %s: %s", event.event_id, exc, exc_info=True)
                # Tenta atualizar audit log se possível
                try:
                    with self._session() as db2:
                        audit2 = db2.query(SyncAuditLog).filter_by(original_event_id=event.event_id).first()
                        if audit2:
                            self._update_audit_log(db2, audit2, "failed", str(exc))
                except Exception:
                    pass
                return False

    def _is_duplicate_in_db(self, event_id: str) -> bool:
        """Verifica se evento já foi processado no banco."""
        with self._session() as db:
            existing = db.query(IdempotencyKey).filter_by(event_id=event_id).first()
            return existing is not None

    def _mark_idempotency_in_db(self, db: Session, event_id: str, user_id: uuid.UUID) -> None:
        """Marca evento como processado no banco."""
        key = IdempotencyKey(
            key=f"event:{event_id}",
            event_id=event_id,
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(days=IDEMPOTENCY_TTL_DAYS),
        )
        db.add(key)

    def _create_audit_log(self, db: Session, event: MarketplaceEvent, status: str) -> SyncAuditLog:
        """Cria log de auditoria inicial."""
        return SyncAuditLog(
            user_id=uuid.UUID(event.user_id),
            platform=event.source,
            event_type=event.event_type,
            order_id=event.order_id,
            item_id=event.item_id,
            status=status,
            original_event_id=event.event_id,
            metadata=event.metadata,
        )

    def _update_audit_log(
        self, db: Session, audit: SyncAuditLog, status: str, error: Optional[str] = None
    ) -> None:
        """Atualiza log de auditoria."""
        audit.status = status
        if error:
            audit.error_message = error
        if status in ("completed", "failed"):
            audit.completed_at = datetime.utcnow()
        db.add(audit)

    # ── Handlers por tipo de evento ─────────────────────────────────────────────

    def _handle_order_created(
        self, db: Session, event: MarketplaceEvent, audit: SyncAuditLog
    ) -> bool:
        """
        Processa criação de pedido: decrementa estoque.
        """
        if not event.item_id:
            logger.warning("order.created sem item_id: event_id=%s", event.event_id)
            return False

        # Busca mapeamento no catalog-service
        mapping = catalog_client.get_mapping_by_external_id(
            user_id=event.user_id,
            platform=event.source,
            external_item_id=event.item_id,
        )
        if not mapping:
            logger.warning(
                "Mapeamento não encontrado para order.created — user_id=%s platform=%s item_id=%s",
                event.user_id, event.source, event.item_id,
            )
            return False

        # Busca estoque atual no catálogo
        current_qty = catalog_client.get_stock_quantity(event.user_id, mapping.sku)
        if current_qty is None:
            logger.warning("Estoque não encontrado no catálogo — user_id=%s sku=%s", event.user_id, mapping.sku)
            return False

        # Para order.created, assume que 1 unidade foi vendida
        # TODO: No futuro, buscar quantidade real do pedido via API do marketplace
        sold_qty = self._extract_sold_quantity(event, mapping)
        new_qty = max(0, current_qty - sold_qty)

        audit.sku = mapping.sku
        audit.old_quantity = current_qty
        audit.new_quantity = new_qty

        # Publica atualização de estoque
        stock_event = StockUpdateEvent(
            user_id=event.user_id,
            platform=event.source,
            sku=mapping.sku,
            item_id=event.item_id,
            model_id=mapping.external_model_id,
            shop_id=self._extract_shop_id(event),
            external_seller_id=event.external_seller_id,
            quantity=new_qty,
            sync_reason="order_created",
            original_event_id=event.event_id,
        )

        publish_stock_update(stock_event.model_dump())
        logger.info(
            "Estoque publicado para order.created — user_id=%s sku=%s qty=%d->%d",
            event.user_id, mapping.sku, current_qty, new_qty,
        )
        return True

    def _handle_order_updated(
        self, db: Session, event: MarketplaceEvent, audit: SyncAuditLog
    ) -> bool:
        """
        Processa atualização de pedido: pode ser mudança de status, cancelamento parcial, etc.
        Por segurança, força uma releitura do estoque real do marketplace.
        """
        if not event.item_id:
            logger.warning("order.updated sem item_id: event_id=%s", event.event_id)
            return False

        mapping = catalog_client.get_mapping_by_external_id(
            user_id=event.user_id,
            platform=event.source,
            external_item_id=event.item_id,
        )
        if not mapping:
            logger.warning(
                "Mapeamento não encontrado para order.updated — user_id=%s platform=%s item_id=%s",
                event.user_id, event.source, event.item_id,
            )
            return False

        current_qty = catalog_client.get_stock_quantity(event.user_id, mapping.sku)
        if current_qty is None:
            logger.warning("Estoque não encontrado — user_id=%s sku=%s", event.user_id, mapping.sku)
            return False

        # Para order.updated, republica o estoque atual (sincronização defensiva)
        # O worker do integrations-service vai chamar a API do marketplace para obter o real
        audit.sku = mapping.sku
        audit.old_quantity = current_qty
        audit.new_quantity = current_qty

        stock_event = StockUpdateEvent(
            user_id=event.user_id,
            platform=event.source,
            sku=mapping.sku,
            item_id=event.item_id,
            model_id=mapping.external_model_id,
            shop_id=self._extract_shop_id(event),
            external_seller_id=event.external_seller_id,
            quantity=current_qty,
            sync_reason="order_updated",
            original_event_id=event.event_id,
        )

        publish_stock_update(stock_event.model_dump())
        logger.info(
            "Sincronização defensiva publicada para order.updated — user_id=%s sku=%s qty=%d",
            event.user_id, mapping.sku, current_qty,
        )
        return True

    def _handle_order_cancelled(
        self, db: Session, event: MarketplaceEvent, audit: SyncAuditLog
    ) -> bool:
        """
        Processa cancelamento de pedido: incrementa estoque (devolução).
        """
        if not event.item_id:
            logger.warning("order.cancelled sem item_id: event_id=%s", event.event_id)
            return False

        mapping = catalog_client.get_mapping_by_external_id(
            user_id=event.user_id,
            platform=event.source,
            external_item_id=event.item_id,
        )
        if not mapping:
            logger.warning(
                "Mapeamento não encontrado para order.cancelled — user_id=%s platform=%s item_id=%s",
                event.user_id, event.source, event.item_id,
            )
            return False

        current_qty = catalog_client.get_stock_quantity(event.user_id, mapping.sku)
        if current_qty is None:
            logger.warning("Estoque não encontrado — user_id=%s sku=%s", event.user_id, mapping.sku)
            return False

        # Para cancelamento, assume devolução de 1 unidade
        # TODO: Buscar quantidade real do pedido cancelado
        returned_qty = self._extract_sold_quantity(event, mapping)
        new_qty = current_qty + returned_qty

        audit.sku = mapping.sku
        audit.old_quantity = current_qty
        audit.new_quantity = new_qty

        stock_event = StockUpdateEvent(
            user_id=event.user_id,
            platform=event.source,
            sku=mapping.sku,
            item_id=event.item_id,
            model_id=mapping.external_model_id,
            shop_id=self._extract_shop_id(event),
            external_seller_id=event.external_seller_id,
            quantity=new_qty,
            sync_reason="order_cancelled",
            original_event_id=event.event_id,
        )

        publish_stock_update(stock_event.model_dump())
        logger.info(
            "Estoque publicado para order.cancelled — user_id=%s sku=%s qty=%d->%d",
            event.user_id, mapping.sku, current_qty, new_qty,
        )
        return True

    def _handle_item_updated(
        self, db: Session, event: MarketplaceEvent, audit: SyncAuditLog
    ) -> bool:
        """
        Processa atualização de item/anúncio: sincroniza estoque do marketplace para o catálogo.
        """
        if not event.item_id:
            logger.warning("item.updated sem item_id: event_id=%s", event.event_id)
            return False

        mapping = catalog_client.get_mapping_by_external_id(
            user_id=event.user_id,
            platform=event.source,
            external_item_id=event.item_id,
        )
        if not mapping:
            logger.warning(
                "Mapeamento não encontrado para item.updated — user_id=%s platform=%s item_id=%s",
                event.user_id, event.source, event.item_id,
            )
            return False

        # Para item.updated, força sincronização completa (releitura do marketplace)
        current_qty = catalog_client.get_stock_quantity(event.user_id, mapping.sku)

        audit.sku = mapping.sku
        audit.old_quantity = current_qty
        audit.new_quantity = current_qty  # Será atualizado pelo worker

        stock_event = StockUpdateEvent(
            user_id=event.user_id,
            platform=event.source,
            sku=mapping.sku,
            item_id=event.item_id,
            model_id=mapping.external_model_id,
            shop_id=self._extract_shop_id(event),
            external_seller_id=event.external_seller_id,
            quantity=current_qty or 0,
            sync_reason="item_updated",
            original_event_id=event.event_id,
        )

        publish_stock_update(stock_event.model_dump())
        logger.info(
            "Sincronização publicada para item.updated — user_id=%s sku=%s",
            event.user_id, mapping.sku,
        )
        return True

    # ── Helpers ──────────────────────────────────────────────────────────────────

    def _extract_sold_quantity(self, event: MarketplaceEvent, mapping) -> int:
        """
        Extrai quantidade vendida do metadata do evento.
        Fallback para 1 se não disponível.
        """
        # Tenta extrair do metadata
        metadata = event.metadata or {}
        raw_data = metadata.get("raw_data", {})
        
        # Shopee: pode vir quantity no data
        if event.source == "shopee":
            qty = raw_data.get("quantity") or raw_data.get("item_list", [{}])[0].get("quantity")
            if qty:
                try:
                    return int(qty)
                except (ValueError, TypeError):
                    pass
        
        # Mercado Livre: pode vir no metadata
        if event.source == "mercadolivre":
            qty = metadata.get("quantity")
            if qty:
                try:
                    return int(qty)
                except (ValueError, TypeError):
                    pass
        
        return 1  # Default

    def _extract_shop_id(self, event: MarketplaceEvent) -> Optional[int]:
        """Extrai shop_id do evento (apenas Shopee)."""
        if event.source != "shopee":
            return None
        metadata = event.metadata or {}
        raw_data = metadata.get("raw_data", {})
        shop_id = raw_data.get("shop_id") or metadata.get("shop_id")
        if shop_id:
            try:
                return int(shop_id)
            except (ValueError, TypeError):
                pass
        # Tenta usar external_seller_id
        try:
            return int(event.external_seller_id)
        except (ValueError, TypeError):
            return None


def process_marketplace_event(event_data: dict) -> bool:
    """
    Função de conveniência para processar um evento (usada pelo worker).
    """
    try:
        event = MarketplaceEvent(**event_data)
    except Exception as exc:
        logger.error("Payload inválido para MarketplaceEvent: %s", exc)
        return False

    engine = SyncEngine()
    return engine.process_event(event)