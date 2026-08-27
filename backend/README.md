# Backend

Estrutura inicial do backend do projeto StockSync.

## Como executar

1. Ative a venv:
   ```bash
   source .venv/bin/activate
   ```
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Rode a aplicação:
   ```bash
   uvicorn app.main:app --reload
   ```

A aplicação ficará disponível em http://127.0.0.1:8000.
