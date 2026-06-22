import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture(autouse=True)
def mock_embedding_pool():
    """Mock embedding pool untuk semua tests — elak HuggingFace network call."""
    with patch('app.services.embedding_pool.embedding_pool.start', new_callable=AsyncMock), \
         patch('app.services.embedding_pool.embedding_pool.stop', new_callable=AsyncMock):
        yield
