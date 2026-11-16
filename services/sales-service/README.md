# sales-service

Serviço responsável por registrar e consultar o histórico de vendas recebidas dos marketplaces.

## Responsabilidades

- persistir cada venda processada pelo sync-service (uma linha por par pedido × item, isolada por `tenant_id`)
- expor o histórico de vendas paginado para o frontend (página "Vendas"), sempre filtrado pelo tenant autenticado
- garantir idempotência: o sync-service pode reentregar eventos (semântica at-least-once), então a mesma tupla `(tenant_id, marketplace, marketplace_order_id, marketplace_item_id)` atualiza a linha existente em vez de duplicar
- registrar vendas sem SKU mapeado e vendas de variação (`is_variation=true`) sem perder histórico

## Endpoints principais

| Método | Rota | Auth | Descrição |
| ------ | ---- | ---- | --------- |
| `GET` | `/api/v1/orders` | JWT (Bearer ou cookie `access_token`, `type=access`) | histórico paginado (`page`, `limit`) do tenant, mais recentes primeiro |
| `POST` | `/api/v1/orders/internal` | `X-Internal-Secret` + `X-Tenant-ID` | upsert idempotente de uma venda (chamado pelo sync-service) |

O `X-Tenant-ID` isolado e o cookie legado `tenant_id` não são aceitos; tokens
`refresh` também são rejeitados nas rotas públicas. O upsert concorrente é
protegido pela unique constraint: em `IntegrityError` a rota faz rollback,
relê a linha vencedora e reaplica o payload (sem 500 e sem duplicata).

### Modelo `Order`

Além dos campos originais, a venda carrega os dados exibidos na tela de Vendas:

- `tenant_id` — dono da venda; toda consulta é filtrada por ele
- `marketplace_item_id` — item do anúncio vendido (um pedido pode ter vários)
- `internal_sku` / `sku_id` — vínculo com o catálogo (nulo quando o anúncio não tem SKU mapeado; a venda é registrada mesmo assim)
- `item_title`, `thumbnail_url`, `buyer_nickname` — dados do anúncio e comprador
- `unit_price`, `total_amount`, `currency`, `status`, `ordered_at`
- `is_variation` — marca vendas de variação, que não movimentam o SKU pai

Restrição única: `(tenant_id, marketplace, marketplace_order_id, marketplace_item_id)`.

### `GET /api/v1/orders`

Resposta:

```json
{
  "items": [ { "id": 1, "marketplace": "mercado_livre", "buyer_nickname": "joao", "...": "..." } ],
  "total": 1, "page": 1, "limit": 20
}
```

## Estrutura

```text
sales-service/
├── app/
│   ├── api/
│   │   ├── deps.py          # get_tenant_id + require_internal_secret
│   │   └── routes/orders.py # GET /orders + POST /orders/internal
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   └── main.py
├── alembic/
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

### Migration guard de tenancy

A migration `e4b7c2d9f1a3_guard_order_tenant_id.py` roda antes do `uvicorn`
(o entrypoint executa `alembic upgrade head`) e falha se existir qualquer linha
com `tenant_id IS NULL` ou `tenant_id = ''`. O sales-service não consegue
descobrir o tenant original de vendas antigas, então a migração não faz
backfill silencioso: a mensagem orienta resetar os dados de teste (Plano 1) ou
preencher `tenant_id` manualmente.

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| -------- | ------ | --------- |
| `DATABASE_URL` | `postgresql+psycopg://.../stocksync_sales` | banco do serviço |
| `INTERNAL_SERVICE_SECRET` | `your-internal-service-secret-change-in-production` | segredo que guarda `/orders/internal` (compartilhado com os demais serviços) |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` | — | resolvem o tenant do cookie `access_token`/`Authorization: Bearer` no `GET /orders` |

## Testes

```bash
cd services/sales-service
pytest tests/
```
