#!/bin/bash
for service in catalog-service sync-service integrations-service sales-service; do
  cd services/$service
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  cd ../..
done

# arquivo criado para ajudar na ativação dos venvs, para não precisar ativar um por um se você quiser trabalhar em todos os serviços ao mesmo tempo.
# use no terminal: chmod +x script_ativação_venvs.sh
# e depois use: source script_ativação_venvs.sh

# se perceber algum serviço novo que ainda não esteja na lista, adicione ele no for do script, e rode novamente o script para criar o venv dele.

# como ele esta instalando um ambiente virtual para cada serviço, isso pode demorar um pouco (max de 1 min (mas bem mais rapido que fazer um a um)).
# automação do amoras