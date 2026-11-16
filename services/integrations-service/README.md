# integrations-service

Serviço responsável pela integração com APIs externas de canais de venda (Mercado Livre, Shopee).

## Responsabilidades

- OAuth com Mercado Livre (troca de código por tokens, refresh automático)
- publicar/buscar/atualizar anúncios (`create_item_v3`, `update_item`, `sync_item_to_local`)
- receber notificações (webhooks) do Mercado Livre e encaminhá-las ao stream Redis
- expor endpoints internos (service-to-service) usados pelo sync-service

## Webhook (thin forwarder)

`POST /api/v1/integrations/webhooks/mercadolivre/{secret}` recebe as notificações
do ML e apenas valida + encaminha para o Redis Streams (`stocksync:events`):

1. valida o segredo compartilhado embutido na própria callback URL
2. mapeia o tópico para um tipo de evento: `items` → `items_changed`, `orders`/`orders_v2` → `order_created`
3. deduplica reentregas e faz `XADD` no stream — toda a busca de detalhes e
   processamento de negócio acontece no sync-service

Retorna `2xx` para a notificação ser marcada como entregue; `5xx` faz o ML reenviar depois.

### Por que não há assinatura HMAC

O Mercado Livre **não assina** notificações de marketplace. O esquema
`x-signature: ts=...,v1=...` documentado publicamente é do **Mercado Pago**, um
produto diferente. A documentação oficial de notificações do ML (atualizada em
14/09/2026) define apenas um `POST` JSON com `resource`, `user_id`, `topic`,
`application_id`, `attempts`, `sent` e `received` — sem header de assinatura.

Como não existe assinatura, o segredo é um token compartilhado na callback URL
(`ML_WEBHOOK_SECRET`). O ML posta exatamente na URL configurada no gerenciador
de aplicações. Use apenas caracteres seguros para URL e trate a URL como
credencial (ela pode aparecer em logs de acesso). Exemplo:

```text
${PUBLIC_API_URL}/api/v1/integrations/webhooks/mercadolivre/${ML_WEBHOOK_SECRET}
```

Em produção (`DEBUG=false`), se `ML_WEBHOOK_SECRET` estiver vazio o endpoint
responde `503`: configuração ausente não pode virar endpoint aberto. Em
desenvolvimento (`DEBUG=true`) a URL sem segredo é aceita com warning para
facilitar testes locais.

### Configuração no ML

A callback URL e os tópicos (`items`, `orders_v2`) são configurados no
[gerenciador de aplicações](https://applications.mercadolibre.com/), não por API.
`api.mercadolibre.com/webhooks` retorna `404` para `GET`, `POST` e `DELETE`, então
não existe fluxo de subscribe/unsubscribe.

### Replay e deduplicação

- Não há janela de replay baseada em timestamp: `sent`/`received` não são
  autenticados e um atacante pode forjá-los. A proteção real é sempre refazer
  `GET` do recurso no ML com o token do tenant antes de aplicar qualquer mudança.
- A chave de idempotência usa `id`/`_id` quando presente. Como `orders_v2` e
  `items` normalmente não enviam id, o fallback é
  `sha256(topic:user_id:resource)`.
- A chave é usada no cache Redis (`webhook:dedupe:*`, TTL de
  `ML_WEBHOOK_DEDUP_TTL_SECONDS`) e também como `event_id` do stream. O
  sync-service persiste esse valor em `SyncEvent.dedupe_key` (único), então a
  reentrega é idempotente mesmo se duas cópias passarem pelo cache.
- Reentregas com o mesmo recurso e `sent` diferente continuam deduplicadas: o
  sync-service refaz o `GET` e aplica o estado mais recente.
- Mesmo depois do TTL do cache, um replay é inofensivo: o processamento no
  sync-service é idempotente (upsert por `order_id`/item e claims de estoque com
  lease), então repetir a mesma notificação não duplica venda nem dedução.

## OAuth do Mercado Livre (state assinado)

`GET /api/v1/auth/mercadolivre/connect` exige um access token do auth-service
(Bearer ou cookie `access_token`, `type=access`). O `/connect` gera um nonce
aleatório, assina o `state` com `JWT_SECRET_KEY` (claims `tenant_id`, `nonce`,
`aud`, `type=oauth_state`, `exp`) e grava `oauth:state:<nonce>` no Redis com TTL
`OAUTH_STATE_TTL_SECONDS` (padrão 600 s).

`GET /callback` valida assinatura, `aud`, `type` e expiração, consome o nonce
com `GETDEL` (uso único) e compara o tenant antes de trocar o código. Estado
cru, adulterado, expirado ou reutilizado retorna `401`; Redis indisponível no
connect ou no callback retorna `503`.

Limitação residual: o state não é vinculado à sessão do navegador; para isso
seria necessário um callback intermediado pelo frontend ou PKCE.

## Endpoints internos (`X-Internal-Secret`)

Todos exigem o header `X-Internal-Secret` (segredo compartilhado). As rotas com
escopo de tenant também exigem `X-Tenant-ID`; as rotas de resolução de dono
(`/items/{id}/owner` e `/credentials/by-ml-user/{id}`) são globais e usam apenas
o segredo, porque o tenant ainda não é conhecido pelo chamador.

| Método | Rota | Descrição |
| ------ | ---- | --------- |
| `GET` | `/api/v1/integrations/internal/mercadolivre/orders/{id}` | busca pedido completo no ML |
| `GET` | `/api/v1/integrations/internal/mercadolivre/items/{id}` | busca anúncio completo |
| `GET` | `/api/v1/integrations/internal/mercadolivre/items` | scroll search (`search_type=scan`) dos ids do vendedor + metadados de truncamento |
| `GET` | `/api/v1/integrations/internal/mercadolivre/local-items/ids` | ids ativos locais, separando anúncios com variações |
| `POST` | `/api/v1/integrations/internal/mercadolivre/items/reconcile` | soft delete local de um conjunto explícito de ausentes (idempotente) |
| `GET` | `/api/v1/integrations/internal/mercadolivre/items/{id}/owner` | resolve qual tenant é dono de um anúncio |
| `POST` | `/api/v1/integrations/internal/mercadolivre/items/local-sync` | upsert do anúncio na tabela local `MarketplaceItem` (descarta eventos antigos via `event_timestamp`) |
| `POST` | `/api/v1/integrations/internal/mercadolivre/items/{id}/unlink` | pausa/zera o anúncio antes do desvínculo orquestrado |
| `POST` | `/api/v1/integrations/internal/mercadolivre/items/{id}/seller-custom-field` | atualiza o `seller_custom_field` no revínculo manual |
| `PUT` | `/api/v1/integrations/internal/mercadolivre/items/{id}/quantity` | atualiza só `available_quantity` (alvo do flush em lote de 3s) |
| `GET` | `/api/v1/integrations/internal/mercadolivre/credentials` | lista credenciais ML do tenant |
| `GET` | `/api/v1/integrations/internal/mercadolivre/credentials/by-ml-user/{id}` | resolve `ml_user_id` → tenant |

Rejeições 4xx do ML na atualização de quantidade (anúncio pausado/encerrado,
variação etc.) retornam `409` para o chamador descartar a atualização pendente
em vez de repetir para sempre. Anúncios com `children`/`variations` também
retornam `409` antes de chamar o ML: a quantidade do anúncio pai nunca é
alterada pelo sistema local.

## Estrutura

```text
integrations-service/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── auth.py       # OAuth ML
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
| `ML_WEBHOOK_SECRET` | — | token compartilhado na callback URL do webhook; obrigatório quando `DEBUG=false` |
| `ML_WEBHOOK_DEDUP_TTL_SECONDS` | `3600` | TTL do cache de deduplicação de notificações |
| `OAUTH_STATE_TTL_SECONDS` | `600` | TTL do nonce assinado do OAuth (`oauth:state:<nonce>`) |
| `ML_REFRESH_LOCK_TTL_SECONDS` | `15` | TTL do lock distribuído de refresh (`lock:mercadolivre:refresh:<tenant>`) |
| `ML_REFRESH_LOCK_TIMEOUT_SECONDS` | `10` | tempo máximo de espera pelo lock antes de seguir sem ele |
| `ML_REFRESH_BUFFER_SECONDS` | `600` | janela antes da expiração em que o token é renovado |
| `INTERNAL_SERVICE_SECRET` | `your-internal-service-secret-change-in-production` | segredo dos endpoints internos |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` | — | validação do JWT do auth-service |

## Testes

```bash
cd services/integrations-service
pytest tests/
```
