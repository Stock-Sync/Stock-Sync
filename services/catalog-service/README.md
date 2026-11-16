# catalog-service

Serviço responsável pelo catálogo de produtos e pelo mapeamento de SKU entre plataformas.

## Responsabilidades

- cadastro e consulta de produtos
- relacionamento entre SKU interno e SKU do marketplace
- estoque como fonte da verdade (`SKU.stock_quantity`)
- ajuste atômico de estoque com publicação de evento no Redis Streams
- leitura e validação de dados para os demais serviços

## Endpoints principais

| Método | Rota | Descrição |
| ------ | ---- | --------- |
| `GET` | `/api/v1/products` | lista produtos |
| `POST` | `/api/v1/products` | cria produto |
| `DELETE` | `/api/v1/products/{id}` | soft delete do produto + SKUs + desativa vínculos |
| `GET` | `/api/v1/skus` | lista SKUs |
| `POST` | `/api/v1/skus` | cria SKU (publica `stock_adjust` se houver estoque inicial) |
| `PUT` | `/api/v1/skus/{id}` | atualiza SKU (publica `stock_adjust` se o estoque mudou) |
| `DELETE` | `/api/v1/skus/{id}` | soft delete do SKU + desativa vínculos (idempotente) |
| `POST` | `/api/v1/skus/{id}/adjust` | ajuste atômico de estoque (clampa em 0 e publica `stock_adjust`) |
| `GET` | `/api/v1/platform-mappings` | lista vínculos SKU ↔ marketplace (filtros: `platform`, `platform_sku`, `platform_product_id`) |
| `POST` | `/api/v1/platform-mappings` | cria vínculo (usado pelo wizard de anúncios e pelo pull de anúncios) |
| `POST` | `/api/v1/platform-mappings/re-link` | revínculo manual controlado (reativa vínculo removido pelo usuário e tenta atualizar o `seller_custom_field`) |
| `DELETE` | `/api/v1/platform-mappings/{id}` | desvínculo orquestrado: pausa/zera no ML antes do soft delete (`deleted_reason=user`) |

### Exclusão (soft delete)

Produtos e SKUs não são removidos fisicamente. As rotas `DELETE` marcam
`is_deleted = true` e atualizam `updated_at`; ao excluir um produto, seus SKUs
também são marcados e os `PlatformMapping` vinculados ficam com
`is_active = false`.

- As listagens (`GET /products`, `GET /skus`) omitem registros excluídos.
- `GET /skus/{id}` continua retornando o SKU excluído para preservar o
  histórico de vendas e integrações.
- Atualizações, ajustes de estoque e criação de novos vínculos são bloqueados
  para SKUs excluídos; também não é possível criar SKU em produto excluído.
- `internal_sku` permanece reservado após a exclusão: tentar recriar o mesmo
  código retorna `409 Conflict`.
- Bancos existentes precisam de `alembic upgrade head` para adicionar as
  colunas `is_deleted` e seus índices.


### `POST /api/v1/skus/{id}/adjust`

Ajuste relativo de estoque (`delta` negativo deduz, positivo soma). A linha é lida
com `SELECT ... FOR UPDATE`, então `previous_quantity`, `new_quantity` e `clamped`
descrevem a mesma transição serializada: um ajuste concorrente no mesmo SKU espera
o lock e enxerga a quantidade já gravada. O estoque nunca fica negativo (clampa em
0, `clamped: true`) e o valor de `previous_quantity` é seguro para calcular a
devolução em cancelamentos.

```json
{ "delta": -3, "source": "manual" }
```

Resposta:

```json
{ "sku_id": 3, "internal_sku": "SKU-1", "previous_quantity": 10, "new_quantity": 7, "clamped": false }
```

Após o commit, o serviço publica um evento `stock_adjust` no stream
`stocksync:events` (Redis DB 0, compartilhado com sync-service e
integrations-service) para que o sync-service propague a nova quantidade aos
marketplaces. O publish é best-effort: uma indisponibilidade do Redis nunca
falha a request original.

## Autenticação e tenancy

As rotas públicas aceitam apenas o access token do auth-service
(`Authorization: Bearer` ou cookie `access_token`, com `type=access`). O
`X-Tenant-ID` isolado e o cookie legado `tenant_id` não são confiados; tokens
`refresh` são rejeitados.

As chamadas do sync-service usam o caminho interno: `X-Internal-Secret` válido
(comparação com `hmac.compare_digest`) + `X-Tenant-ID`. A presença do header de
segredo ativa o caminho interno; sem ele, um `X-Tenant-ID` isolado é ignorado e
a requisição cai na validação do JWT.

## Estrutura interna

```text
catalog-service/
├── app/
│   ├── api/
│   ├── core/
│   │   └── redis.py        # producer do stream stocksync:events
│   ├── db/
│   ├── models/
│   ├── schemas/
│   └── main.py
├── tests/
├── .env.example
├── Dockerfile
├── requirements.txt
└── README.md
```

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| -------- | ------ | --------- |
| `DATABASE_URL` | `postgresql+psycopg://.../stocksync_catalog` | banco do serviço |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis compartilhado (stream `stocksync:events`) |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` | — | validam o access token do auth-service |
| `INTERNAL_SERVICE_SECRET` | `your-internal-service-secret-change-in-production` | segredo das chamadas internas do sync-service (`X-Internal-Secret` + `X-Tenant-ID`) |
| `INTEGRATIONS_SERVICE_URL` | `http://localhost:8003` | usado no desvínculo (pausa/zeragem) e no revínculo (`seller_custom_field`) |

## Como executar

Use a venv única na raiz do repositório (a partir do `Stock-Sync/`):

```bash
source .venv/bin/activate
cp services/catalog-service/.env.example services/catalog-service/.env
# aplica as migrations (banco local em 5432)
uvicorn --app-dir services/catalog-service app.main:app --reload
```

Para rodar as migrations do serviço:

```bash
cd services/catalog-service
alembic upgrade head
# criar uma nova migração a partir dos modelos:
alembic revision --autogenerate -m "descricao da mudanca"
```

Acesse a documentação em `http://localhost:8000/docs`.

## Testes

```bash
cd services/catalog-service
pytest tests/
```
