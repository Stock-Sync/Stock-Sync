# integrations-service

Serviço responsável pela integração com APIs externas de canais de venda.

## Responsabilidades

- consumir dados de Mercado Livre e Shopee
- mapear payloads externos para modelos internos
- publicar eventos de sincronização e resposta de API

## Estrutura

```text
integrations-service/
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
