"""
Configuração do pytest para sync-service.
"""

import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assíncronos."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()