# Editor Model Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure workspace dari 3-kolum-statik kepada model Editor-centric: Bab aktif jadi pane utama, Source jadi collapsible sidebar, Chat jadi sidebar, dan AI cadang dulu (Terima/Tolak) bukan overwrite terus.

**Architecture:** Backend dapat 4 endpoint baru (DELETE chapter, PATCH chapter meta, GET chapter content, DELETE document). Frontend restructure kepada 4 komponen jelas (SourcePanel collapsible, ThesisPanel navigator, ChapterEditor utama, ChatPanel sidebar). pendingSuggestion disimpan dalam React state sahaja — tiada DB baru.

**Tech Stack:** FastAPI + SQLite (backend), React + inline styles dengan design tokens sedia ada (frontend), `useMediaQuery` sedia ada untuk breakpoint <768px.

## Global Constraints

- Bahasa UI: "Terima" / "Tolak" (bukan Apply/Discard). Label bab terus (bukan "Editor pane"). Tiada font monospace dalam editor, tiada dark-theme default — kekal design tokens sedia ada (`var(--bg)`, `var(--accent)`, `var(--ink)`, dll.)
- Design tokens rujuk `Logo.jsx` dan inline styles sedia ada dalam ProjectPage.jsx
- Setiap commit mesti pass backend test suite (baseline: 90 pass / 3 deselected)
- Frontend state `pendingSuggestion` = `{ text: string } | null` — JANGAN tambah DB table baru untuk cadangan
- **FLAG untuk Bos:** Setiap AI answer dalam chat ada butang "→ Hantar ke Editor" (eksplisit). Jika Bos mahu auto-cadangan untuk mode tertentu (literature_review dsb.), beritahu dan plan akan dikemas kini.
- Reorder bab: guna butang ↑↓ (bukan drag-and-drop) — lebih ringkas

---

## File Structure

### Backend — Modify
- `backend/app/routers/chapters.py` — tambah GET single, DELETE, PATCH meta
- `backend/app/routers/documents.py` — tambah DELETE

### Backend — Create
- `backend/tests/test_chapters_crud.py` — tests untuk 4 endpoint baru

### Frontend — Create
- `frontend/src/components/ChapterEditor.jsx` — pane utama editor + suggestion mode
- `frontend/src/components/ChatPanel.jsx` — extracted dari ProjectPage inline

### Frontend — Modify
- `frontend/src/components/SourcePanel.jsx` — collapsible + delete per-dokumen
- `frontend/src/components/ThesisPanel.jsx` — jadi navigator: active highlight, Add/Delete/Reorder
- `frontend/src/pages/ProjectPage.jsx` — restructure layout, state baru, mobile rebuild

---

## Task 1: Backend — Panel CRUD + GET chapter content

**Files:**
- Modify: `backend/app/routers/chapters.py`
- Modify: `backend/app/routers/documents.py`
- Create: `backend/tests/test_chapters_crud.py`

**Interfaces:**
- Produces:
  - `GET /projects/{project_id}/chapters/{chapter_id}` → `{ id, title, chapter_order, status, content }`
  - `DELETE /projects/{project_id}/chapters/{chapter_id}` → 204
  - `PATCH /projects/{project_id}/chapters/{chapter_id}` body `{ title?, chapter_order? }` → `{ id, title, chapter_order }`
  - `DELETE /documents/{doc_id}` → 204, bumps `document_set_version`

- [ ] **Step 1: Tulis failing tests untuk semua 4 endpoint baru**

Cipta fail `backend/tests/test_chapters_crud.py`:

```python
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt

def make_headers(user_id="user-1", email="u1@test.com"):
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def client_with_chapter(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            h = make_headers()
            proj_r = c.post("/projects", json={"title": "Tesis", "research_mode": "general"}, headers=h)
            project_id = proj_r.json()["id"]
            chap_r = c.post(
                f"/projects/{project_id}/chapters",
                json={"title": "Bab 1: Pengenalan", "chapter_order": 1},
                headers=h
            )
            chapter_id = chap_r.json()["id"]
            yield c, project_id, chapter_id, h

# --- GET single chapter ---

def test_get_chapter_returns_content(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.get(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == chapter_id
    assert data["title"] == "Bab 1: Pengenalan"
    assert "content" in data
    assert data["content"] == ""  # fresh chapter starts empty

def test_get_chapter_not_found(client_with_chapter):
    client, project_id, _, h = client_with_chapter
    r = client.get(f"/projects/{project_id}/chapters/nonexistent", headers=h)
    assert r.status_code == 404

# --- DELETE chapter ---

def test_delete_chapter(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.delete(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)
    assert r.status_code == 204
    # Verify chapter gone
    r2 = client.get(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)
    assert r2.status_code == 404

def test_delete_chapter_cascades_content(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    import sqlite3, app.database as _db
    conn = sqlite3.connect(_db._db_path)
    before = conn.execute("SELECT id FROM chapter_content WHERE chapter_id=?", (chapter_id,)).fetchone()
    conn.close()
    assert before is not None  # content row exists

    client.delete(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)

    conn2 = sqlite3.connect(_db._db_path)
    after = conn2.execute("SELECT id FROM chapter_content WHERE chapter_id=?", (chapter_id,)).fetchone()
    conn2.close()
    assert after is None  # cascaded

def test_delete_chapter_wrong_user(client_with_chapter):
    client, project_id, chapter_id, _ = client_with_chapter
    other_h = make_headers("user-2", "u2@test.com")
    r = client.delete(f"/projects/{project_id}/chapters/{chapter_id}", headers=other_h)
    assert r.status_code == 404  # project not found for other user

# --- PATCH chapter meta ---

def test_patch_chapter_title(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}",
        json={"title": "Bab 1: Latar Belakang Kajian"},
        headers=h
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Bab 1: Latar Belakang Kajian"

def test_patch_chapter_order(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}",
        json={"chapter_order": 3},
        headers=h
    )
    assert r.status_code == 200
    assert r.json()["chapter_order"] == 3

def test_patch_chapter_partial(client_with_chapter):
    """Patch without title should preserve existing title."""
    client, project_id, chapter_id, h = client_with_chapter
    r = client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}",
        json={"chapter_order": 2},
        headers=h
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Bab 1: Pengenalan"  # preserved

# --- DELETE document ---

@pytest.fixture
def client_with_doc(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            h = make_headers()
            proj_r = c.post("/projects", json={"title": "Tesis", "research_mode": "general"}, headers=h)
            project_id = proj_r.json()["id"]
            doc_r = c.post("/documents/upload", json={
                "project_id": project_id,
                "filename": "artikel.pdf",
                "category": "artikel",
                "pages": [{"page_number": 1, "text": " ".join(["perkataan"] * 150)}]
            }, headers=h)
            doc_id = doc_r.json()["id"]
            yield c, project_id, doc_id, h

def test_delete_document(client_with_doc):
    client, project_id, doc_id, h = client_with_doc
    r = client.delete(f"/documents/{doc_id}", headers=h)
    assert r.status_code == 204
    # Verify doc gone from list
    docs = client.get(f"/documents?project_id={project_id}", headers=h).json()
    assert all(d["id"] != doc_id for d in docs)

def test_delete_document_bumps_version(client_with_doc):
    client, project_id, doc_id, h = client_with_doc
    version_before = client.get(f"/projects/{project_id}", headers=h).json()["document_set_version"]
    client.delete(f"/documents/{doc_id}", headers=h)
    version_after = client.get(f"/projects/{project_id}", headers=h).json()["document_set_version"]
    assert version_after == version_before + 1

def test_delete_document_wrong_user(client_with_doc):
    client, _, doc_id, _ = client_with_doc
    other_h = make_headers("user-2", "u2@test.com")
    r = client.delete(f"/documents/{doc_id}", headers=other_h)
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests — semua patut FAIL**

```bash
cd /home/astro/claude-project/researcherhq/backend
python -m pytest tests/test_chapters_crud.py -v 2>&1 | tail -20
```

Expected: semua fail dengan `405 Method Not Allowed` atau `404`.

- [ ] **Step 3: Tambah 4 endpoint baru dalam chapters.py**

Buka `backend/app/routers/chapters.py`. Tambah selepas `from pydantic import BaseModel`:

```python
from typing import Optional
```

Tambah class baru selepas `ChapterContentUpdate`:

```python
class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    chapter_order: Optional[int] = None
```

Tambah 3 endpoint baru (tambah selepas list_chapters endpoint):

```python
@router.get("/projects/{project_id}/chapters/{chapter_id}")
def get_chapter(project_id: str, chapter_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id=? AND user_id=?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        row = db.execute(
            """SELECT ch.id, ch.title, ch.chapter_order, ch.status, cc.content
               FROM chapters ch
               LEFT JOIN chapter_content cc ON cc.chapter_id = ch.id
               WHERE ch.id=? AND ch.project_id=?""",
            (chapter_id, project_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Bab tidak dijumpai.")
    return dict(row)


@router.delete("/projects/{project_id}/chapters/{chapter_id}", status_code=204)
def delete_chapter(project_id: str, chapter_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id=? AND user_id=?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        chap = db.execute(
            "SELECT id FROM chapters WHERE id=? AND project_id=?",
            (chapter_id, project_id)
        ).fetchone()
        if not chap:
            raise HTTPException(404, "Bab tidak dijumpai.")
        db.execute("DELETE FROM chapters WHERE id=?", (chapter_id,))
        # chapter_content cascades via FK ON DELETE CASCADE


@router.patch("/projects/{project_id}/chapters/{chapter_id}")
def update_chapter(
    project_id: str, chapter_id: str,
    body: ChapterUpdate,
    user=Depends(get_current_user)
):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id=? AND user_id=?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        chap = db.execute(
            "SELECT id, title, chapter_order FROM chapters WHERE id=? AND project_id=?",
            (chapter_id, project_id)
        ).fetchone()
        if not chap:
            raise HTTPException(404, "Bab tidak dijumpai.")
        new_title = body.title if body.title is not None else chap["title"]
        new_order = body.chapter_order if body.chapter_order is not None else chap["chapter_order"]
        db.execute(
            "UPDATE chapters SET title=?, chapter_order=? WHERE id=?",
            (new_title, new_order, chapter_id)
        )
    return {"id": chapter_id, "title": new_title, "chapter_order": new_order}
```

- [ ] **Step 4: Tambah DELETE document dalam documents.py**

Tambah selepas `get_document` endpoint (akhir fail):

```python
@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        doc = db.execute(
            """SELECT d.id, d.project_id FROM documents d
               JOIN projects p ON d.project_id = p.id
               WHERE d.id=? AND p.user_id=?""",
            (doc_id, user["user_id"])
        ).fetchone()
        if not doc:
            raise HTTPException(404, "Dokumen tidak dijumpai.")
        project_id = doc["project_id"]

        # chunk_vectors adalah virtual table — tiada FK cascade, perlu padam manual
        chunk_ids = [
            row["id"] for row in db.execute(
                "SELECT id FROM chunks WHERE doc_id=?", (doc_id,)
            ).fetchall()
        ]
        for chunk_id in chunk_ids:
            db.execute("DELETE FROM chunk_vectors WHERE chunk_id=?", (chunk_id,))

        # padam dokumen — chunks cascade via FK ON DELETE CASCADE
        db.execute("DELETE FROM documents WHERE id=?", (doc_id,))

        # invalidate query cache
        db.execute(
            "UPDATE projects SET document_set_version = document_set_version + 1 WHERE id=?",
            (project_id,)
        )
```

- [ ] **Step 5: Run tests — semua patut PASS**

```bash
cd /home/astro/claude-project/researcherhq/backend
python -m pytest tests/test_chapters_crud.py -v 2>&1 | tail -20
```

Expected: semua 11 test PASS.

- [ ] **Step 6: Run full test suite — tiada regression**

```bash
cd /home/astro/claude-project/researcherhq/backend
python -m pytest --tb=short 2>&1 | tail -10
```

Expected: `90 passed, 3 deselected` → sekarang `101 passed, 3 deselected` (11 test baru).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/chapters.py backend/app/routers/documents.py backend/tests/test_chapters_crud.py
git commit -m "feat(api): panel CRUD — DELETE/PATCH chapter, GET chapter content, DELETE document"
```

---

## Task 2: `ChapterEditor.jsx` — Komponen Editor Baru

**Files:**
- Create: `frontend/src/components/ChapterEditor.jsx`

**Interfaces:**
- Consumes (dari Task 4 / ProjectPage):
  - `chapter` — `{ id, title, chapter_order, status }` atau `null`
  - `content` — string (content bab aktif, fetched oleh ProjectPage)
  - `pendingSuggestion` — `{ text: string } | null`
  - `onAccept(text: string)` — user klik Terima → ProjectPage PATCH content ke DB
  - `onReject()` — user klik Tolak → ProjectPage clear pendingSuggestion
  - `onSave(text: string)` — user klik Simpan manual → ProjectPage PATCH content
  - `saving` — boolean (semasa API call)

- Produces: komponen UI, tiada side effects sendiri

- [ ] **Step 1: Cipta ChapterEditor.jsx**

```jsx
// frontend/src/components/ChapterEditor.jsx
import { useState, useEffect } from 'react'

const TOOLTIP_KEY = 'rhq_suggestion_tooltip_seen'

export function ChapterEditor({ chapter, content, pendingSuggestion, onAccept, onReject, onSave, saving }) {
  const [editText, setEditText] = useState(content || '')
  const [showTooltip, setShowTooltip] = useState(false)

  // Sync edit text bila chapter bertukar atau content load dari API
  useEffect(() => {
    if (!pendingSuggestion) setEditText(content || '')
  }, [content, chapter?.id])

  // First-time tooltip bila ada cadangan AI buat pertama kali
  useEffect(() => {
    if (pendingSuggestion && !localStorage.getItem(TOOLTIP_KEY)) {
      setShowTooltip(true)
    }
  }, [pendingSuggestion])

  function dismissTooltip() {
    localStorage.setItem(TOOLTIP_KEY, '1')
    setShowTooltip(false)
  }

  if (!chapter) {
    return (
      <div style={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg)', color: 'var(--ink-soft)',
        fontFamily: 'var(--font-body)', fontSize: 15, padding: 40, textAlign: 'center',
      }}>
        <div>
          <p style={{ marginBottom: 8, fontWeight: 500 }}>Pilih bab dari panel Struktur Tesis.</p>
          <p style={{ fontSize: 13 }}>Atau tambah bab baru untuk mula menulis.</p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg)' }}>
      {/* Header */}
      <div style={{
        padding: '12px 24px', borderBottom: '1px solid var(--line)',
        background: 'var(--card)', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16, color: 'var(--ink)' }}>
          {chapter.title}
        </span>
        {!pendingSuggestion && (
          <button
            onClick={() => onSave(editText)}
            disabled={saving || editText === (content || '')}
            style={{
              padding: '6px 16px', background: 'var(--accent)', border: 'none',
              borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)',
              fontWeight: 700, fontSize: 13, cursor: saving ? 'wait' : 'pointer',
              opacity: (saving || editText === (content || '')) ? 0.5 : 1,
            }}
          >
            {saving ? 'Menyimpan...' : 'Simpan'}
          </button>
        )}
      </div>

      {/* First-time tooltip */}
      {showTooltip && (
        <div style={{
          margin: '12px 24px 0', padding: '12px 16px',
          background: 'var(--accent-soft)', border: '1px solid var(--accent)',
          borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'flex-start',
          gap: 12,
        }}>
          <span style={{ fontSize: 18 }}>💡</span>
          <div style={{ flex: 1 }}>
            <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}>
              Ni cadangan AI — klik <strong>Terima</strong> untuk masuk ke bab, atau <strong>Tolak</strong> untuk buang.
              Sama macam Track Changes dalam Word yang penyelia guna untuk bagi maklum balas.
            </p>
          </div>
          <button onClick={dismissTooltip} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--ink-soft)', fontSize: 16, flexShrink: 0, padding: 0,
          }}>×</button>
        </div>
      )}

      {/* Suggestion mode */}
      {pendingSuggestion ? (
        <div style={{ flex: 1, overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Suggestion banner */}
          <div style={{
            borderLeft: '4px solid var(--accent)', paddingLeft: 16,
            background: 'var(--accent-soft)', borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
            padding: '16px 16px 16px 20px',
          }}>
            <p style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase',
              letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px',
            }}>
              Cadangan AI
            </p>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 15, lineHeight: 1.7, color: 'var(--ink)', margin: 0, whiteSpace: 'pre-wrap' }}>
              {pendingSuggestion.text}
            </p>
          </div>

          {/* Terima / Tolak */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => onAccept(pendingSuggestion.text)}
              disabled={saving}
              style={{
                padding: '10px 24px', background: 'var(--accent)', border: 'none',
                borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)',
                fontWeight: 700, fontSize: 14, cursor: saving ? 'wait' : 'pointer',
                opacity: saving ? 0.6 : 1,
              }}
            >
              {saving ? 'Menyimpan...' : 'Terima'}
            </button>
            <button
              onClick={onReject}
              disabled={saving}
              style={{
                padding: '10px 24px', background: 'transparent',
                border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
                fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14,
                cursor: 'pointer', color: 'var(--ink-soft)',
              }}
            >
              Tolak
            </button>
          </div>

          {/* Current content (read-only, muted) — only show if not empty */}
          {(content || '').trim() && (
            <div>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Kandungan semasa (tidak berubah jika Tolak)
              </p>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 14, lineHeight: 1.7, color: 'var(--ink-soft)', whiteSpace: 'pre-wrap' }}>
                {content}
              </p>
            </div>
          )}
        </div>
      ) : (
        /* Edit mode */
        <textarea
          value={editText}
          onChange={e => setEditText(e.target.value)}
          placeholder="Mula taip kandungan bab di sini..."
          style={{
            flex: 1, padding: '24px', border: 'none', outline: 'none', resize: 'none',
            fontFamily: 'var(--font-body)', fontSize: 15, lineHeight: 1.8,
            background: 'var(--bg)', color: 'var(--ink)',
          }}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify komponen boleh diimport (tiada syntax error)**

```bash
cd /home/astro/claude-project/researcherhq/frontend
node -e "import('./src/components/ChapterEditor.jsx').then(() => console.log('OK')).catch(e => console.error(e))" 2>&1 || echo "syntax check done"
```

(Akan fail kerana ESM dalam Node, tapi error mesej harus ada nama modul bukan syntax error — atau gunakan langkah seterusnya dalam browser.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ChapterEditor.jsx
git commit -m "feat(ui): ChapterEditor component — edit mode + Terima/Tolak suggestion mode"
```

---

## Task 3: ChatPanel.jsx — Extracted dari ProjectPage

**Files:**
- Create: `frontend/src/components/ChatPanel.jsx`

**Interfaces:**
- Consumes:
  - `messages` — array `{ id, role, content, sources?, kredit_used? }`
  - `loading` — boolean
  - `query` — string
  - `onQueryChange(val: string)` — untuk controlled input
  - `onSubmit(e)` — form submit handler
  - `outputMode` — string
  - `onOutputModeChange(mode: string)` — toggle output mode
  - `credits` — `{ kredit_remaining, tier } | null`
  - `onSendToEditor(text: string)` — butang "→ Hantar ke Editor" per AI message, disabled jika tiada activeChapterId
  - `hasActiveChapter` — boolean (untuk disable butang Hantar ke Editor)
  - `bottomRef` — React ref untuk scroll
- Produces: panel chat full UI

- [ ] **Step 1: Cipta ChatPanel.jsx**

Ini extracted + extended dari ProjectPage inline chat. Tambah `onSendToEditor` per message:

```jsx
// frontend/src/components/ChatPanel.jsx
import { CitationCard } from './CitationCard'

const OUTPUT_MODES = [
  { value: 'qa', label: 'Soal-Jawab', credits: 1 },
  { value: 'key_findings', label: 'Dapatan Utama', credits: 3 },
  { value: 'executive_summary', label: 'Ringkasan Eksekutif', credits: 5 },
  { value: 'literature_review', label: 'Sorotan Kajian', credits: 10 },
]

export function ChatPanel({ messages, loading, query, onQueryChange, onSubmit, outputMode, onOutputModeChange, credits, onSendToEditor, hasActiveChapter, bottomRef }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', background: 'var(--card)', flexShrink: 0 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Chat AI
        </span>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '20px 16px' }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--ink-soft)' }}>
            <p style={{ fontSize: 15, fontWeight: 500 }}>Muat naik dokumen dan mula bertanya.</p>
            <p style={{ fontSize: 13 }}>Semua jawapan bersumberkan dokumen anda sahaja.</p>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} style={{
            marginBottom: 20, display: 'flex', flexDirection: 'column',
            alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '90%',
              background: msg.role === 'user' ? 'var(--ink)' : msg.role === 'error' ? '#FEF2F2' : 'var(--card)',
              color: msg.role === 'user' ? 'var(--bg)' : msg.role === 'error' ? '#EF4444' : 'var(--ink)',
              border: msg.role === 'user' ? 'none' : `1px solid ${msg.role === 'error' ? '#FECACA' : 'var(--line)'}`,
              borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
              padding: '12px 16px', fontFamily: 'var(--font-body)', fontSize: 14,
              lineHeight: 1.6, whiteSpace: 'pre-wrap',
            }}>
              {msg.content}
              {msg.kredit_used && (
                <span style={{ display: 'block', marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 10, opacity: 0.6 }}>
                  {msg.kredit_used} kredit
                </span>
              )}
            </div>

            {/* Butang Hantar ke Editor — hanya untuk AI answers */}
            {msg.role === 'assistant' && (
              <button
                onClick={() => onSendToEditor(msg.content)}
                disabled={!hasActiveChapter}
                title={!hasActiveChapter ? 'Pilih bab dahulu untuk hantar ke Editor' : 'Hantar jawapan ini ke bab aktif sebagai cadangan'}
                style={{
                  marginTop: 4, padding: '3px 10px',
                  background: 'transparent',
                  border: '1px solid var(--line)',
                  borderRadius: 4, cursor: hasActiveChapter ? 'pointer' : 'not-allowed',
                  fontFamily: 'var(--font-mono)', fontSize: 11,
                  color: hasActiveChapter ? 'var(--ink)' : 'var(--ink-soft)',
                  opacity: hasActiveChapter ? 1 : 0.5,
                }}
              >
                → Hantar ke Editor
              </button>
            )}

            {msg.sources && msg.sources.length > 0 && (
              <div style={{ marginTop: 8, maxWidth: '90%', width: '100%' }}>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)', margin: '0 0 4px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Sumber ({msg.sources.length})
                </p>
                {msg.sources.map(s => <CitationCard key={s.chunk_id} source={s} />)}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', marginBottom: 20 }}>
            <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: '4px 16px 16px 16px', padding: '12px 16px' }}>
              <span style={{ color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>Berfikir...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div style={{ borderTop: '1px solid var(--line)', padding: '12px 16px', background: 'var(--card)', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 10, flexWrap: 'wrap' }}>
          {OUTPUT_MODES.map(m => (
            <button key={m.value} onClick={() => onOutputModeChange(m.value)} style={{
              padding: '3px 8px',
              background: outputMode === m.value ? 'var(--ink)' : 'transparent',
              color: outputMode === m.value ? 'var(--bg)' : 'var(--ink-soft)',
              border: `1px solid ${outputMode === m.value ? 'var(--ink)' : 'var(--line)'}`,
              borderRadius: 5, fontFamily: 'var(--font-mono)', fontSize: 10, cursor: 'pointer',
            }}>
              {m.label} ({m.credits}kr)
            </button>
          ))}
        </div>
        <form onSubmit={onSubmit} style={{ display: 'flex', gap: 6 }}>
          <input
            value={query} onChange={e => onQueryChange(e.target.value)}
            placeholder="Tanya soalan..."
            disabled={loading}
            style={{
              flex: 1, padding: '10px 14px',
              border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
              fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', outline: 'none',
            }}
          />
          <button type="submit" disabled={loading || !query.trim()} style={{
            padding: '10px 16px', background: 'var(--accent)', color: 'var(--ink)',
            border: 'none', borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, cursor: 'pointer',
          }}>→</button>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ChatPanel.jsx
git commit -m "feat(ui): extract ChatPanel from ProjectPage — adds Hantar ke Editor button per AI message"
```

---

## Task 4: SourcePanel + ThesisPanel Refactor

**Files:**
- Modify: `frontend/src/components/SourcePanel.jsx`
- Modify: `frontend/src/components/ThesisPanel.jsx`

**Interfaces:**

SourcePanel new props:
- `collapsed` — boolean
- `onToggleCollapse()` — toggle show/hide
- `onDeleteDoc(docId: string)` — delete callback (ProjectPage buat API call + update state)

ThesisPanel new props:
- `activeChapterId` — string | null
- `onSetActive(chapterId: string)` — klik chapter untuk set aktif
- `onAddChapter(title: string)` — ProjectPage buat POST + update state
- `onDeleteChapter(chapterId: string)` — ProjectPage buat DELETE + update state
- `onReorderChapter(chapterId: string, direction: 'up'|'down')` — ProjectPage buat PATCH + update state

- [ ] **Step 1: Refactor SourcePanel.jsx — tambah collapse + delete**

Replace keseluruhan `frontend/src/components/SourcePanel.jsx`:

```jsx
import { useState } from 'react'

const CATEGORIES = [
  { value: 'artikel', label: 'Artikel Rujukan', icon: '📄' },
  { value: 'catatan_sv', label: 'Catatan SV', icon: '📝' },
  { value: 'draf', label: 'Draf Sendiri', icon: '📑' },
  { value: 'data', label: 'Data / Transkrip', icon: '📊' },
]

export function SourcePanel({ documents, onUpload, tier, uploading, collapsed, onToggleCollapse, onDeleteDoc }) {
  const [activeCategory, setActiveCategory] = useState('artikel')
  const uploadDisabled = tier !== 'pro' && (documents || []).length >= 1

  const grouped = CATEGORIES.map(cat => ({
    ...cat,
    docs: (documents || []).filter(d => d.category === cat.value)
  }))

  function handleDelete(e, docId, filename) {
    e.stopPropagation()
    if (window.confirm(`Padam "${filename}"? Semua chunk dan embedding dokumen ini akan dibuang.`)) {
      onDeleteDoc(docId)
    }
  }

  if (collapsed) {
    return (
      <div style={{
        width: 36, flexShrink: 0, borderRight: '1px solid var(--line)',
        background: 'var(--card)', display: 'flex', flexDirection: 'column', alignItems: 'center',
        paddingTop: 12,
      }}>
        <button
          onClick={onToggleCollapse}
          title="Buka panel Sumber"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--ink-soft)', fontSize: 16, padding: 4,
          }}
        >›</button>
      </div>
    )
  }

  return (
    <div style={{
      width: 260, flexShrink: 0, borderRight: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column', background: 'var(--card)',
      overflow: 'hidden',
    }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Sumber
        </span>
        <button
          onClick={onToggleCollapse}
          title="Tutup panel Sumber"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 16, padding: 0 }}
        >‹</button>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {grouped.map(cat => (
          <div key={cat.value}>
            <button
              onClick={() => setActiveCategory(activeCategory === cat.value ? null : cat.value)}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                width: '100%', padding: '8px 16px', background: 'transparent', border: 'none',
                fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)',
                cursor: 'pointer', textAlign: 'left',
              }}
            >
              <span>{cat.icon} {cat.label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)' }}>
                {cat.docs.length}
              </span>
            </button>
            {activeCategory === cat.value && cat.docs.map(doc => (
              <div key={doc.id} style={{
                padding: '6px 16px 6px 32px',
                display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 4,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-soft)', wordBreak: 'break-word' }}>
                    {doc.filename}
                  </p>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)' }}>
                    {doc.chunk_count} chunk
                  </span>
                </div>
                <button
                  onClick={e => handleDelete(e, doc.id, doc.filename)}
                  title="Padam dokumen ini"
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--ink-soft)', fontSize: 14, padding: '2px 4px',
                    flexShrink: 0, lineHeight: 1,
                  }}
                >×</button>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div style={{ padding: 12, borderTop: '1px solid var(--line)' }}>
        <button
          onClick={uploadDisabled || uploading ? undefined : onUpload}
          disabled={uploadDisabled || uploading}
          title={uploadDisabled ? 'Free tier: 1 PDF sahaja. Naik taraf ke Pro untuk sehingga 5 PDF.' : ''}
          style={{
            width: '100%', padding: '8px 0',
            background: uploadDisabled ? 'var(--line)' : 'var(--accent-soft)',
            border: `1px solid ${uploadDisabled ? 'var(--line)' : 'var(--accent)'}`,
            borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 13,
            cursor: uploadDisabled || uploading ? 'not-allowed' : 'pointer',
            color: uploadDisabled ? 'var(--ink-soft)' : 'var(--ink)',
            opacity: uploadDisabled || uploading ? 0.6 : 1,
          }}
        >
          {uploadDisabled ? '🔒 Had Dicapai' : uploading ? 'Memproses...' : '+ Muat naik'}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Refactor ThesisPanel.jsx — jadi navigator dengan CRUD**

Replace keseluruhan `frontend/src/components/ThesisPanel.jsx`:

```jsx
import { useState } from 'react'
import api from '../api/client'

const STATUS_LABEL = { draft: 'Draf', dalam_proses: 'Dalam Proses', siap: 'Siap' }
const STATUS_COLOR = { draft: 'var(--line)', dalam_proses: 'var(--accent-soft)', siap: '#D1FAE5' }

export function ThesisPanel({ chapters, onExport, tier, projectId, activeChapterId, onSetActive, onAddChapter, onDeleteChapter, onReorderChapter }) {
  const [upgrading, setUpgrading] = useState(false)
  const [addMode, setAddMode] = useState(false)
  const [newTitle, setNewTitle] = useState('')

  const done = (chapters || []).filter(c => c.status === 'siap').length
  const total = (chapters || []).length

  function handleAdd(e) {
    e.preventDefault()
    if (!newTitle.trim()) return
    onAddChapter(newTitle.trim())
    setNewTitle('')
    setAddMode(false)
  }

  function handleDelete(e, chap) {
    e.stopPropagation()
    if (window.confirm(`Padam "${chap.title}"? Kandungan bab ini akan hilang sepenuhnya.`)) {
      onDeleteChapter(chap.id)
    }
  }

  return (
    <div style={{
      width: 260, flexShrink: 0, borderLeft: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column', background: 'var(--card)',
      position: 'relative',
    }}>
      {tier !== 'pro' && (
        <div style={{
          position: 'absolute', inset: 0,
          background: 'rgba(248,246,241,0.88)',
          backdropFilter: 'blur(2px)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          zIndex: 10, padding: 24, textAlign: 'center',
        }}>
          <span style={{ fontSize: 32, marginBottom: 12 }}>🔒</span>
          <p style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16, margin: '0 0 8px' }}>
            Thesis Workspace
          </p>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)', margin: '0 0 16px' }}>
            Urus bab, assign output AI, dan export .docx — hanya untuk Pro.
          </p>
          <button
            onClick={async () => {
              setUpgrading(true)
              try {
                const { data } = await api.post('/billing/upgrade/initiate')
                window.location.href = data.payment_url
              } catch {
                alert('Gagal memulakan pembayaran. Sila cuba lagi.')
                setUpgrading(false)
              }
            }}
            disabled={upgrading}
            style={{
              padding: '10px 20px', background: 'var(--accent)', border: 'none',
              borderRadius: 'var(--radius-sm)', fontWeight: 700, cursor: upgrading ? 'wait' : 'pointer',
              fontFamily: 'var(--font-heading)', fontSize: 14, opacity: upgrading ? 0.7 : 1,
            }}
          >
            {upgrading ? 'Memproses...' : 'Naik taraf ke Pro — RM39/bulan'}
          </button>
        </div>
      )}

      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Struktur Tesis
        </span>
        {total > 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: done === total ? '#16A34A' : 'var(--ink-soft)' }}>
            {done}/{total} siap
          </span>
        )}
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {total === 0 && !addMode && (
          <p style={{ padding: '16px', color: 'var(--ink-soft)', fontSize: 13 }}>
            Tiada bab lagi. Tambah bab pertama anda.
          </p>
        )}

        {(chapters || []).map((chap, idx) => {
          const isActive = chap.id === activeChapterId
          return (
            <div
              key={chap.id}
              onClick={() => onSetActive(chap.id)}
              style={{
                padding: '8px 12px',
                borderBottom: '1px solid var(--line)',
                background: isActive ? 'var(--accent-soft)' : 'transparent',
                borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 4 }}>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)', flex: 1, wordBreak: 'break-word' }}>
                  {chap.title}
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 5px', borderRadius: 3,
                  background: STATUS_COLOR[chap.status] || 'var(--line)', color: 'var(--ink)',
                  flexShrink: 0,
                }}>
                  {STATUS_LABEL[chap.status] || chap.status}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6 }} onClick={e => e.stopPropagation()}>
                {/* Reorder butang */}
                <button
                  onClick={() => onReorderChapter(chap.id, 'up')}
                  disabled={idx === 0}
                  title="Gerak naik"
                  style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 3, cursor: idx === 0 ? 'default' : 'pointer', padding: '1px 5px', fontSize: 11, opacity: idx === 0 ? 0.3 : 0.7 }}
                >↑</button>
                <button
                  onClick={() => onReorderChapter(chap.id, 'down')}
                  disabled={idx === chapters.length - 1}
                  title="Gerak turun"
                  style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 3, cursor: idx === chapters.length - 1 ? 'default' : 'pointer', padding: '1px 5px', fontSize: 11, opacity: idx === chapters.length - 1 ? 0.3 : 0.7 }}
                >↓</button>

                {/* Export */}
                {tier === 'pro' && (
                  <button onClick={() => onExport(chap.id)} style={{
                    padding: '2px 7px', fontSize: 10,
                    background: 'transparent', border: '1px solid var(--line)',
                    borderRadius: 3, cursor: 'pointer', fontFamily: 'var(--font-mono)',
                  }}>
                    .docx
                  </button>
                )}

                {/* Padam */}
                <button
                  onClick={e => handleDelete(e, chap)}
                  style={{
                    marginLeft: 'auto', background: 'none', border: 'none',
                    cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 14, padding: '1px 4px',
                  }}
                >×</button>
              </div>
            </div>
          )
        })}

        {/* Form tambah bab baru */}
        {addMode && (
          <form onSubmit={handleAdd} style={{ padding: '8px 12px', borderTop: '1px solid var(--line)' }}>
            <input
              autoFocus
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              placeholder="Nama bab (cth: Bab 1: Pengenalan)"
              style={{
                width: '100%', padding: '6px 8px', boxSizing: 'border-box',
                border: '1px solid var(--accent)', borderRadius: 4,
                fontFamily: 'var(--font-body)', fontSize: 13, outline: 'none',
                background: 'var(--bg)',
              }}
            />
            <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
              <button type="submit" disabled={!newTitle.trim()} style={{
                flex: 1, padding: '5px 0', background: 'var(--accent)', border: 'none',
                borderRadius: 4, fontFamily: 'var(--font-body)', fontSize: 12, cursor: 'pointer',
              }}>Tambah</button>
              <button type="button" onClick={() => { setAddMode(false); setNewTitle('') }} style={{
                padding: '5px 10px', background: 'transparent', border: '1px solid var(--line)',
                borderRadius: 4, fontFamily: 'var(--font-body)', fontSize: 12, cursor: 'pointer',
              }}>Batal</button>
            </div>
          </form>
        )}
      </div>

      {!addMode && (
        <div style={{ padding: 12, borderTop: '1px solid var(--line)' }}>
          <button
            onClick={() => setAddMode(true)}
            style={{
              width: '100%', padding: '7px 0',
              background: 'var(--accent-soft)', border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)',
              fontSize: 13, cursor: 'pointer', color: 'var(--ink)',
            }}
          >+ Tambah Bab</button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SourcePanel.jsx frontend/src/components/ThesisPanel.jsx
git commit -m "feat(ui): SourcePanel collapsible+delete, ThesisPanel navigator with Add/Delete/Reorder"
```

---

## Task 5: ProjectPage.jsx — Desktop Restructure

**Files:**
- Modify: `frontend/src/pages/ProjectPage.jsx`

**Interfaces:**
- Consumes: semua komponen dari Task 2, 3, 4
- New state: `activeChapterId`, `activeChapterContent`, `contentLoading`, `pendingSuggestion`, `sourceCollapsed`, `saving`

- [ ] **Step 1: Rewrite ProjectPage.jsx dengan layout baru**

Replace keseluruhan `frontend/src/pages/ProjectPage.jsx`:

```jsx
import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { ProfileMenu } from '../components/ProfileMenu'
import { SourcePanel } from '../components/SourcePanel'
import { ThesisPanel } from '../components/ThesisPanel'
import { ChapterEditor } from '../components/ChapterEditor'
import { ChatPanel } from '../components/ChatPanel'
import api from '../api/client'
import { extractPdfPages } from '../utils/pdfExtract'
import { useMediaQuery } from '../hooks/useMediaQuery'

export function ProjectPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const [project, setProject] = useState(null)
  const [messages, setMessages] = useState([])
  const [documents, setDocuments] = useState([])
  const [chapters, setChapters] = useState([])
  const [query, setQuery] = useState('')
  const [outputMode, setOutputMode] = useState('qa')
  const [loading, setLoading] = useState(false)
  const [credits, setCredits] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)

  // Editor state
  const [activeChapterId, setActiveChapterId] = useState(null)
  const [activeChapterContent, setActiveChapterContent] = useState('')
  const [contentLoading, setContentLoading] = useState(false)
  const [pendingSuggestion, setPendingSuggestion] = useState(null) // { text: string } | null

  // Layout state
  const [sourceCollapsed, setSourceCollapsed] = useState(false)

  // Mobile state
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [mobileView, setMobileView] = useState('editor') // 'editor' | 'chat'
  const [drawerOpen, setDrawerOpen] = useState(false) // source + navigator drawer

  const fileRef = useRef()
  const bottomRef = useRef()
  const user = JSON.parse(localStorage.getItem('rhq_user') || '{}')

  useEffect(() => {
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/projects/${id}/messages`),
      api.get('/credits'),
      api.get(`/documents?project_id=${id}`),
      api.get(`/projects/${id}/chapters`),
    ]).then(([p, m, c, docs, chaps]) => {
      setProject(p.data)
      setMessages(m.data)
      setCredits(c.data)
      setDocuments(docs.data)
      setChapters(chaps.data)
    }).catch(() => nav('/'))
  }, [id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Fetch chapter content bila active chapter bertukar
  useEffect(() => {
    if (!activeChapterId) {
      setActiveChapterContent('')
      return
    }
    setContentLoading(true)
    api.get(`/projects/${id}/chapters/${activeChapterId}`)
      .then(r => setActiveChapterContent(r.data.content || ''))
      .catch(() => setActiveChapterContent(''))
      .finally(() => setContentLoading(false))
  }, [activeChapterId, id])

  function handleSetActive(chapterId) {
    if (pendingSuggestion && chapterId !== activeChapterId) {
      if (!window.confirm('Ada cadangan AI yang belum disimpan. Tukar bab sekarang akan buang cadangan ini.')) return
      setPendingSuggestion(null)
    }
    setActiveChapterId(chapterId)
  }

  async function handleQuery(e) {
    e.preventDefault()
    if (!query.trim() || loading) return
    const q = query
    setQuery('')
    setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: q, id: Date.now() }])
    try {
      const { data } = await api.post(`/projects/${id}/query`, {
        query: q, output_mode: outputMode, query_type: 'normal'
      })
      setMessages(prev => [...prev, {
        role: 'assistant', content: data.answer,
        sources: data.sources, kredit_used: data.kredit_used,
        id: Date.now() + 1
      }])
      setCredits(prev => prev ? { ...prev, kredit_remaining: data.kredit_remaining } : prev)
    } catch (err) {
      const msg = err.response?.data?.detail || 'Ralat berlaku. Cuba lagi.'
      setMessages(prev => [...prev, { role: 'error', content: msg, id: Date.now() + 1 }])
    }
    setLoading(false)
  }

  async function handleFileUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    if (file.type !== 'application/pdf') {
      alert('Sila muat naik fail PDF sahaja.')
      fileRef.current.value = ''
      return
    }
    setUploading(true)
    try {
      const pages = await extractPdfPages(file)
      const { data } = await api.post('/documents/upload', {
        project_id: id, filename: file.name, category: 'artikel', pages,
      })
      setDocuments(prev => [...prev, data])
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal proses dokumen. Cuba lagi.')
    }
    setUploading(false)
    fileRef.current.value = ''
  }

  async function handleDeleteDoc(docId) {
    try {
      await api.delete(`/documents/${docId}`)
      setDocuments(prev => prev.filter(d => d.id !== docId))
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal padam dokumen. Cuba lagi.')
    }
  }

  async function handleAddChapter(title) {
    const nextOrder = chapters.length > 0 ? Math.max(...chapters.map(c => c.chapter_order)) + 1 : 1
    try {
      const { data } = await api.post(`/projects/${id}/chapters`, { title, chapter_order: nextOrder })
      setChapters(prev => [...prev, data])
      setActiveChapterId(data.id)
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal tambah bab. Cuba lagi.')
    }
  }

  async function handleDeleteChapter(chapterId) {
    try {
      await api.delete(`/projects/${id}/chapters/${chapterId}`)
      setChapters(prev => prev.filter(c => c.id !== chapterId))
      if (activeChapterId === chapterId) {
        setActiveChapterId(null)
        setPendingSuggestion(null)
      }
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal padam bab. Cuba lagi.')
    }
  }

  async function handleReorderChapter(chapterId, direction) {
    const sorted = [...chapters].sort((a, b) => a.chapter_order - b.chapter_order)
    const idx = sorted.findIndex(c => c.id === chapterId)
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1
    if (swapIdx < 0 || swapIdx >= sorted.length) return

    const curr = sorted[idx]
    const swap = sorted[swapIdx]
    const newOrderCurr = swap.chapter_order
    const newOrderSwap = curr.chapter_order

    try {
      await Promise.all([
        api.patch(`/projects/${id}/chapters/${curr.id}`, { chapter_order: newOrderCurr }),
        api.patch(`/projects/${id}/chapters/${swap.id}`, { chapter_order: newOrderSwap }),
      ])
      setChapters(prev => prev.map(c => {
        if (c.id === curr.id) return { ...c, chapter_order: newOrderCurr }
        if (c.id === swap.id) return { ...c, chapter_order: newOrderSwap }
        return c
      }))
    } catch (err) {
      alert('Gagal susun semula bab. Cuba lagi.')
    }
  }

  async function handleAcceptSuggestion(text) {
    if (!activeChapterId) return
    setSaving(true)
    try {
      await api.patch(`/projects/${id}/chapters/${activeChapterId}/content`, { content: text })
      setActiveChapterContent(text)
      setChapters(prev => prev.map(c =>
        c.id === activeChapterId ? { ...c, status: 'dalam_proses' } : c
      ))
      setPendingSuggestion(null)
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal simpan cadangan. Cuba lagi.')
    }
    setSaving(false)
  }

  async function handleSaveContent(text) {
    if (!activeChapterId) return
    setSaving(true)
    try {
      await api.patch(`/projects/${id}/chapters/${activeChapterId}/content`, { content: text })
      setActiveChapterContent(text)
      setChapters(prev => prev.map(c =>
        c.id === activeChapterId ? { ...c, status: 'dalam_proses' } : c
      ))
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal simpan kandungan. Cuba lagi.')
    }
    setSaving(false)
  }

  async function handleExport(chapterId) {
    alert('Export .docx untuk bab ini akan tersedia tidak lama lagi.')
  }

  if (!project) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: 'var(--ink-soft)' }}>Memuatkan...</p>
    </div>
  )

  const activeChapter = chapters.find(c => c.id === activeChapterId) || null
  const sortedChapters = [...chapters].sort((a, b) => a.chapter_order - b.chapter_order)

  // ── MOBILE LAYOUT ──────────────────────────────────────────────
  if (isMobile) {
    return (
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
        {/* Header */}
        <header style={{
          borderBottom: '1px solid var(--line)', padding: '0 16px',
          height: 52, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'var(--card)', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => nav('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 18 }}>←</button>
            <Logo size="sm" />
            <button
              onClick={() => setDrawerOpen(true)}
              title="Buka panel Sumber & Struktur"
              style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 4, cursor: 'pointer', padding: '4px 8px', fontSize: 12, color: 'var(--ink-soft)' }}
            >☰ Sumber</button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {credits && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: credits.kredit_remaining < 10 ? '#EF4444' : 'var(--ink-soft)' }}>
                {credits.kredit_remaining} kr
              </span>
            )}
            <ProfileMenu user={user} tier={credits?.tier} />
          </div>
        </header>

        {/* Mobile toggle bar */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', background: 'var(--card)', flexShrink: 0 }}>
          {[
            { key: 'editor', label: activeChapter ? activeChapter.title.slice(0, 20) + (activeChapter.title.length > 20 ? '…' : '') : 'Editor' },
            { key: 'chat', label: 'Chat AI' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setMobileView(tab.key)}
              style={{
                flex: 1, padding: '10px 0',
                background: mobileView === tab.key ? 'var(--ink)' : 'transparent',
                color: mobileView === tab.key ? 'var(--bg)' : 'var(--ink-soft)',
                border: 'none', fontFamily: 'var(--font-body)', fontSize: 13,
                cursor: 'pointer', borderBottom: mobileView === tab.key ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Mobile views */}
        <input type="file" ref={fileRef} onChange={handleFileUpload} accept=".pdf" style={{ display: 'none' }} />

        <div style={{ flex: 1, overflow: 'hidden' }}>
          {mobileView === 'editor' && (
            <ChapterEditor
              chapter={activeChapter}
              content={contentLoading ? '' : activeChapterContent}
              pendingSuggestion={pendingSuggestion}
              onAccept={handleAcceptSuggestion}
              onReject={() => setPendingSuggestion(null)}
              onSave={handleSaveContent}
              saving={saving}
            />
          )}
          {mobileView === 'chat' && (
            <ChatPanel
              messages={messages} loading={loading}
              query={query} onQueryChange={setQuery}
              onSubmit={handleQuery}
              outputMode={outputMode} onOutputModeChange={setOutputMode}
              credits={credits}
              onSendToEditor={text => { setPendingSuggestion({ text }); setMobileView('editor') }}
              hasActiveChapter={!!activeChapterId}
              bottomRef={bottomRef}
            />
          )}
        </div>

        {/* Drawer — Source + Navigator */}
        {drawerOpen && (
          <>
            <div
              onClick={() => setDrawerOpen(false)}
              style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 40 }}
            />
            <div style={{
              position: 'fixed', top: 0, left: 0, bottom: 0, width: 280,
              background: 'var(--card)', zIndex: 50, display: 'flex', flexDirection: 'column',
              overflowY: 'auto',
            }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15 }}>Sumber & Struktur</span>
                <button onClick={() => setDrawerOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--ink-soft)' }}>×</button>
              </div>
              {/* SourcePanel inlined for drawer */}
              <SourcePanel
                documents={documents}
                onUpload={() => { fileRef.current?.click(); setDrawerOpen(false) }}
                tier={credits?.tier ?? user?.tier}
                uploading={uploading}
                collapsed={false}
                onToggleCollapse={() => {}}
                onDeleteDoc={handleDeleteDoc}
              />
              <div style={{ borderTop: '2px solid var(--line)' }} />
              <ThesisPanel
                chapters={sortedChapters}
                onExport={handleExport}
                tier={credits?.tier ?? user?.tier}
                projectId={id}
                activeChapterId={activeChapterId}
                onSetActive={ch => { handleSetActive(ch); setDrawerOpen(false); setMobileView('editor') }}
                onAddChapter={handleAddChapter}
                onDeleteChapter={handleDeleteChapter}
                onReorderChapter={handleReorderChapter}
              />
            </div>
          </>
        )}
      </div>
    )
  }

  // ── DESKTOP LAYOUT ─────────────────────────────────────────────
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <header style={{
        borderBottom: '1px solid var(--line)', padding: '0 24px',
        height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'var(--card)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={() => nav('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 18 }}>←</button>
          <Logo size="sm" />
          <span style={{ color: 'var(--line)' }}>|</span>
          <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16 }}>{project.title}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {credits && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: credits.kredit_remaining < 10 ? '#EF4444' : 'var(--ink-soft)' }}>
              {credits.kredit_remaining} kredit
            </span>
          )}
          <ProfileMenu user={user} tier={credits?.tier} />
        </div>
      </header>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <input type="file" ref={fileRef} onChange={handleFileUpload} accept=".pdf" style={{ display: 'none' }} />

        {/* Source sidebar — collapsible */}
        <SourcePanel
          documents={documents}
          onUpload={() => fileRef.current?.click()}
          tier={credits?.tier ?? user?.tier}
          uploading={uploading}
          collapsed={sourceCollapsed}
          onToggleCollapse={() => setSourceCollapsed(c => !c)}
          onDeleteDoc={handleDeleteDoc}
        />

        {/* ChapterEditor — main pane */}
        <ChapterEditor
          chapter={activeChapter}
          content={contentLoading ? '' : activeChapterContent}
          pendingSuggestion={pendingSuggestion}
          onAccept={handleAcceptSuggestion}
          onReject={() => setPendingSuggestion(null)}
          onSave={handleSaveContent}
          saving={saving}
        />

        {/* Chat — right sidebar */}
        <div style={{ width: 320, flexShrink: 0, borderLeft: '1px solid var(--line)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <ChatPanel
            messages={messages} loading={loading}
            query={query} onQueryChange={setQuery}
            onSubmit={handleQuery}
            outputMode={outputMode} onOutputModeChange={setOutputMode}
            credits={credits}
            onSendToEditor={text => setPendingSuggestion({ text })}
            hasActiveChapter={!!activeChapterId}
            bottomRef={bottomRef}
          />
        </div>

        {/* Thesis navigator — far right */}
        <ThesisPanel
          chapters={sortedChapters}
          onExport={handleExport}
          tier={credits?.tier ?? user?.tier}
          projectId={id}
          activeChapterId={activeChapterId}
          onSetActive={handleSetActive}
          onAddChapter={handleAddChapter}
          onDeleteChapter={handleDeleteChapter}
          onReorderChapter={handleReorderChapter}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Run backend test suite — verify zero regression**

```bash
cd /home/astro/claude-project/researcherhq/backend
python -m pytest --tb=short 2>&1 | tail -10
```

Expected: `101 passed, 3 deselected` (atau lebih — tiada fail baru).

- [ ] **Step 3: Start dev server dan verify secara visual**

```bash
cd /home/astro/claude-project/researcherhq/frontend
npm run dev &
```

Semak dalam browser (http://localhost:5173):

**Desktop checks:**
- [ ] Source panel ada (260px), boleh collapse jadi sliver (36px), boleh expand semula
- [ ] ChapterEditor pane tengah — tunjuk "Pilih bab" bila tiada active
- [ ] ThesisPanel kanan — senarai bab, "Tambah Bab" button
- [ ] Chat jadi right sidebar (320px), ada "→ Hantar ke Editor" per AI message
- [ ] Klik bab → Editor tunjuk kandungan bab
- [ ] Klik "→ Hantar ke Editor" pada AI answer → suggestion mode muncul dengan "Terima" / "Tolak"
- [ ] "Terima" → content simpan, ChapterEditor kembali ke edit mode
- [ ] "Tolak" → cadangan hilang, content asal kekal
- [ ] First-time tooltip muncul bila suggestion pertama kali
- [ ] Tiada font monospace / dark-theme dalam editor body

**Desktop negative checks:**
- [ ] Refresh browser selepas "Terima" → content kekal (confirmed DB save)
- [ ] Padam dokumen → confirm dialog → hilang dari senarai
- [ ] Tambah bab → muncul dalam navigator, set as active
- [ ] Padam bab → confirm dialog → hilang, editor reset
- [ ] Reorder bab ↑↓ → susunan berubah

**Mobile checks (Chrome DevTools, 375px):**
- [ ] Toggle "Editor" / "Chat AI" → full-screen switch, lancar
- [ ] "☰ Sumber" → drawer slide dari kiri
- [ ] Klik bab dalam drawer → drawer tutup, Editor muncul dengan bab terpilih
- [ ] Chat "→ Hantar ke Editor" → switch ke Editor view dengan cadangan
- [ ] State chat history kekal selepas switch ke Editor dan balik semula

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ProjectPage.jsx
git commit -m "feat(ui): restructure ProjectPage — Editor-centric layout, Terima/Tolak suggestions, mobile drawer"
```

---

## Acceptance Criteria Checklist

### Desktop

- [ ] **AC1:** Padam dokumen → confirm dialog → hilang dari Source, query cache invalidated (test: tanya soalan rujuk dokumen tu → jawapan "tiada sumber")
- [ ] **AC2:** Tambah/padam/reorder bab → navigator update betul, tiada orphan chapter_content (verify dalam DB: `SELECT * FROM chapter_content cc LEFT JOIN chapters ch ON ch.id = cc.chapter_id WHERE ch.id IS NULL`)
- [ ] **AC3:** Chat AI answer → klik "→ Hantar ke Editor" → cadangan muncul dalam ChapterEditor (bukan terus ke DB)
- [ ] **AC4:** Klik Terima → chapter_content updated dalam DB, refresh browser, content kekal
- [ ] **AC5:** Klik Tolak → cadangan hilang, chapter_content asal tak berubah, verify: `SELECT content FROM chapter_content WHERE chapter_id=?`
- [ ] **AC6:** Visual check — tiada `font-family: monospace` dalam editor body, tiada `background: #1e1e1e` atau dark theme

### Mobile (<768px, Chrome DevTools)

- [ ] **AC1:** Editor full-screen, toggle ke Chat — tiada layout break, full viewport used
- [ ] **AC2:** "☰ Sumber" → drawer terbuka, Source + navigator accessible, tutup drawer → state kekal
- [ ] **AC3:** Chat history kekal selepas switch antara Editor / Chat view
- [ ] **AC4:** pendingSuggestion kekal bila switch dari Chat ke Editor view
- [ ] **AC5:** Desktop (>768px) — zero regresi, semua AC Desktop masih pass

### Regression

- [ ] **AC1:** Backend test suite: `python -m pytest --tb=short` → `101 passed, 3 deselected` (min)

---

## Flags & Keputusan yang Perlu Bos Sign-off

1. **"Hantar ke Editor" explicit button** — Setiap AI answer ada butang kecil "→ Hantar ke Editor". Jika Bos mahu auto-suggestion untuk mode tertentu (cth: `literature_review` auto-jadi cadangan), beritahu — boleh tambah selepas ini.

2. **Chat sebagai sidebar 320px** — Desktop layout: Source (collapsible 260px) | Editor (flex) | Chat (320px) | Navigator (260px). Total 4 kolum. Jika screen kecil (laptop 1280px) rasa sesak, chat width boleh dikurangkan ke 280px atau collapsed by default.

3. **pendingSuggestion frontend-only** — Cadangan AI tidak survive page refresh. Jika user reload semasa ada cadangan pending, cadangan hilang (content asal kekal). Ini intentional mengikut spec. Jika Bos rasa perlu persist, akan kena tambah DB table — tanya dulu.

4. **Reorder logic** — Swap `chapter_order` antara dua bab bersebelahan. Jika dua bab ada `chapter_order` yang sama (edge case dari data lama), swap mungkin nampak pelik. Ini edge case yang sangat rare.
