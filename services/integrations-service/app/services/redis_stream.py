"""
Publisher de eventos e helper de idempotência usando Redis Streams.

Responsabilidades:
  - Verificar duplicidade de eventos via SETNX (idempotência)
  - Publicar eventos no stream `marketplaces:events` via XADD
  - Ler eventos do stream `stock:updates` via XREADGROUP (para o worker)
"""

import json
import logging
from functools import lru_cache

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Nome dos streams
STREAM_MARKETPLACE_EVENTS = "marketplaces:events"
STREAM_STOCK_UPDATES = "stock:updates"

# Consumer group para o worker de estoque
CONSUMER_GROUP = "integrations-consumers"


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

    O padrão de chave recomendado:
      - Webhook ML:     'webhook:ml:{topic}:{resource_id}'
      - Webhook Shopee: 'webhook:shopee:{event_code}:{shop_id}:{timestamp}'

    Args:
        key: Chave única do evento.
        ttl_seconds: TTL em segundos (padrão: 24h).

    Returns:
        True se o evento já foi processado (duplicado), False se é novo.
    """
    client = get_redis_client()
    # SETNX retorna True se a chave foi criada (evento novo), False se já existia
    is_new = client.setnx(key, "1")
    if is_new:
        client.expire(key, ttl_seconds)
        return False  # não é duplicado
    return True  # é duplicado


def publish_event(event: dict) -> str:
    """
    Publica um evento no stream `marketplaces:events` via XADD.

    O payload é serializado como JSON no campo 'data' do stream entry,
    mantendo a estrutura do Redis Streams simples (chave/valor flat).

    Args:
        event: Dicionário com os campos do evento (event_id, event_type, etc.).

    Returns:
        ID da mensagem gerado pelo Redis (ex: '1693000000000-0').
    """
    client = get_redis_client()
    message_id = client.xadd(
        STREAM_MARKETPLACE_EVENTS,
        {"data": json.dumps(event)},
        maxlen=10_000,  # mantém o stream com no máximo 10k entradas (~aproximado)
        approximate=True,
    )
    logger.info(
        "Evento publicado no stream '%s': id=%s event_type=%s",
        STREAM_MARKETPLACE_EVENTS,
        message_id,
        event.get("event_type"),
    )
    return message_id


def ensure_consumer_group() -> None:
    """
    Cria o consumer group do worker se ainda não existir.
    Deve ser chamado na inicialização do worker.
    """
    client = get_redis_client()
    try:
        client.xgroup_create(
            STREAM_STOCK_UPDATES,
            CONSUMER_GROUP,
            id="0",
            mkstream=True,  # cria o stream se não existir
        )
        logger.info("Consumer group '%s' criado.", CONSUMER_GROUP)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug("Consumer group '%s' já existe.", CONSUMER_GROUP)
        else:
            raise


def read_stock_updates(consumer_name: str, count: int = 10, block_ms: int = 5000) -> list:
    """
    Lê mensagens do stream `stock:updates` via XREADGROUP.

    Args:
        consumer_name: Nome do consumidor (ex: 'worker-1').
        count: Número máximo de mensagens por leitura.
        block_ms: Tempo de bloqueio em ms aguardando novas mensagens.

    Returns:
        Lista de tuplas (message_id, data_dict).
    """
    client = get_redis_client()
    results = client.xreadgroup(
        groupname=CONSUMER_GROUP,
        consumername=consumer_name,
        streams={STREAM_STOCK_UPDATES: ">"},
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
                logger.warning("Mensagem malformada no stream, id=%s", message_id)
    return messages


def ack_message(message_id: str) -> None:
    """
    Confirma o processamento de uma mensagem via XACK.

    Args:
        message_id: ID da mensagem retornado pelo XREADGROUP.
    """
    client = get_redis_client()
    client.xack(STREAM_STOCK_UPDATES, CONSUMER_GROUP, message_id)
    logger.debug("Mensagem confirmada (XACK): id=%s", message_id)
