import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import MagicMock, patch
from app.services.llm_provider import query_llm
from app.config import settings


def _make_fake_post(captured: dict):
    """Return an async fake httpx.AsyncClient.post that records the model."""
    async def fake_post(self, url, *, headers, json, **kwargs):
        captured["model"] = json["model"]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "choices": [{"message": {"content": "jawapan ujian"}}],
            "usage": {"total_tokens": 50},
        })
        return mock_resp
    return fake_post


@pytest.mark.asyncio
async def test_flash_used_for_normal_qa():
    """Q&A biasa guna deepseek-v4-flash."""
    captured = {}
    with patch("httpx.AsyncClient.post", new=_make_fake_post(captured)):
        await query_llm(
            [{"role": "user", "content": "apa metodologi?"}],
            output_mode="qa",
            query_type="normal",
        )
    assert captured["model"] == settings.deepseek_model_flash
    assert captured["model"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_pro_used_for_literature_review():
    """literature_review guna deepseek-v4-pro."""
    captured = {}
    with patch("httpx.AsyncClient.post", new=_make_fake_post(captured)):
        await query_llm(
            [{"role": "user", "content": "sorotan kajian"}],
            output_mode="literature_review",
            query_type="normal",
        )
    assert captured["model"] == settings.deepseek_model_pro
    assert captured["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_pro_used_for_research_gap():
    """research_gap guna deepseek-v4-pro."""
    captured = {}
    with patch("httpx.AsyncClient.post", new=_make_fake_post(captured)):
        await query_llm(
            [{"role": "user", "content": "jurang kajian?"}],
            output_mode="research_gap",
            query_type="normal",
        )
    assert captured["model"] == settings.deepseek_model_pro
    assert captured["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_pro_used_for_deep_query_type():
    """query_type='deep' guna deepseek-v4-pro tanpa mengira output_mode."""
    captured = {}
    with patch("httpx.AsyncClient.post", new=_make_fake_post(captured)):
        await query_llm(
            [{"role": "user", "content": "analisis mendalam"}],
            output_mode="qa",
            query_type="deep",
        )
    assert captured["model"] == settings.deepseek_model_pro
    assert captured["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_citation_token_in_system_prompt():
    """System prompt wajib ada arahan [[cite:N]] untuk semua research modes."""
    from app.services.llm_provider import SYSTEM_PROMPTS
    for mode, prompt in SYSTEM_PROMPTS.items():
        assert '[[cite:' in prompt, f"Mode '{mode}' tiada arahan [[cite:N]] dalam system prompt"
