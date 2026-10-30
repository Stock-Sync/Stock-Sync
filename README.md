# Stock Sync

Sistema de orquestração e centralização de estoque para vendedores que operam em múltiplos marketplaces.

## Objetivo do projeto

O Stock Sync centraliza o controle de estoque, SKU e métricas de vendas entre canais e marketplaces, permitindo decisões operacionais com menos risco de overselling e com uma visão consolidada do negócio.

Vendedores que operam em mais de um canal de vendas geralmente enfrentam dois problemas recorrentes: overselling, quando uma venda é feita sem estoque disponível em outros canais, e underselling, quando o estoque é mantido excessivamente reservado e impede vendas em outros marketplaces. O projeto nasceu para reduzir esse ruído operacional e dar uma visão unificada do estoque e da performance comercial.

## Arquitetura proposta

O backend foi organizado em um monorepo de microsserviços, com uma pasta por serviço. Esse modelo reduz acoplamento, permite evolução independente de cada domínio e facilita a adoção de regras de negócio separadas por contexto.

### Serviços do MVP

- `catalog-service` — catálogo de produtos, SKU e mapeamento entre plataformas; estoque é a fonte da verdade e todo ajuste publica um evento `stock_adjust` no stream
- `sync-service` — consome o stream Redis Streams, processa vendas do ML (deduz estoque, grava a venda) e faz o flush em lote (3s) da quantidade ao marketplace
- `integrations-service` — integrações com Mercado Livre e Shopee via API, OAuth, webhook receiver (thin forwarder para o stream) e endpoints internos para o sync-service
- `sales-service` — persiste o histórico de vendas (uma linha por pedido × item) e o expõe para a tela "Vendas"

### Estratégia de comunicação

A comunicação entre serviços segue um modelo híbrido:

- HTTP para operações síncronas e validadores de dados entre serviços (endpoints internos protegidos por `X-Internal-Secret`)
- Redis Streams para o fluxo de sincronização de estoque e vendas

Fluxo de uma venda no Mercado Livre:

```text
webhook ML ─► integrations (valida + XADD) ─► stocksync:events ◄─ catalog (XADD stock_adjust)
                                                  │
                                                  ▼
                                     sync-service (consumer group)
                                        ├─ order_created: busca pedido → deduz estoque (catalog, atômico)
                                        │                 → grava venda (sales) → enfileira flush
                                        └─ stock_adjust: enfileira flush pros anúncios vinculados
                                                  │
                                                  ▼
                              flusher 3s: lê estoque atual local → PUT available_quantity no ML
```

- `catalog-service` precisa responder rapidamente a consultas de produtos e SKU
- `sync-service` consome eventos com garantia at-least-once (dedupe por `dedupe_key`, retries via `XAUTOCLAIM`, dead-letter stream após 5 falhas)
- `integrations-service` recebe as notificações do ML e apenas valida + encaminha ao stream; a busca de detalhes acontece sob demanda no sync-service

### Estrutura do monorepo

```text
StockSync1/
├── services/
│   ├── catalog-service/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── core/
│   │   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── README.md
│   ├── sync-service/
│   │   ├── app/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── README.md
│   ├── integrations-service/
│   │   ├── app/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── README.md
│   └── sales-service/
│       ├── app/
│       ├── tests/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── README.md
├── README.md
├── docker-compose.yml
└── .env.example
```

## Padrão interno de cada serviço

Todos os serviços devem seguir a mesma base interna para manter consistência de manutenção:

- `app/api` — rotas e endpoints
- `app/core` — configuração, env vars e utilidades compartilhadas
- `app/db` — conexão com banco e session management
- `app/models` — modelos ORM / entidades do domínio
- `app/schemas` — DTOs, validação e serialização de entrada/saída
- `tests` — testes unitários e de integração do serviço

Esse padrão reduz a curva de aprendizado e permite a criação de novos serviços com o mesmo desenho sem reescrever a base da solução.

## Stack tecnológica

| Camada | Tecnologia |
|---|---|
| Backend | Python + FastAPI |
| Frontend | React + TypeScript + Tailwind CSS |
| Banco de dados | PostgreSQL |
| Cache / fila | Redis |
| Conteinerização | Docker |
| Orquestração local | Docker Compose |
| CI/CD | GitHub Actions |

## Serviço inicial

A pasta atual de backend foi migrada para `services/catalog-service/` para representar o ponto de partida mais natural do MVP, já que o catálogo é o domínio base que alimenta SKU, estoque e sincronização entre canais.

## Como rodar localmente

Para o MVP, você pode subir tudo junto via Docker Compose na raiz do repositório:

```bash
docker compose up --build
```

> **Atenção:** o serviço `postgres` do Compose mapeia a porta `5433:5432` para não conflitar com um Postgres local já em execução na 5432.

Para rodar um serviço isoladamente, use uma única venv na raiz do repositório (os serviços compartilham a mesma stack):

```bash
python -m venv .venv
source .venv/bin/activate
for s in catalog-service sync-service integrations-service sales-service; do
  pip install -r services/$s/requirements.txt
done

# inicializa um serviço (a partir da raiz do repo)
uvicorn --app-dir services/catalog-service app.main:app --reload
```

A API do catálogo estará disponível em `http://localhost:8000/docs`.

O `catalog-service` precisa de variáveis de ambiente para conectar no banco — crie um `.env` a partir do `.env.example` do serviço. Os demais serviços seguem a mesma convenção de estrutura, trocando apenas o `--app-dir` em `services/<serviço>`.

### Migrations (Alembic)

Cada serviço possui seu próprio Alembic (aponta para o banco dedicado do serviço). Para criar uma migração nova a partir dos modelos:

```bash
source .venv/bin/activate
cd services/catalog-service
DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_catalog" \
  alembic revision --autogenerate -m "descricao da mudanca"
alembic upgrade head
```

Nos containers, o `alembic upgrade head` roda automaticamente antes do `uvicorn` (ver `Dockerfile`).

## Status do projeto

🚀 Em desenvolvimento ativo — sincronização de anúncios e vendas com o Mercado Livre implementada:

- **Anúncios**: publicação automática a partir do programa (wizard) e pull manual completo ("Sincronizar") com auditoria em `ListingsSyncRun`
- **Vendas**: webhook do ML → Redis Streams → `sync-service` deduz estoque (endpoint atômico no catalog) e grava a venda no `sales-service`, com dedupe, retries e dead-letter
- **Estoque**: mudanças manuais e de venda passam pelo stream; o flusher em lote (3s) envia a quantidade final ao ML, colapsando múltiplas mudanças numa chamada
- **Frontend**: página "Vendas" no menu lateral (SKU, estoque, preço, quantidade, foto, comprador, data) e botão "Sincronizar" ligado ao sync-service

## Equipe

Rafael Ryu Suzuki Furukawa - [linkedin](https://www.linkedin.com/in/rafael-ryu-15944b351/) & [github](https://github.com/RafaelRyu)

Enzo Rafael Brito - [linkedin](https://www.linkedin.com/in/enzo-rafael-brito/) & [github](https://github.com/BritoEnzo)

Gabriel Alves Freitas - [linkedin](https://www.linkedin.com/in/gabriel-alves-fr/) & [github](https://github.com/GabrielvFrei)

Thiago Farias - [linkedin](https://www.linkedin.com/in/thiago-farias-da-silva-a101a726b/) & [github](https://github.com/Thiagofs007)

Gustavo Amorim de Matos - [linkedin](https://www.linkedin.com/in/gustavo-amorim1/) & [github](https://github.com/amoras200)

