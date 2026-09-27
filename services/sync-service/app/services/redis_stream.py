"""
Redis Streams consumer/publisher for sync-service.

Responsibilities:
  - Consume events from `marketplaces:events` via XREADGROUP
  - Publish stock update events to `stock:updates` via XADD
  - Manage consumer group for marketplace events
  - Idempotency checking for consumed events
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
STREAM_STOCK_UPDATES = "stock:updates"

# Consumer groups
MARKETPLACE_CONSUMER_GROUP = "sync-consumers"
STOCK_UPDATES_CONSUMER_GROUP = "integrations-consumers"  # Used by integrations-service worker


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


def is_duplicate_sync_event(key: str, ttl_seconds: int = 86400) -> bool:
    """
    Verifica idempotência de um evento de sincronização usando SETNX + EXPIRE.

    Args:
        key: Chave única do evento (ex: 'sync:event:{event_id}').
        ttl_seconds: TTL em segundos (padrão: 24h).

    Returns:
        True se o evento já foi processado (duplicado), False se é novo.
    """
    client = get_redis_client()
    is_new = client.setnx(key, "1")
    if is_new:
        client.expire(key, ttl_seconds)
        return False
    return True


def ensure_marketplace_consumer_group() -> None:
    """
    Cria o consumer group para consumir eventos do marketplace se não existir.
    Deve ser chamado na inicialização do worker.
    """
    client = get_redis_client()
    try:
        client.xgroup_create(
            STREAM_MARKETPLACE_EVENTS,
            MARKETPLACE_CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        logger.info("Consumer group '%s' criado para stream '%s'.", MARKETPLACE_CONSUMER_GROUP, STREAM_MARKETPLACE_EVENTS)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug("Consumer group '%s' já existe.", MARKETPLACE_CONSUMER_GROUP)
        else:
            raise


def read_marketplace_events(
    consumer_name: str,
    count: int = 10,
    block_ms: int = 5000,
) -> list[tuple[str, dict]]:
    """
    Lê mensagens do stream `marketplaces:events` via XREADGROUP.

    Args:
        consumer_name: Nome do consumidor (ex: 'sync-worker-1').
        count: Número máximo de mensagens por leitura.
        block_ms: Tempo de bloqueio em ms aguardando novas mensagens.

    Returns:
        Lista de tuplas (message_id, data_dict).
    """
    client = get_redis_client()
    results = client.xreadgroup(
        groupname=MARKETPLACE_CONSUMER_GROUP,
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
    client.xack(STREAM_MARKETPLACE_EVENTS, MARKETPLACE_CONSUMER_GROUP, message_id)
    logger.debug("Mensagem confirmada (XACK) no marketplaces:events: id=%s", message_id)


def publish_stock_update(event: dict) -> str:
    """
    Publica um evento de atualização de estoque no stream `stock:updates` via XADD.

    O payload é serializado como JSON no campo 'data' do stream entry.

    Args:
        event: Dicionário com os campos do evento de atualização de estoque.

    Returns:
        ID da mensagem gerado pelo Redis.
    """
    client = get_redis_client()
    message_id = client.xadd(
        STREAM_STOCK_UPDATES,
        {"data": json.dumps(event)},
        maxlen=10_000,
        approximate=True,
    )
    logger.info(
        "Evento de estoque publicado no stream '%s': id=%s sku=%s qty=%s",
        STREAM_STOCK_UPDATES,
        message_id,
        event.get("sku"),
        event.get("quantity"),
    )
    return message_id


def ensure_stock_updates_stream() -> None:
    """
    Garante que o stream stock:updates existe (cria se necessário).
    """
    client = get_redis_client()
    # XADD com ID 0-0 e maxlen=0 cria o stream se não existir
    # Usamos um entry dummy que será limpo pelo maxlen
    try:
        client.xadd(STREAM_STOCK_UPDATES, {"data": "{}"}, maxlen=1, approximate=True)
        # Remove o entry dummy
        entries = client.xrange(STREAM_STOCK_UPDATES, count=1)
        if entries:
            client.xdel(STREAM_STOCK_UPDATES, entries[0][0])
    except Exception:
        # Stream pode já existir
        pass


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
        groupname=MARKETPLACE_CONSUMER_GROUP,
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
        MARKETPLACE_CONSUMER_GROUP,
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
        MARKETPLACE_CONSUMER_GROUP,
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