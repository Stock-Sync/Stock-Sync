# sync-service

Serviço responsável por orquestrar a sincronização de estoque e vendas entre canais via Redis Streams.

## Responsabilidades

- consumir eventos do stream `stocksync:events` (grupo `sync-service`) e processá-los com garantia at-least-once
- processar vendas do Mercado Livre: buscar o pedido completo, deduzir estoque (via endpoint atômico do catalog), gravar a venda no sales-service e enfileirar a atualização de quantidade no ML
- reagir a ajustes manuais de estoque (`stock_adjust`) atualizando os anúncios vinculados
- flusher em lote (3s) que envia a quantidade atual ao ML, colapsando múltiplas mudanças numa única chamada
- pull manual de anúncios ("Sincronizar") com auditoria (`ListingsSyncRun`)
- deduplicação, retries com dead-letter stream e auditoria (`SyncEvent`)

## Arquitetura do stream

```text
webhook ML ──► integrations-service (XADD) ──┐
                                             ├──► stocksync:events ◄── catalog-service (XADD stock_adjust)
                                             │            │
                                             │            ▼
                                             │     sync-service (XREADGROUP, consumer group)
                                             │            │
                                             │            ├─ order_created → GET pedido → ajusta estoque (catalog)
                                             │            │                  → grava venda (sales) → enfileira flush
                                             │            └─ stock_adjust  → enfileira flush pros anúncios vinculados
                                             │
                                             └─ falhas após 5 tentativas ► stocksync:dead (dead-letter)
```

- **Deduplicação**: cada evento carrega um `dedupe_key` único persistido em `SyncEvent`; entregas repetidas são ignoradas (o anúncio de pedido usa `ml_order:{order_id}:{item_id}`).
- **Retry**: entradas que falham ficam sem `XACK`; o `XAUTOCLAIM` as resgatam após o timeout de visibilidade. Após `stream_max_attempts` vão para o dead-letter stream com a `SyncEvent` marcada `failed`.
- **Flush de quantidade (3s)**: vendas e ajustes manuais não chamam a API do ML direto — gravam numa hash Redis `pending:stock` (último valor vence por item). O flusher lê o estoque **atual** local a cada ciclo, então várias mudanças na janela colapsam numa chamada com o valor final (auto-curativo).

## Endpoints

| Método | Rota | Auth | Descrição |
| ------ | ---- | ---- | --------- |
| `POST` | `/api/v1/sync/listings/pull` | JWT cookie | pull completo de anúncios ML → itens locais + vínculos |
| `GET` | `/api/v1/sync/status` | JWT cookie | última execução, backlog do stream e dead-letters |

`POST /listings/pull` busca todos os anúncios do vendedor conectado, faz upsert de
cada um no `MarketplaceItem` (integrations) e cria os vínculos
`PlatformMapping` que faltam quando o `seller_custom_field` corresponde a um SKU
interno. Registra uma linha em `ListingsSyncRun` com o resumo.

## Estrutura

```text
sync-service/
├── app/
│   ├── api/routes/sync.py     # pull manual + status
│   ├── core/
│   │   └── redis.py           # factory do cliente Redis
│   ├── models/                # SyncEvent, ListingsSyncRun, StockUpdateLog
│   ├── services/
│   │   ├── clients.py         # HTTP clients (catalog, integrations, sales)
│   │   ├── listings_sync.py   # pull manual de anúncios
│   │   └── order_processor.py # pipeline de venda + stock_adjust
│   ├── streams/
│   │   ├── consts.py          # nomes de stream/grupo/hash
│   │   └── consumer.py        # loop XREADGROUP + XAUTOCLAIM + dead-letter
│   ├── tasks/flusher.py       # flush em lote de 3s
│   └── main.py                # sobe consumer + flusher no lifespan
├── alembic/
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| -------- | ------ | --------- |
| `DATABASE_URL` | `postgresql+psycopg://.../stocksync_sync` | banco do serviço |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis compartilhado (deve ser o mesmo DB de catalog e integrations) |
| `CATALOG_SERVICE_URL` | `http://localhost:8001` | base do catalog-service |
| `INTEGRATIONS_SERVICE_URL` | `http://localhost:8003` | base do integrations-service |
| `SALES_SERVICE_URL` | `http://localhost:8004` | base do sales-service |
| `INTERNAL_SERVICE_SECRET` | `your-internal-service-secret-change-in-production` | segredo dos endpoints internos chamados |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` | — | resolve o tenant a partir do cookie JWT |
| `CONSUMER_ENABLED` / `FLUSHER_ENABLED` | `true` | sobe os workers em background |
| `FLUSHER_INTERVAL_SECONDS` | `3.0` | intervalo do flush em lote |
| `STREAM_MAX_ATTEMPTS` | `5` | tentativas antes do dead-letter |
| `STREAM_CLAIM_MIN_IDLE_MS` | `30000` | idle mínimo para `XAUTOCLAIM` resgatar entradas |

## Testes

```bash
cd services/sync-service
pytest tests/
```
