import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


SONAR_RESPONSE = {
    "choices": [{"message": {"content": "Jawapan daripada Sonar."}}],
    "citations": ["https://example.com/paper1", "https://example.com/paper2"],
}


def test_web_search_unavailable_when_no_key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "perplexity_api_key", "")
    from app.services.web_search_service import search_with_citations, WebSearchUnavailable
    with pytest.raises(WebSearchUnavailable):
        asyncio.run(search_with_citations("kajian literasi"))


def test_search_with_citations_mock(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "perplexity_api_key", "test-key")

    mock_response = MagicMock()
    mock_response.json.return_value = SONAR_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.services.web_search_service.httpx.AsyncClient", return_value=mock_client):
        from app.services.web_search_service import search_with_citations
        result = asyncio.run(search_with_citations("kajian literasi"))

    assert result["source_type"] == "web_search"
    assert len(result["citations"]) == 2
    assert "url" in result["citations"][0]
    assert result["citations"][0]["url"] == "https://example.com/paper1"
