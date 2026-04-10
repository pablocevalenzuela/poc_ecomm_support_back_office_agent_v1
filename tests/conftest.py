import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from langgraph.checkpoint.memory import MemorySaver

@pytest.fixture
def mock_shopify_response():
    """Fixture para simular respuestas de la API de Shopify."""
    def _create_response(data, status_code=200):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = data
        return mock
    return _create_response

@pytest.fixture
def mock_checkpointer():
    """Proporciona un checkpointer en memoria para tests de integración."""
    return MemorySaver()
