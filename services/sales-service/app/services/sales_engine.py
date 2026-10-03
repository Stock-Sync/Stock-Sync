"""
Motor de processamento de vendas — Core logic do sales-service.

Responsabilidades:
  - Processar eventos do marketplaces:events em batch
  - Parsear eventos ML/Shopee e extrair dados de pedido
  - Enriquecer com dados do catalog-service (SKU, produto)
  - Batch INSERT Orders + UPSERT SaleMetric (diário)
  - Publicar deltas de métricas para SSE
"""

import json
import logging
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.order import Order
from app.models.sale_metric import SaleMetric
from app.schemas.integration import StreamEvent
from app.services.catalog_client import catalog_client
from app.services.redis_stream import (
    ack_marketplace_event,
    claim_pending_messages,
    ensure_sales_consumer_group,
    get_pending_marketplace_events,
    is_duplicate_event,
    read_marketplace_events,
)

logger = logging.getLogger(__name__)

# TTL para chaves de idempotência no Redis (dias)
IDEMPOTENCY_TTL_DAYS = 7

# Tipos de métricas suportados
METRIC_TYPES = {
    "total_revenue": "total_amount",
    "total_orders": "count",
    "total_items_sold": "quantity",
    "sku_revenue": "total_amount",
    "sku_orders": "count",
    "sku_items_sold": "quantity",
}


class SalesEngine:
    """Motor principal de processamento de vendas."""

    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db
        self._owns_session = db is None
        # Cache de deltas de métricas para push SSE
        self._metric_deltas: dict[str, float] = defaultdict(float)

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

    def process_batch(self, events: list[tuple[str, dict]]) -> dict[str, float]:
        """
        Processa um batch de eventos do marketplace.

        Args:
            events: Lista de tuplas (message_id, event_data).

        Returns:
            Dict com deltas de métricas para push SSE.
        """
        if not events:
            return {}

        self._metric_deltas.clear()
        orders_to_insert: list[Order] = []
        metrics_upsert: dict[tuple, float] = defaultdict(float)

        for message_id, event_data in events:
            try:
                # Verifica idempotência
                idempotency_key = f"sales:event:{event_data.get('event_id', message_id)}"
                if is_duplicate_event(idempotency_key):
                    logger.debug("Evento duplicado ignorado: %s", event_data.get('event_id'))
                    continue

                event = StreamEvent(**event_data)

                # Só processa eventos de pedido
                if event.event_type not in ("order.created", "order.updated", "order.cancelled"):
                    logger.debug("Evento não é de pedido, ignorando: %s", event.event_type)
                    continue

                # Enriquece com dados do catálogo
                order_data = self._parse_order_event(event)
                if not order_data:
                    logger.warning("Não foi possível parsear evento: %s", event.event_id)
                    continue

                # Cria objeto Order
                order = Order(
                    user_id=uuid.UUID(event.user_id),
                    marketplace=event.source,
                    marketplace_order_id=order_data["marketplace_order_id"],
                    internal_sku=order_data["internal_sku"],
                    quantity=order_data["quantity"],
                    total_amount=order_data["total_amount"],
                    currency=order_data.get("currency", "BRL"),
                    status=order_data.get("status", "created"),
                    ordered_at=order_data.get("ordered_at", datetime.now(UTC)),
                )
                orders_to_insert.append(order)

                # Prepara upserts de métricas
                self._prepare_metric_upserts(
                    metrics_upsert,
                    user_id=uuid.UUID(event.user_id),
                    marketplace=event.source,
                    internal_sku=order_data["internal_sku"],
                    quantity=order_data["quantity"],
                    total_amount=order_data["total_amount"],
                    ordered_at=order_data.get("ordered_at", datetime.now(UTC)),
                )

                # Marca idempotência no Redis
                is_duplicate_event(idempotency_key)  # SETNX já foi feito, isso só garante expire

            except Exception as exc:
                logger.error("Erro ao processar evento %s: %s", message_id, exc, exc_info=True)
                continue

        # Batch insert + upsert em transação única
        if orders_to_insert:
            with self._session() as db:
                self._batch_insert_orders(db, orders_to_insert)
                self._batch_upsert_metrics(db, metrics_upsert)
                logger.info("Batch processado: %d ordens, %d métricas", len(orders_to_insert), len(metrics_upsert))

        # Converte deltas para retorno (para SSE)
        deltas = dict(self._metric_deltas)
        self._metric_deltas.clear()
        return deltas

    def _parse_order_event(self, event: StreamEvent) -> Optional[dict]:
        """
        Parseia evento de pedido (ML ou Shopee) e extrai dados relevantes.

        Returns:
            Dict com dados do pedido ou None se falhar.
        """
        metadata = event.metadata or {}
        raw_data = metadata.get("raw_data", {})

        if event.source == "mercadolivre":
            return self._parse_ml_order(event, raw_data)
        elif event.source == "shopee":
            return self._parse_shopee_order(event, raw_data)
        return None

    def _parse_ml_order(self, event: StreamEvent, raw_data: dict) -> Optional[dict]:
        """Parseia evento de pedido do Mercado Livre."""
        # ML envia resource como '/orders/123456789' no webhook
        # O item_id vem do event.item_id (se disponível) ou do raw_data
        item_id = event.item_id
        marketplace_order_id = event.order_id or raw_data.get("id")

        # Busca mapeamento no catálogo
        mapping = catalog_client.get_mapping_by_external_id(
            user_id=event.user_id,
            platform="mercadolivre",
            external_item_id=item_id,
        )

        if not mapping:
            logger.warning("Mapeamento não encontrado para ML item_id=%s user_id=%s", item_id, event.user_id)
            return None

        # Extrai quantidade e valor do raw_data
        quantity = raw_data.get("quantity", 1)
        total_amount = raw_data.get("total_amount", 0.0)

        # Se não tem total_amount, tenta calcular
        if total_amount == 0.0 and "unit_price" in raw_data:
            total_amount = raw_data["unit_price"] * quantity

        return {
            "marketplace_order_id": str(marketplace_order_id),
            "internal_sku": mapping.sku,
            "quantity": int(quantity),
            "total_amount": float(total_amount),
            "currency": "BRL",
            "status": "paid",
            "ordered_at": datetime.now(UTC),
        }

    def _parse_shopee_order(self, event: StreamEvent, raw_data: dict) -> Optional[dict]:
        """Parseia evento de pedido da Shopee."""
        item_id = event.item_id
        model_id = metadata.get("model_id", 0) if (metadata := event.metadata) else 0

        mapping = catalog_client.get_mapping_by_external_id(
            user_id=event.user_id,
            platform="shopee",
            external_item_id=item_id,
            external_model_id=model_id,
        )

        if not mapping:
            logger.warning("Mapeamento não encontrado para Shopee item_id=%s model_id=%s user_id=%s", item_id, model_id, event.user_id)
            return None

        # Shopee pode enviar lista de itens
        order_items = raw_data.get("item_list", [])
        if order_items:
            # Procura o item correspondente
            item = next((i for i in order_items if str(i.get("item_id")) == str(item_id) and int(i.get("model_id", 0)) == model_id), None)
            if item:
                quantity = item.get("quantity", 1)
                total_amount = item.get("total_price", item.get("unit_price", 0) * quantity) / 100000  # Shopee usa centésimos de centavo
            else:
                quantity = 1
                total_amount = 0.0
        else:
            quantity = raw_data.get("quantity", 1)
            total_amount = raw_data.get("total_amount", 0.0)

        return {
            "marketplace_order_id": event.order_id or str(raw_data.get("ordersn", raw_data.get("order_sn", ""))),
            "internal_sku": mapping.sku,
            "quantity": int(quantity),
            "total_amount": float(total_amount),
            "currency": "BRL",
            "status": "created",
            "ordered_at": datetime.now(UTC),
        }

    def _prepare_metric_upserts(
        self,
        metrics_upsert: dict[tuple, float],
        user_id: uuid.UUID,
        marketplace: str,
        internal_sku: str,
        quantity: int,
        total_amount: float,
        ordered_at: datetime,
    ) -> None:
        """
        Prepara upserts de métricas (globais e por SKU) para o batch.
        """
        metric_date = ordered_at.date()
        today = date.today()

        # Métricas globais (sku = NULL)
        global_key = (metric_date, marketplace, "total_revenue", user_id, None)
        metrics_upsert[global_key] += total_amount
        self._metric_deltas[f"total_revenue:{marketplace}"] += total_amount

        global_key = (metric_date, marketplace, "total_orders", user_id, None)
        metrics_upsert[global_key] += 1
        self._metric_deltas[f"total_orders:{marketplace}"] += 1

        global_key = (metric_date, marketplace, "total_items_sold", user_id, None)
        metrics_upsert[global_key] += quantity
        self._metric_deltas[f"total_items_sold:{marketplace}"] += quantity

        # Métricas por SKU
        sku_key = (metric_date, marketplace, "sku_revenue", user_id, internal_sku)
        metrics_upsert[sku_key] += total_amount
        self._metric_deltas[f"sku_revenue:{marketplace}:{internal_sku}"] += total_amount

        sku_key = (metric_date, marketplace, "sku_orders", user_id, internal_sku)
        metrics_upsert[sku_key] += 1
        self._metric_deltas[f"sku_orders:{marketplace}:{internal_sku}"] += 1

        sku_key = (metric_date, marketplace, "sku_items_sold", user_id, internal_sku)
        metrics_upsert[sku_key] += quantity
        self._metric_deltas[f"sku_items_sold:{marketplace}:{internal_sku}"] += quantity

    def _batch_insert_orders(self, db: Session, orders: list[Order]) -> None:
        """Batch insert de ordens."""
        db.add_all(orders)

    def _batch_upsert_metrics(self, db: Session, metrics_upsert: dict[tuple, float]) -> None:
        """
        Batch upsert de métricas usando INSERT ... ON CONFLICT DO UPDATE.
        """
        if not metrics_upsert:
            return

        # Prepara dados para upsert
        values = []
        for (metric_date, marketplace, metric_type, user_id, sku), value in metrics_upsert.items():
            values.append({
                "metric_date": metric_date,
                "marketplace": marketplace,
                "metric_type": metric_type,
                "user_id": user_id,
                "sku": sku,
                "value": value,
                "created_at": datetime.now(UTC),
            })

        # Usa SQLAlchemy Core para upsert
        stmt = pg_insert(SaleMetric.__table__).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["metric_date", "marketplace", "metric_type", "user_id", "sku"],
            set_={
                "value": SaleMetric.__table__.c.value + stmt.excluded.value,
                "created_at": datetime.now(UTC),
            }
        )
        db.execute(stmt)


def process_batch(events: list[tuple[str, dict]]) -> dict[str, float]:
    """
    Função de conveniência para processar um batch (usada pelo worker).
    """
    engine = SalesEngine()
    return engine.process_batch(events)


def recover_pending_events(consumer_name: str) -> dict[str, float]:
    """
    Recupera eventos pendentes de consumidores que morreram.
    """
    logger.info("Recuperando eventos pendentes...")
    pending = get_pending_marketplace_events(consumer_name)
    if pending:
        logger.info("Recuperados %d eventos pendentes", len(pending))
        return process_batch(pending)
    return {}