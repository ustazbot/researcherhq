import httpx
from app.config import settings


class WebSearchUnavailable(Exception):
    pass


async def search_with_citations(query: str) -> dict:
    """
    Call Perplexity Sonar API.
    Return: {"answer": str, "citations": [{"url": str, "title": str}], "source_type": "web_search"}
    Raises: WebSearchUnavailable if key empty or API fails.
    """
    if not settings.perplexity_api_key:
        raise WebSearchUnavailable("Perplexity API key tidak dikonfigurasi.")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {settings.perplexity_api_key}"},
                json={
                    "model": settings.perplexity_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Anda pembantu penyelidikan akademik. "
                                "Berikan jawapan berdasarkan sumber yang boleh diverifikasi. "
                                "Jawab dalam Bahasa Malaysia."
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                    "return_citations": True,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise WebSearchUnavailable(str(exc)) from exc

    answer = data["choices"][0]["message"]["content"]
    # Sonar returns citations as list of URL strings
    raw_citations = data.get("citations", [])
    citations = [{"url": url, "title": url} for url in raw_citations]

    return {"answer": answer, "citations": citations, "source_type": "web_search"}
