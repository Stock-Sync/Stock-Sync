# sync-service

Serviço responsável por orquestrar a sincronização de estoque e eventos entre canais.

## Responsabilidades

- Determinar quando um estoque deve ser sincronizado
- Consumir eventos do stream `marketplaces:events` (publicados pelo integrations-service)
- Publicar eventos de atualização de estoque no stream `stock:updates`
- Coordenar retries, deduplicação e auditoria de sincronização
- Disponibilizar API para sincronização manual e consulta de status

## Arquitetura

```text
sync-service/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── sync.py      # Endpoints de sync manual e status
│   │       └── audit.py     # Endpoints de logs de auditoria
│   ├── core/
│   │   ├── config.py        # Configurações via Pydantic Settings
│   │   └── tasks.py         # Jobs periódicos (APScheduler)
│   ├── db/
│   │   └── session.py       # Sessão SQLAlchemy/SQLModel
│   ├── models/
│   │   └── sync.py          # Modelos SQLModel (SyncAuditLog, SyncState, IdempotencyKey)
│   ├── schemas/
│   │   └── sync.py          # Schemas Pydantic (MarketplaceEvent, StockUpdateEvent, etc.)
│   ├── services/
│   │   ├── catalog_client.py    # Cliente HTTP para catalog-service
│   │   ├── redis_stream.py      # Consumer/Producer Redis Streams
│   │   └── sync_engine.py       # Lógica core de processamento
│   ├── worker.py            # Worker background (consome marketplaces:events)
│   └── main.py              # Entry point FastAPI + lifespan
├── tests/
│   ├── conftest.py
│   └── test_sync.py
├── Dockerfile
├── requirements.txt
└── README.md
```

## Fluxo de Dados

```
Webhook (ML/Shopee)
       ↓
integrations-service (valida, deduplica, publica em marketplaces:events)
       ↓
sync-service worker (consome marketplaces:events)
       ↓
    ┌─────────────────────────────────────┐
    │ SyncEngine.process_event()          │
    │ 1. Verifica idempotência (Redis+DB) │
    │ 2. Busca mapeamento no catalog      │
    │ 3. Calcula nova quantidade          │
    │ 4. Publica em stock:updates         │
    │ 5. Registra auditoria               │
    └─────────────────────────────────────┘
       ↓
integrations-service worker (consome stock:updates)
       ↓
Chama APIs dos marketplaces (ML/Shopee) para atualizar estoque
       ↓
Atualiza banco de dados local
```

## Tipos de Evento Processados

| Evento | Ação | Descrição |
|--------|------|-----------|
| `order.created` | Decrementa | Venda realizada - reduz estoque |
| `order.updated` | Sincroniza | Atualização defensiva - republica estoque atual |
| `order.cancelled` | Incrementa | Cancelamento - devolve estoque |
| `item.updated` | Sincroniza | Mudança no anúncio - força releitura do marketplace |

## Streams Redis

### Consome: `marketplaces:events`
- Consumer group: `sync-consumers`
- Publicado por: `integrations-service` (webhooks)
- Schema: `MarketplaceEvent`

### Publica: `stock:updates`
- Consumer group: `integrations-consumers` (consumido pelo worker do integrations-service)
- Schema: `StockUpdateEvent`

## Modelos de Dados

### SyncAuditLog
Log de auditoria para rastreamento completo:
- `user_id`, `platform`, `event_type`
- `order_id`, `item_id`, `sku`
- `old_quantity`, `new_quantity`
- `status`: `pending` | `published` | `completed` | `failed`
- `error_message`, `metadata`

### SyncState
Estado de sincronização por SKU para controle de concorrência:
- `current_quantity`, `pending_quantity`
- `locked`, `locked_at` (prevenção de race conditions)
- `last_event_id`, `last_event_type`

### IdempotencyKey
Deduplicação persistente (sobrevive a restarts):
- `key`, `event_id`, `user_id`
- `processed_at`, `expires_at`

## API Endpoints

### Sincronização Manual
```
POST   /api/v1/sync/manual           # Dispara sync manual
GET    /api/v1/sync/status/{user_id} # Status de sincronização
GET    /api/v1/sync/state/...        # Estado detalhado por SKU
POST   /api/v1/sync/reprocess/{event_id} # Reprocessa evento
```

### Auditoria
```
GET    /api/v1/audit/logs            # Lista logs com filtros
GET    /api/v1/audit/logs/{log_id}   # Detalhes de um log
GET    /api/v1/audit/stats/{user_id} # Estatísticas por tenant
```

### Health Checks
```
GET    /health                       # Serviço rodando
GET    /health/db                    # PostgreSQL
GET    /health/redis                 # Redis
GET    /health/catalog               # Catalog-service
```

## Configuração (.env)

```env
APP_NAME=sync-service
APP_VERSION=0.1.0
DEBUG=true

DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_sync
DB_ECHO=false

REDIS_URL=redis://localhost:6379/0

CATALOG_SERVICE_URL=http://localhost:8001
INTEGRATIONS_SERVICE_URL=http://localhost:8003

SYNC_LOCK_TTL_SECONDS=30
IDEMPOTENCY_TTL_DAYS=7
WORKER_CONSUMER_NAME=sync-worker-1
WORKER_BATCH_SIZE=10
WORKER_BLOCK_MS=5000
```

## Execução

### Desenvolvimento
```bash
# Instala dependências
pip install -r requirements.txt

# Inicia API (com worker em background)
uvicorn app.main:app --reload --port 8002

# Ou inicia apenas o worker
python -m app.worker
```

### Docker
```bash
docker build -t sync-service .
docker run -p 8002:8000 --env-file .env sync-service
```

## Jobs Periódicos (APScheduler)

| Job | Frequência | Descrição |
|-----|------------|-----------|
| `cleanup_audit_logs` | Diário 03:00 UTC | Remove logs > 90 dias (completed/failed) |
| `cleanup_idempotency_keys` | A cada 6h | Remove chaves expiradas |
| `log_sync_metrics` | Horário | Loga métricas das últimas 24h |

## Deduplicação

Duas camadas de proteção:

1. **Redis (rápido)**: `SETNX sync:event:{event_id}` com TTL 24h
2. **PostgreSQL (persistente)**: Tabela `idempotency_keys` com TTL 7 dias

Permite reprocessamento seguro após restarts.

## Concurrency Control

- `SyncState.locked` + `locked_at` previne race conditions no mesmo SKU
- Lock TTL configurável (padrão 30s) evita deadlocks
- Worker processa mensagens sequencialmente por consumer

## Observabilidade

- Logs estruturados em JSON (configurável)
- Métricas periódicas no log (status, plataforma, tipo de evento)
- Health checks para todos os dependências
- Auditoria completa com rastreamento de event_id original