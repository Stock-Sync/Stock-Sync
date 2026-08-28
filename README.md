# Stock Sync

Sistema de orquestração e centralização de estoque para vendedores que atuam em múltiplos marketplaces (Mercado Livre, Shopee, e futuramente outros).

## O Problema

Vendedores que operam em mais de um canal de vendas enfrentam um desafio recorrente: a falta de sincronização de estoque em tempo real entre plataformas. Isso gera dois cenários:

- **Overselling** — o produto é vendido em um canal, mas o estoque não é atualizado nos demais a tempo, resultando em venda sem estoque disponível.
- **Underselling** — para evitar overselling, o vendedor reserva/separa estoque por canal, deixando produtos parados sem vender em outros lugares.

## A Solução

O Stock Sync centraliza o estoque de todos os canais em um único lugar e sincroniza automaticamente as atualizações entre as plataformas conectadas, sempre que houver uma venda em qualquer uma delas. Além disso, apresenta um painel com dados operacionais consolidados, como vendas por canal e produtos mais vendidos.

## Funcionalidades (MVP)

- Integração com marketplaces via API oficial (Mercado Livre e Shopee)
- Sincronização de estoque em tempo real entre canais
- Dashboard de vendas consolidado
- Alertas de estoque baixo/crítico
- Mapeamento de SKU entre diferentes plataformas
- Histórico/log de auditoria de sincronizações

## Arquitetura

O sistema é construído como um conjunto de **microsserviços** em Python (FastAPI), com frontend em React (CSR). Visão geral dos serviços planejados:

- `catalog-service` — produtos e mapeamento de SKUs entre plataformas
- `sync-service` — orquestra a sincronização de estoque
- `integrations-service` — comunicação com as APIs do Mercado Livre e Shopee
- `sales-service` — métricas e dados de vendas


## Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Backend | Python + FastAPI |
| Frontend | React + TypeScript + Tailwind CSS |
| Banco de dados | PostgreSQL |
| Cache / Fila | Redis |
| Conteinerização | Docker |
| Orquestração | A decidir |
| CI/CD | GitHub Actions + Amazon ECR |

## Estrutura do Repositório

```
SyncHub/
├── backend/          # Serviço(s) backend em FastAPI
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   └── schemas/
│   └── tests/
├── requirements.txt
├── .env.example
└── README.md
```

> Estrutura em evolução — conforme os demais microsserviços forem criados, cada um passará a viver em sua própria pasta dentro de `services/`.

## Como Rodar Localmente

```bash
# Clonar o repositório
git clone <url-do-repositorio>
cd SyncHub

# Criar e ativar o ambiente virtual
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# preencher as variáveis necessárias no .env

# Rodar o servidor (a partir da pasta backend/)
cd backend
uvicorn app.main:app --reload
```

A documentação interativa da API (Swagger) fica disponível em `http://localhost:8000/docs` após subir o servidor.

## Status do Projeto

🚧 Em desenvolvimento — projeto integrador acadêmico.

## Equipe

Rafael Ryu Suzuki Furukawa - [linkedin](https://www.linkedin.com/in/rafael-ryu-15944b351/) & [github](https://github.com/RafaelRyu)

Enzo Rafael Brito - [linkedin](https://www.linkedin.com/in/enzo-rafael-brito/) & [github](https://github.com/BritoEnzo)

Gabriel Alves Freitas - [linkedin](https://www.linkedin.com/in/gabriel-alves-fr/) & [github](https://github.com/GabrielvFrei)

Thiago Farias - [linkedin](https://www.linkedin.com/in/thiago-farias-da-silva-a101a726b/) & [github](https://github.com/Thiagofs007)

Gustavo Amorim de Matos - [linkedin](https://www.linkedin.com/in/gustavo-amorim1/) & [github](https://github.com/amoras200)

