# sync-service

Serviço responsável por orquestrar a sincronização de estoque e eventos entre canais.

## Responsabilidades

- determinar quando um estoque deve ser sincronizado
- consumir ou publicar eventos de sincronização
- coordenar retries, deduplicação e auditoria de sincronização

## Estrutura

```text
sync-service/
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
