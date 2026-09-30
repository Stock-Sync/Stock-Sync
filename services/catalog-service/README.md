# catalog-service

Serviço responsável pelo catálogo de produtos e pelo mapeamento de SKU entre plataformas.

## Responsabilidades

- cadastro e consulta de produtos
- relacionamento entre SKU interno e SKU do marketplace (source of truth)
- regras de base para sincronização de estoque
- leitura e validação de dados para os demais serviços

## Estrutura interna

```text
catalog-service/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── mappings.py   # Marketplace-to-SKU mappings (NEW)
│   │       └── products.py   # Product & stock queries
│   ├── core/
│   ├── db/
│   ├── models/
│   │   ├── product.py        # Product model with user_id
│   │   └── mapping.py        # ProductPlatformMapping model (NEW)
│   ├── schemas/
│   │   └── mapping.py        # Pydantic schemas for mappings (NEW)
│   └── main.py
├── tests/
├── .env.example
├── Dockerfile
├── requirements.txt
└── README.md
```

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

## API Endpoints

### Mappings (Marketplace → SKU)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/mappings/by-external-id` | Get mapping by marketplace item ID |
| `POST` | `/api/v1/mappings/` | Create new marketplace-to-SKU mapping |
| `GET` | `/api/v1/mappings/` | List mappings with filters |
| `DELETE` | `/api/v1/mappings/{mapping_id}` | Deactivate a mapping (soft delete) |

#### Get Mapping by External ID

```
GET /api/v1/mappings/by-external-id?user_id={uuid}&platform=mercadolivre&external_item_id=MLB123456&external_model_id=0
```

**Response:**
```json
{
  "id": 1,
  "user_id": "tenant-uuid",
  "platform": "mercadolivre",
  "external_item_id": "MLB123456",
  "external_model_id": 0,
  "product_id": 1,
  "sku": "SKU-001",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Used by:** sync-service to resolve marketplace item_id → internal SKU

#### Create Mapping

```
POST /api/v1/mappings/
{
  "user_id": "tenant-uuid",
  "platform": "shopee",
  "external_item_id": "123456789",
  "external_model_id": 98765,
  "product_id": 1,
  "sku": "SKU-002",
  "is_active": true
}
```

**Constraints:** Unique on (platform, external_item_id, external_model_id, user_id)

### Products

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/products/by-sku` | Get product by SKU + tenant |
| `GET` | `/api/v1/products/stock/{user_id}/{sku}` | Get current stock quantity |

#### Get Product by SKU

```
GET /api/v1/products/by-sku?user_id={uuid}&sku=SKU-001
```

**Response:**
```json
{
  "id": "1",
  "user_id": "tenant-uuid",
  "sku": "SKU-001",
  "name": "Produto Exemplo",
  "description": null,
  "price": 99.90,
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### Get Stock Quantity

```
GET /api/v1/products/stock/tenant-uuid/SKU-001
```

**Response:**
```json
{
  "quantity": 42
}
```

## Database Models

### Product
- `id` (PK)
- `user_id` (tenant UUID, indexed)
- `name`, `sku` (unique per user_id)
- `price`, `stock_quantity`
- `created_at`, `updated_at`

### ProductPlatformMapping (catalog_mapping table)
- `id` (PK)
- `user_id` (tenant UUID, indexed)
- `platform` ("mercadolivre" or "shopee")
- `external_item_id` (ML item_id or Shopee item_id)
- `external_model_id` (Shopee variation, 0 for ML/no variation)
- `product_id` (FK → product.id)
- `sku` (internal SKU, denormalized for fast lookups)
- `is_active` (soft delete)
- `created_at`, `updated_at`
- **Unique constraint:** (platform, external_item_id, external_model_id, user_id)

## Integração com sync-service

O sync-service consulta o catalog-service via HTTP para:
1. Resolver `item_id` do marketplace → `sku` interno (`/mappings/by-external-id`)
2. Obter quantidade atual em estoque (`/products/stock/{user_id}/{sku}`)

## Docker

```bash
docker build -t catalog-service services/catalog-service/
docker run -p 8000:8000 --env-file services/catalog-service/.env catalog-service
```

## Variáveis de Ambiente (.env)

```env
APP_NAME=catalog-service
APP_VERSION=0.1.0
DEBUG=true
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_catalog
DB_ECHO=false
## Testes

```bash
cd services/catalog-service
pytest tests/
```
