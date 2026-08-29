# sales-service

Serviço responsável por consolidar e consultar dados de vendas para dashboards e métricas operacionais.

## Responsabilidades

- leitura de métricas de vendas
- agregação por canal, produto e período
- suporte a dashboard de performance
- exposição de endpoints para business intelligence

## Estrutura

```text
sales-service/
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   └── main.py
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```
