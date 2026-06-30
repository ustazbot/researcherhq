import asyncio
import io
import json as _json
import os
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
import httpx

import app.database as _db_module
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.rag_pipeline import chunk_text

router = APIRouter()

_HEADERS = {"User-Agent": "researcherHQ/1.0 (mailto:admin@researcherhq.com)"}


# ── External API helpers ────────────────────────────────────────────────────

async def search_openalex(q: str, year_from=None) -> list:
    params = {
        "search": q,
        "per-page": 10,
        "select": "id,title,authorships,publication_year,primary_location,doi,abstract_inverted_index,cited_by_count,open_access",
    }
    if year_from:
        params["filter"] = f"publication_year:>{year_from - 1}"

    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get("https://api.openalex.org/works", params=params, headers=_HEADERS)
        r.raise_for_status()
        results = r.json().get("results", [])

    def reconstruct_abstract(inverted: dict) -> str:
        if not inverted:
            return ""
        words = sorted(inverted.items(), key=lambda x: min(x[1]))
        return " ".join(w for w, _ in words)[:1000]

    out = []
    for row in results:
        if not row.get("title"):
            continue
        oa_info = row.get("open_access") or {}
        out.append({
            "source": "openalex",
            "title": row.get("title", ""),
            "authors": [a["author"]["display_name"] for a in row.get("authorships", [])[:3]],
            "year": row.get("publication_year"),
            "journal": (row.get("primary_location") or {}).get("source", {}).get("display_name", ""),
            "doi": row.get("doi", "").replace("https://doi.org/", "") if row.get("doi") else None,
            "abstract": reconstruct_abstract(row.get("abstract_inverted_index")),
            "cited_by": row.get("cited_by_count", 0),
            "url": row.get("doi") or "",
            "is_oa": oa_info.get("is_oa", False),
            "oa_url": oa_info.get("oa_url"),
            "openalex_id": row.get("id", "").replace("https://openalex.org/", ""),
        })
    return out


async def search_semantic_scholar(q: str) -> list:
    params = {
        "query": q,
        "limit": 10,
        "fields": "title,authors,year,venue,externalIds,abstract,citationCount",
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params, headers=_HEADERS,
        )
        r.raise_for_status()
        results = r.json().get("data", [])

    return [
        {
            "source": "semantic_scholar",
            "title": row.get("title", ""),
            "authors": [a["name"] for a in row.get("authors", [])[:3]],
            "year": row.get("year"),
            "journal": row.get("venue", ""),
            "doi": (row.get("externalIds") or {}).get("DOI"),
            "abstract": (row.get("abstract") or "")[:1000],
            "cited_by": row.get("citationCount", 0),
            "url": f"https://doi.org/{row['externalIds']['DOI']}" if (row.get("externalIds") or {}).get("DOI") else "",
            "is_oa": False,
            "oa_url": None,
            "openalex_id": None,
        }
        for row in results if row.get("title")
    ]


async def search_crossref(q: str, year_from=None) -> list:
    params = {
        "query": q,
        "rows": 10,
        "select": "title,author,published,container-title,DOI,abstract",
    }
    if year_from:
        params["filter"] = f"from-pub-date:{year_from}"

    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get("https://api.crossref.org/works", params=params, headers=_HEADERS)
        r.raise_for_status()
        items = r.json().get("message", {}).get("items", [])

    return [
        {
            "source": "crossref",
            "title": (item.get("title") or [""])[0],
            "authors": [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in item.get("author", [])[:3]
            ],
            "year": ((item.get("published") or {}).get("date-parts") or [[None]])[0][0],
            "journal": (item.get("container-title") or [""])[0],
            "doi": item.get("DOI"),
            "abstract": (item.get("abstract") or "")[:1000],
            "cited_by": 0,
            "url": f"https://doi.org/{item['DOI']}" if item.get("DOI") else "",
            "is_oa": False,
            "oa_url": None,
            "openalex_id": None,
        }
        for item in items if item.get("title")
    ]


def deduplicate(results: list) -> list:
    seen_dois = set()
    seen_titles = set()
    out = []
    for r in results:
        doi = r.get("doi")
        title_key = r["title"].lower()[:60]
        if doi and doi in seen_dois:
            continue
        if not doi and title_key in seen_titles:
            continue
        if doi:
            seen_dois.add(doi)
        seen_titles.add(title_key)
        out.append(r)
    return out


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/articles")
async def search_articles(
    q: str,
    project_id: str,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    user=Depends(get_current_user),
):
    if len(q.strip()) < 3:
        raise HTTPException(400, "Kata kunci terlalu pendek (minimum 3 aksara).")

    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"]),
        ).fetchone()
        if not proj:
            raise HTTPException(403, "Projek tidak dijumpai atau akses ditolak.")
        user_row = db.execute("SELECT tier FROM users WHERE id = ?", (user["user_id"],)).fetchone()
        tier = user_row["tier"] if user_row else "free"

    if os.getenv("LOAD_TEST_MODE"):
        return {"results": [], "query": q, "total": 0}

    tasks = [
        search_openalex(q, year_from),
        search_semantic_scholar(q),
        search_crossref(q, year_from),
    ]
    all_results = []
    for coro in asyncio.as_completed(tasks):
        try:
            results = await coro
            all_results.extend(results)
        except Exception:
            pass

    all_results.sort(key=lambda x: x.get("cited_by", 0), reverse=True)
    merged = deduplicate(all_results)

    if tier != "pro":
        merged = merged[:5]

    return {"results": merged, "query": q, "total": len(merged)}


@router.get("/check-duplicate")
def check_duplicate(
    project_id: str,
    doi: Optional[str] = None,
    openalex_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(403, "Projek tidak dijumpai.")

        exists = False
        if doi:
            row = db.execute(
                "SELECT id FROM documents WHERE project_id = ? AND filename LIKE ?",
                (project_id, f"%[{doi}]%")
            ).fetchone()
            exists = row is not None
        elif openalex_id:
            row = db.execute(
                "SELECT id FROM documents WHERE project_id = ? AND openalex_id = ?",
                (project_id, openalex_id)
            ).fetchone()
            exists = row is not None

    return {"exists": exists}


class AcceptArticleBody(BaseModel):
    project_id: str
    title: str
    authors: List[str]
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    abstract: str
    url: Optional[str] = None
    source: str
    is_oa: bool = False
    oa_url: Optional[str] = None
    openalex_id: Optional[str] = None
    cited_by: int = 0


def build_article_text(body: AcceptArticleBody) -> str:
    authors_str = ", ".join(body.authors) if body.authors else "Tidak diketahui"
    return f"""TAJUK: {body.title}

PENULIS: {authors_str}
TAHUN: {body.year or 'Tidak diketahui'}
JURNAL: {body.journal or 'Tidak diketahui'}
DOI: {body.doi or 'Tiada DOI'}
SUMBER API: {body.source}

ABSTRAK:
{body.abstract}

URL: {body.url or ''}
"""


async def _embed_and_store_chunks(doc_id: str, chunk_texts_list: list, chunk_ids: list):
    """Background: embed chunks from accepted article."""
    import sqlite3 as _sqlite3
    import sqlite_vec as _sqlite_vec
    from app.services.embedding_pool import embedding_pool
    try:
        embeddings = await embedding_pool.embed_batch(chunk_texts_list)
        conn = _sqlite3.connect(_db_module._db_path)
        _sqlite_vec.load(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            conn.execute(
                "INSERT INTO chunk_vectors (chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, _sqlite_vec.serialize_float32(embedding)),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Embedding error for doc {doc_id}: {e}")


async def _fetch_oa_full_text(doc_id: str, oa_url: str, project_id: str):
    """
    Background: fetch Open Access full text dari oa_url.
    Silent fail jika URL tidak accessible.
    """
    from html.parser import HTMLParser

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(oa_url, headers=_HEADERS)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")

            if "pdf" in content_type or oa_url.endswith(".pdf"):
                try:
                    import pdfplumber
                    text = ""
                    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                        for page in pdf.pages[:50]:
                            text += (page.extract_text() or "") + "\n"
                except Exception:
                    return
            elif "html" in content_type:
                class TextExtractor(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.texts = []
                        self._skip = False

                    def handle_starttag(self, tag, attrs):
                        if tag in ('script', 'style', 'nav', 'header', 'footer'):
                            self._skip = True

                    def handle_endtag(self, tag):
                        if tag in ('script', 'style', 'nav', 'header', 'footer'):
                            self._skip = False

                    def handle_data(self, data):
                        if not self._skip and data.strip():
                            self.texts.append(data.strip())

                extractor = TextExtractor()
                extractor.feed(resp.text[:500_000])
                text = " ".join(extractor.texts)
            else:
                return

            if len(text.strip()) < 200:
                return

            chunks = chunk_text(text[:100_000], page_number=1)
            if not chunks:
                return

            with get_db() as db:
                now = datetime.utcnow().isoformat()
                old_chunks = db.execute(
                    "SELECT id FROM chunks WHERE doc_id = ?", (doc_id,)
                ).fetchall()
                old_chunk_ids = [r["id"] for r in old_chunks]
                if old_chunk_ids:
                    db.execute(
                        f"DELETE FROM chunk_vectors WHERE chunk_id IN ({','.join('?'*len(old_chunk_ids))})",
                        old_chunk_ids
                    )
                    db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

                chunk_ids = []
                chunk_texts_list = []
                for chunk in chunks:
                    cid = str(uuid.uuid4())
                    db.execute(
                        "INSERT INTO chunks (id, doc_id, page_number, chunk_index, text, created_at) VALUES (?,?,?,?,?,?)",
                        (cid, doc_id, chunk["page_number"], chunk["chunk_index"], chunk["text"], now)
                    )
                    chunk_ids.append(cid)
                    chunk_texts_list.append(chunk["text"])

                db.execute(
                    "UPDATE documents SET content_level = 'full_text', chunk_count = ? WHERE id = ?",
                    (len(chunks), doc_id)
                )
                db.execute(
                    "UPDATE projects SET document_set_version = document_set_version + 1 WHERE id = ?",
                    (project_id,)
                )

            await _embed_and_store_chunks(doc_id, chunk_texts_list, chunk_ids)

    except Exception as e:
        print(f"OA fetch failed for doc {doc_id}: {e}")


@router.post("/accept", status_code=201)
async def accept_article(
    body: AcceptArticleBody,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (body.project_id, user["user_id"]),
        ).fetchone()
        if not proj:
            raise HTTPException(403, "Projek tidak dijumpai atau akses ditolak.")

        user_row = db.execute("SELECT tier FROM users WHERE id = ?", (user["user_id"],)).fetchone()
        tier = user_row["tier"] if user_row else "free"

        if tier != "pro":
            raise HTTPException(403, "Tambah artikel dari Search hanya untuk pengguna Pro.")

        doc_count = db.execute(
            "SELECT COUNT(*) as c FROM documents WHERE project_id = ?",
            (body.project_id,),
        ).fetchone()["c"]
        if doc_count >= 5:
            raise HTTPException(403, "Had dokumen (5 serentak) tercapai.")

        if body.doi:
            existing = db.execute(
                "SELECT id FROM documents WHERE project_id = ? AND filename LIKE ?",
                (body.project_id, f"%[{body.doi}]%"),
            ).fetchone()
            if existing:
                raise HTTPException(409, "Artikel dengan DOI yang sama sudah ditambah dalam projek ini.")

        doc_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        first_author_last = body.authors[0].split()[-1] if body.authors else "Anon"
        doi_suffix = f"[{body.doi}]" if body.doi else ""
        filename = f"{first_author_last} ({body.year or '?'}) — {body.title[:50]}{doi_suffix}.txt"

        external_meta = _json.dumps({
            "doi": body.doi,
            "authors": body.authors,
            "year": body.year,
            "journal": body.journal,
            "cited_by": body.cited_by,
            "oa_url": body.oa_url,
            "url": body.url,
        })

        article_text = build_article_text(body)
        chunks = chunk_text(article_text, page_number=1)

        db.execute(
            """INSERT INTO documents
               (id, project_id, filename, category, page_count, chunk_count,
                source_type, content_level, openalex_id, external_metadata, uploaded_at)
               VALUES (?, ?, ?, 'artikel_rujukan', ?, ?, 'search_result', ?, ?, ?, ?)""",
            (doc_id, body.project_id, filename, 1, len(chunks),
             'abstract_only',
             body.openalex_id, external_meta, now),
        )

        chunk_ids = []
        for chunk in chunks:
            chunk_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO chunks (id, doc_id, page_number, chunk_index, text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chunk_id, doc_id, chunk["page_number"], chunk["chunk_index"], chunk["text"], now),
            )
            chunk_ids.append(chunk_id)

        db.execute(
            "UPDATE projects SET document_set_version = document_set_version + 1 WHERE id = ?",
            (body.project_id,),
        )

    chunk_texts_list = [c["text"] for c in chunks]
    background_tasks.add_task(_embed_and_store_chunks, doc_id, chunk_texts_list, chunk_ids)

    if body.is_oa and body.oa_url:
        background_tasks.add_task(_fetch_oa_full_text, doc_id, body.oa_url, body.project_id)

    return {
        "id": doc_id,
        "filename": filename,
        "chunk_count": len(chunks),
        "category": "artikel_rujukan",
        "source_type": "search_result",
        "content_level": "full_text" if (body.is_oa and body.oa_url) else "abstract_only",
        "status": "accepted",
        "message": (
            "Artikel diterima. Memproses teks penuh..."
            if (body.is_oa and body.oa_url)
            else "Artikel diterima (abstract sahaja). Muat naik PDF untuk analisis mendalam."
        ),
    }
