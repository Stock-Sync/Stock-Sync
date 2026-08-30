# catalog-service

Serviço responsável pelo catálogo de produtos e pelo mapeamento de SKU entre plataformas.

## Responsabilidades

- cadastro e consulta de produtos
- relacionamento entre SKU interno e SKU do marketplace
- regras de base para sincronização de estoque
- leitura e validação de dados para os demais serviços

## Estrutura interna

```text
catalog-service/
├── app/
│   ├── api/
│   ├── core/
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

## Como executar

Use a venv única na raiz do repositório (a partir do `Stock-Sync/`):

```bash
source .venv/bin/activate
cp services/catalog-service/.env.example services/catalog-service/.env
uvicorn --app-dir services/catalog-service app.main:app --reload
```

Acesse a documentação em `http://localhost:8000/docs`.
