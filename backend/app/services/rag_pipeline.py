from typing import List, Dict, Any

CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
MIN_CHUNK_SIZE = 100

def chunk_text(text: str, page_number: int = 0) -> List[Dict[str, Any]]:
    words = text.split()
    chunks = []
    start = 0
    chunk_index = 0

    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        chunk_words = words[start:end]

        if len(chunk_words) >= MIN_CHUNK_SIZE:
            chunks.append({
                "text": " ".join(chunk_words),
                "page_number": page_number,
                "chunk_index": chunk_index,
                "token_count": len(chunk_words),
            })
            chunk_index += 1

        if end >= len(words):
            break
        start = end - CHUNK_OVERLAP

    return chunks
