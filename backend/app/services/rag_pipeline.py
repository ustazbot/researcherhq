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


import math
import sqlite3
import sqlite_vec
from app.config import settings as _settings


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def mmr_rerank(
    candidates: List[Dict[str, Any]],
    k: int,
    similarity_weight: float = 0.7,
    diversity_weight: float = 0.3,
) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    k = min(k, len(candidates))
    selected = []
    remaining = list(candidates)

    # Always pick highest-similarity first
    best = max(remaining, key=lambda x: x["similarity"])
    selected.append(best)
    remaining.remove(best)

    while len(selected) < k and remaining:
        best_score = float("-inf")
        best_item = None

        for item in remaining:
            relevance = item["similarity"]
            max_sim_to_selected = max(
                cosine_similarity(item.get("embedding", []), sel.get("embedding", []))
                for sel in selected
            )
            mmr_score = similarity_weight * relevance - diversity_weight * max_sim_to_selected
            if mmr_score > best_score:
                best_score = mmr_score
                best_item = item

        if best_item:
            selected.append(best_item)
            remaining.remove(best_item)

    return selected


def get_retrieval_k(query_type: str, doc_count: int) -> int:
    if query_type == "deep":
        return 12
    elif doc_count > 10:
        return 10
    else:
        return 6


async def retrieve_chunks(
    project_id: str,
    query_embedding: List[float],
    query_type: str,
    db_path: str = None,
) -> List[Dict[str, Any]]:
    path = db_path or _settings.database_url
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    sqlite_vec.load(conn)

    doc_count = conn.execute(
        "SELECT COUNT(*) as c FROM documents WHERE project_id = ?", (project_id,)
    ).fetchone()["c"]

    if doc_count == 0:
        conn.close()
        return []

    k_initial = get_retrieval_k(query_type, doc_count) * 2

    rows = conn.execute("""
        SELECT cv.chunk_id,
               vec_distance_cosine(cv.embedding, ?) AS distance,
               c.text, c.page_number, c.chunk_index,
               d.filename,
               cv.embedding
        FROM chunk_vectors cv
        JOIN chunks c ON cv.chunk_id = c.id
        JOIN documents d ON c.doc_id = d.id
        WHERE d.project_id = ?
        ORDER BY distance ASC
        LIMIT ?
    """, (query_embedding, project_id, k_initial)).fetchall()

    conn.close()

    candidates = []
    for row in rows:
        similarity = max(0.0, 1.0 - row["distance"])
        emb = list(row["embedding"]) if row["embedding"] else []
        candidates.append({
            "chunk_id": row["chunk_id"],
            "text": row["text"],
            "page_number": row["page_number"],
            "filename": row["filename"],
            "similarity": similarity,
            "embedding": emb,
        })

    # Deterministic tie-breaking
    candidates.sort(key=lambda x: (-x["similarity"], x["chunk_id"]))

    k_final = get_retrieval_k(query_type, doc_count)
    return mmr_rerank(candidates, k=k_final)
