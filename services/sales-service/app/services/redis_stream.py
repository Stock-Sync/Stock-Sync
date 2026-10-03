"""
Redis Streams consumer para sales-service.

Responsabilidades:
  - Consumir eventos do stream `marketplaces:events` via XREADGROUP
  - Gerenciar consumer group `sales-consumers`
  - Verificação de idempotência para deduplicação
  - Batching com BLOCK 5000ms
"""

import json
import logging
from functools import lru_cache
from typing import Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Stream names
STREAM_MARKETPLACE_EVENTS = "marketplaces:events"

# Consumer group para sales-service
SALES_CONSUMER_GROUP = "sales-consumers"


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    """Retorna instância singleton do cliente Redis."""
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )


def is_duplicate_event(key: str, ttl_seconds: int = 86400) -> bool:
    """
    Verifica idempotência de um evento usando SETNX + EXPIRE.

    Args:
        key: Chave única do evento (ex: 'sales:event:{event_id}').
        ttl_seconds: TTL em segundos (padrão: 24h).

    Returns:
        True se o evento já foi processado (duplicado), False se é novo.
    """
    client = get_redis_client()
    is_new = client.setnx(key, "1")
    if is_new:
        client.expire(key, ttl_seconds)
        return False  # não é duplicado
    return True  # é duplicado


def ensure_sales_consumer_group() -> None:
    """
    Cria o consumer group para consumir eventos do marketplace se não existir.
    Deve ser chamado na inicialização do worker.
    """
    client = get_redis_client()
    try:
        client.xgroup_create(
            STREAM_MARKETPLACE_EVENTS,
            SALES_CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        logger.info("Consumer group '%s' criado para stream '%s'.", SALES_CONSUMER_GROUP, STREAM_MARKETPLACE_EVENTS)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug("Consumer group '%s' já existe.", SALES_CONSUMER_GROUP)
        else:
            raise


def read_marketplace_events(
    consumer_name: str,
    count: int = 100,
    block_ms: int = 5000,
) -> list[tuple[str, dict]]:
    """
    Lê mensagens do stream `marketplaces:events` via XREADGROUP.

    Args:
        consumer_name: Nome do consumidor (ex: 'sales-worker-1').
        count: Número máximo de mensagens por leitura.
        block_ms: Tempo de bloqueio em ms aguardando novas mensagens (padrão: 5000ms).

    Returns:
        Lista de tuplas (message_id, data_dict).
    """
    client = get_redis_client()
    results = client.xreadgroup(
        groupname=SALES_CONSUMER_GROUP,
        consumername=consumer_name,
        streams={STREAM_MARKETPLACE_EVENTS: ">"},
        count=count,
        block=block_ms,
    )
    if not results:
        return []

    messages = []
    for _stream_name, entries in results:
        for message_id, fields in entries:
            try:
                data = json.loads(fields.get("data", "{}"))
                messages.append((message_id, data))
            except json.JSONDecodeError:
                logger.warning("Mensagem malformada no stream marketplaces:events, id=%s", message_id)
    return messages


def ack_marketplace_event(message_id: str) -> None:
    """
    Confirma o processamento de uma mensagem do stream marketplaces:events via XACK.

    Args:
        message_id: ID da mensagem retornado pelo XREADGROUP.
    """
    client = get_redis_client()
    client.xack(STREAM_MARKETPLACE_EVENTS, SALES_CONSUMER_GROUP, message_id)
    logger.debug("Mensagem confirmada (XACK) no marketplaces:events: id=%s", message_id)


def get_pending_marketplace_events(consumer_name: str, count: int = 100) -> list[tuple[str, dict]]:
    """
    Recupera mensagens pendentes (não confirmadas) para um consumidor específico.
    Útil para recuperação após restart.

    Args:
        consumer_name: Nome do consumidor.
        count: Número máximo de mensagens a recuperar.

    Returns:
        Lista de tuplas (message_id, data_dict).
    """
    client = get_redis_client()
    results = client.xreadgroup(
        groupname=SALES_CONSUMER_GROUP,
        consumername=consumer_name,
        streams={STREAM_MARKETPLACE_EVENTS: "0"},
        count=count,
    )
    if not results:
        return []

    messages = []
    for _stream_name, entries in results:
        for message_id, fields in entries:
            try:
                data = json.loads(fields.get("data", "{}"))
                messages.append((message_id, data))
            except json.JSONDecodeError:
                logger.warning("Mensagem pendente malformada, id=%s", message_id)
    return messages


def claim_pending_messages(
    consumer_name: str,
    min_idle_time_ms: int = 60000,
    count: int = 100,
) -> list[tuple[str, dict]]:
    """
    Reivindica mensagens pendentes que estão ociosas há muito tempo (outro consumidor morreu).

    Args:
        consumer_name: Nome do consumidor que vai reivindicar.
        min_idle_time_ms: Tempo mínimo ocioso em ms (padrão: 60s).
        count: Número máximo de mensagens a reivindicar.

    Returns:
        Lista de tuplas (message_id, data_dict).
    """
    client = get_redis_client()
    message_ids = client.xpending_range(
        STREAM_MARKETPLACE_EVENTS,
        SALES_CONSUMER_GROUP,
        min="-",
        max="+",
        count=count,
    )
    if not message_ids:
        return []

    # Filtra por tempo ocioso
    to_claim = [m["message_id"] for m in message_ids if m["time_since_delivered"] >= min_idle_time_ms]
    if not to_claim:
        return []

    claimed = client.xclaim(
        STREAM_MARKETPLACE_EVENTS,
        SALES_CONSUMER_GROUP,
        consumer_name,
        min_idle_time_ms,
        to_claim,
    )

    messages = []
    for message_id, fields in claimed:
        try:
            data = json.loads(fields.get("data", "{}"))
            messages.append((message_id, data))
        except json.JSONDecodeError:
            logger.warning("Mensagem reivindicada malformada, id=%s", message_id)
    return messages