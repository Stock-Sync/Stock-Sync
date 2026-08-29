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

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Acesse a documentação em `http://localhost:8000/docs`.
