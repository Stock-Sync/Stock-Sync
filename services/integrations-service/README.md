# integrations-service

Serviço responsável pela integração com APIs externas de canais de venda (Mercado Livre, Shopee).

## Responsabilidades

- OAuth com Mercado Livre (troca de código por tokens, refresh automático, assinatura de webhooks)
- publicar/buscar/atualizar anúncios (`create_item_v3`, `update_item`, `sync_item_to_local`)
- receber notificações (webhooks) do Mercado Livre e encaminhá-las ao stream Redis
- expor endpoints internos (service-to-service) usados pelo sync-service

## Webhook (thin forwarder)

`POST /api/v1/integrations/webhooks/mercadolivre` recebe as notificações do ML e
apenas valida + encaminha para o Redis Streams (`stocksync:events`):

1. valida a assinatura HMAC (`X-Signature`) quando `ML_WEBHOOK_SECRET` está configurado
2. mapeia o tópico para um tipo de evento: `items` → `items_changed`, `orders`/`orders_v2` → `order_created`
3. `XADD` no stream — toda a busca de detalhes e processamento de negócio acontece no sync-service

Retorna `2xx` para a notificação ser marcada como entregue; `5xx` faz o ML reenviar depois.
A assinatura do webhook é configurada automaticamente no callback OAuth
(`/api/v1/auth/mercadolivre/callback`) via `subscribe_webhook`, usando a URL base
de `PUBLIC_API_URL`.

## Endpoints internos (`X-Internal-Secret`)

Todos exigem o header `X-Internal-Secret` (segredo compartilhado) e usam
`X-Tenant-ID` para resolver o tenant.

| Método | Rota | Descrição |
| ------ | ---- | --------- |
| `GET` | `/api/v1/integrations/internal/mercadolivre/orders/{id}` | busca pedido completo no ML |
| `GET` | `/api/v1/integrations/internal/mercadolivre/items/{id}` | busca anúncio completo |
| `GET` | `/api/v1/integrations/internal/mercadolivre/items` | lista ids de todos os anúncios do vendedor (pull manual) |
| `GET` | `/api/v1/integrations/internal/mercadolivre/items/{id}/owner` | resolve qual tenant é dono de um anúncio |
| `POST` | `/api/v1/integrations/internal/mercadolivre/items/local-sync` | upsert do anúncio na tabela local `MarketplaceItem` |
| `PUT` | `/api/v1/integrations/internal/mercadolivre/items/{id}/quantity` | atualiza só `available_quantity` (alvo do flush em lote de 3s) |
| `GET` | `/api/v1/integrations/internal/mercadolivre/credentials` | lista credenciais ML do tenant |
| `GET` | `/api/v1/integrations/internal/mercadolivre/credentials/by-ml-user/{id}` | resolve `ml_user_id` → tenant |

Rejeições 4xx do ML na atualização de quantidade (anúncio pausado/encerrado,
variação etc.) retornam `409` para o chamador descartar a atualização pendente
em vez de repetir para sempre.

## Estrutura

```text
integrations-service/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── auth.py       # OAuth ML + assinatura de webhook no callback
│   │   │   ├── internal.py   # endpoints service-to-service do sync-service
│   │   │   ├── products.py   # endpoints de anúncios para o frontend
│   │   │   └── webhooks.py   # receiver thin de notificações ML
│   │   ├── core/
│   │   │   └── redis.py      # producer do stream stocksync:events
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── main.py
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| -------- | ------ | --------- |
| `DATABASE_URL` | `postgresql+psycopg://.../stocksync_integrations` | banco do serviço |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis compartilhado (stream + caches) |
| `MERCADO_LIVRE_APP_ID` / `MERCADO_LIVRE_CLIENT_SECRET` | — | credenciais do app ML |
| `PUBLIC_API_URL` | — | URL pública da API (redirect OAuth + callback do webhook) |
| `ML_WEBHOOK_SECRET` | — | segredo HMAC do painel do app ML (opcional em dev) |
| `INTERNAL_SERVICE_SECRET` | `your-internal-service-secret-change-in-production` | segredo dos endpoints internos |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` | — | validação do JWT do auth-service |

## Testes

```bash
cd services/integrations-service
pytest tests/
```
