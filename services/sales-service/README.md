# sales-service

Serviço responsável por registrar e consultar o histórico de vendas recebidas dos marketplaces.

## Responsabilidades

- persistir cada venda processada pelo sync-service (uma linha por par pedido × item)
- expor o histórico de vendas paginado para o frontend (página "Vendas")
- garantir idempotência: o sync-service pode reentregar eventos (semântica at-least-once), então a mesma tupla `(marketplace, marketplace_order_id, marketplace_item_id)` atualiza a linha existente em vez de duplicar

## Endpoints principais

| Método | Rota | Auth | Descrição |
| ------ | ---- | ---- | --------- |
| `GET` | `/api/v1/orders` | pública | histórico paginado (`page`, `limit`), mais recentes primeiro |
| `POST` | `/api/v1/orders/internal` | `X-Internal-Secret` | upsert idempotente de uma venda (chamado pelo sync-service) |

### Modelo `Order`

Além dos campos originais, a venda carrega os dados exibidos na tela de Vendas:

- `marketplace_item_id` — item do anúncio vendido (um pedido pode ter vários)
- `internal_sku` / `sku_id` — vínculo com o catálogo (nulo quando o anúncio não tem SKU mapeado; a venda é registrada mesmo assim)
- `item_title`, `thumbnail_url`, `buyer_nickname` — dados do anúncio e comprador
- `unit_price`, `total_amount`, `currency`, `status`, `ordered_at`

Restrição única: `(marketplace, marketplace_order_id, marketplace_item_id)`.

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
│   │   ├── deps.py          # require_internal_secret (guarda X-Internal-Secret)
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

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| -------- | ------ | --------- |
| `DATABASE_URL` | `postgresql+psycopg://.../stocksync_sales` | banco do serviço |
| `INTERNAL_SERVICE_SECRET` | `your-internal-service-secret-change-in-production` | segredo que guarda `/orders/internal` (compartilhado com os demais serviços) |

## Testes

```bash
cd services/sales-service
pytest tests/
```
