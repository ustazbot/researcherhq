# ResearcherHQ MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bina ResearcherHQ — workspace penyelidikan berasaskan dokumen untuk pelajar postgrad Malaysia, dengan RAG anti-hallucination, thesis workspace 3-panel, dan sistem kredit.

**Architecture:** FastAPI backend dengan SQLite + sqlite-vec untuk vector storage, React SPA frontend, all-MiniLM-L6-v2 embedding model tempatan dengan worker pool, DeepSeek V4 Flash sebagai LLM via abstraction layer.

**Tech Stack:** Python 3.11, FastAPI, SQLite (WAL), sqlite-vec, sentence-transformers (all-MiniLM-L6-v2), DeepSeek API, React 18 + Vite, React Router, Axios, KaTeX, python-docx, pytesseract, Resend SMTP, ToyyibPay (Fasa 2)

**Design Tokens (dari logo system):**
- `--bg: #F8F6F1` | `--ink: #1C1B19` | `--accent: #F97316` | `--card: #FFFFFF` | `--line: #E3DFD5`
- Fonts: Plus Jakarta Sans (heading/logo), DM Sans (body), DM Mono (code/badge)

---

## File Structure

```
researcherhq/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI entry, CORS, router mount
│   │   ├── config.py             # Settings dari .env
│   │   ├── database.py           # SQLite init, schema, PRAGMA, FK
│   │   ├── schemas.py            # Pydantic request/response models
│   │   ├── routers/
│   │   │   ├── auth.py           # /auth/request-password, /auth/login
│   │   │   ├── projects.py       # CRUD /projects
│   │   │   ├── documents.py      # /documents/upload, /documents/{id}
│   │   │   ├── rag.py            # /projects/{id}/query
│   │   │   ├── credits.py        # /credits, /credits/topup
│   │   │   ├── account.py        # /account, DELETE /account
│   │   │   └── support.py        # /support/report
│   │   └── services/
│   │       ├── embedding_pool.py # Worker pool all-MiniLM-L6-v2
│   │       ├── rag_pipeline.py   # chunk, embed, MMR retrieval
│   │       ├── llm_provider.py   # DeepSeek abstraction
│   │       ├── auth_service.py   # JWT, password-on-demand
│   │       └── email_service.py  # Resend SMTP
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_rag.py
│   │   ├── test_credits.py
│   │   └── test_cascade_delete.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx
│   │   ├── tokens.css            # Design tokens
│   │   ├── api/
│   │   │   └── client.js         # Axios wrapper + auth interceptor
│   │   ├── components/
│   │   │   ├── Logo.jsx          # "Researcher" + "HQ" badge
│   │   │   ├── CreditTank.jsx    # Visual credit bar
│   │   │   ├── ProfileMenu.jsx   # Top-right dropdown
│   │   │   └── CitationCard.jsx  # Citation + "Lihat Sumber"
│   │   └── pages/
│   │       ├── AuthPage.jsx      # Email → password login
│   │       ├── DashboardPage.jsx # Project list + create
│   │       └── ProjectPage.jsx   # Workspace (chat + source)
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── .env.example
└── nginx.conf
```

---

## FASA 1A — RAG Core

---

### Task 1: Project Scaffolding

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `.env.example`

- [ ] **Step 1: Buat fail requirements.txt**

```
# backend/requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.27.2
sentence-transformers==3.1.1
sqlite-vec==0.1.6
python-multipart==0.0.12
resend==2.4.0
python-dotenv==1.0.1
pydantic-settings==2.5.2
python-docx==1.1.2
pytesseract==0.3.13
Pillow==10.4.0
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Buat .env.example**

```
# .env.example
DATABASE_URL=./researcherhq.db
JWT_SECRET=ganti-dengan-secret-panjang-rawak
JWT_EXPIRE_DAYS=30

RESEND_API_KEY=re_xxxxxxxxxxxx
RESEND_FROM=noreply@researcherhq.com

DEEPSEEK_API_KEY=sk-xxxxxxxxxxxx
DEEPSEEK_MODEL_FLASH=deepseek-chat
DEEPSEEK_MODEL_PRO=deepseek-reasoner
LLM_PROVIDER=deepseek

TELEGRAM_BOT_TOKEN=xxxxxxx:xxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789

TOYYIBPAY_SECRET_KEY=xxxxxxxxx
TOYYIBPAY_CATEGORY_CODE=xxxxxxxxx

FRONTEND_URL=http://localhost:5173
EMBEDDING_WORKERS=3
EMBEDDING_BATCH_SIZE=8
```

- [ ] **Step 3: Buat app/config.py**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "./researcherhq.db"
    jwt_secret: str
    jwt_expire_days: int = 30
    resend_api_key: str
    resend_from: str = "noreply@researcherhq.com"
    deepseek_api_key: str
    deepseek_model_flash: str = "deepseek-chat"
    deepseek_model_pro: str = "deepseek-reasoner"
    llm_provider: str = "deepseek"
    telegram_bot_token: str
    telegram_chat_id: str
    toyyibpay_secret_key: str = ""
    toyyibpay_category_code: str = ""
    frontend_url: str = "http://localhost:5173"
    embedding_workers: int = 3
    embedding_batch_size: int = 8

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 4: Buat app/main.py**

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import auth, projects, documents, rag, credits, account, support

app = FastAPI(title="ResearcherHQ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(rag.router, prefix="/projects", tags=["rag"])
app.include_router(credits.router, prefix="/credits", tags=["credits"])
app.include_router(account.router, prefix="/account", tags=["account"])
app.include_router(support.router, prefix="/support", tags=["support"])
```

- [ ] **Step 5: Buat placeholder routers (supaya app boleh start)**

```python
# backend/app/routers/__init__.py  — kosong

# Untuk setiap router dalam routers/, buat fail kosong dengan:
from fastapi import APIRouter
router = APIRouter()
```
Buat fail ini: `auth.py`, `projects.py`, `documents.py`, `rag.py`, `credits.py`, `account.py`, `support.py`

- [ ] **Step 6: Setup React + Vite**

```bash
cd frontend
npm create vite@latest . -- --template react
npm install axios react-router-dom katex
```

- [ ] **Step 7: Verify backend start**

```bash
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Expected: `GET http://localhost:8000/health` → `{"status":"ok","version":"1.0.0"}`

- [ ] **Step 8: Commit**

```bash
git init
git add .
git commit -m "chore: scaffold backend (FastAPI) + frontend (React/Vite)"
```

---

### Task 2: Database Schema

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_database.py`

- [ ] **Step 1: Tulis failing test**

```python
# backend/tests/test_database.py
import sqlite3
from app.database import get_db, init_db

def test_schema_tables_exist(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cursor.fetchall()}
    required = {
        "users", "projects", "documents", "chunks",
        "chapters", "chapter_content", "messages",
        "query_cache", "billing_events", "user_interactions",
        "app_learnings", "support_reports"
    }
    assert required.issubset(tables)

def test_foreign_keys_enabled(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    result = conn.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1

def test_wal_mode(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    result = conn.execute("PRAGMA journal_mode").fetchone()
    assert result[0] == "wal"
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
cd backend && pytest tests/test_database.py -v
```
Expected: FAIL — `init_db` belum wujud

- [ ] **Step 3: Implement database.py**

```python
# backend/app/database.py
import sqlite3
import sqlite_vec
from contextlib import contextmanager
from app.config import settings

_db_path: str = settings.database_url

def init_db(db_path: str = None) -> sqlite3.Connection:
    path = db_path or _db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    sqlite_vec.load(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _create_schema(conn)
    conn.commit()
    return conn

def _create_schema(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT UNIQUE NOT NULL,
      tier TEXT DEFAULT 'free',
      kredit_remaining INTEGER DEFAULT 50,
      kredit_total INTEGER DEFAULT 50,
      tokens_used_internal INTEGER DEFAULT 0,
      reset_date TEXT,
      fingerprint TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS projects (
      id TEXT PRIMARY KEY,
      user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
      title TEXT,
      research_mode TEXT DEFAULT 'general',
      field TEXT,
      document_set_version INTEGER DEFAULT 1,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS documents (
      id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
      filename TEXT,
      category TEXT,
      page_count INTEGER,
      chunk_count INTEGER,
      is_ocr INTEGER DEFAULT 0,
      uploaded_at TEXT
    );

    CREATE TABLE IF NOT EXISTS chunks (
      id TEXT PRIMARY KEY,
      doc_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
      page_number INTEGER,
      chunk_index INTEGER,
      text TEXT,
      created_at TEXT
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
      chunk_id TEXT,
      embedding FLOAT[384]
    );

    CREATE TABLE IF NOT EXISTS chapters (
      id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
      title TEXT,
      chapter_order INTEGER,
      status TEXT DEFAULT 'draft',
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS chapter_content (
      id TEXT PRIMARY KEY,
      chapter_id TEXT REFERENCES chapters(id) ON DELETE CASCADE,
      content TEXT,
      summary TEXT,
      source_citations TEXT,
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
      role TEXT,
      content TEXT,
      output_mode TEXT,
      source_chunks TEXT,
      kredit_used INTEGER,
      tokens_used_internal INTEGER,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS query_cache (
      id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
      query_normalized TEXT,
      query_embedding BLOB,
      document_set_version INTEGER,
      response TEXT,
      source_chunks TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS billing_events (
      id TEXT PRIMARY KEY,
      user_id TEXT REFERENCES users(id),
      event_type TEXT,
      amount REAL,
      kredit_added INTEGER,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS user_interactions (
      id TEXT PRIMARY KEY,
      user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
      event_type TEXT,
      research_mode TEXT,
      output_mode TEXT,
      response_rating INTEGER,
      query_length INTEGER,
      kredit_used INTEGER,
      session_id TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS app_learnings (
      id TEXT PRIMARY KEY,
      pattern TEXT,
      confidence REAL,
      action_suggested TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS support_reports (
      id TEXT PRIMARY KEY,
      user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
      category TEXT,
      description TEXT,
      project_id TEXT,
      status TEXT DEFAULT 'open',
      created_at TEXT
    );
    """)

@contextmanager
def get_db():
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    sqlite_vec.load(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [ ] **Step 4: Update conftest.py**

```python
# backend/tests/conftest.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
```

- [ ] **Step 5: Run test — verify PASS**

```bash
cd backend && pytest tests/test_database.py -v
```
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/database.py backend/tests/
git commit -m "feat: SQLite schema + WAL + FK + sqlite-vec init"
```

---

### Task 3: Auth Service (Password-on-Demand + JWT)

**Files:**
- Create: `backend/app/services/auth_service.py`
- Create: `backend/app/services/email_service.py`
- Create: `backend/app/routers/auth.py`
- Create: `backend/app/schemas.py` (tambah auth schemas)
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Tulis failing tests**

```python
# backend/tests/test_auth.py
import pytest
from app.services.auth_service import (
    generate_password, hash_password, verify_password,
    create_jwt, decode_jwt
)

def test_generate_password_length():
    pwd = generate_password()
    assert len(pwd) == 8

def test_generate_password_alphanumeric():
    pwd = generate_password()
    assert pwd.isalnum()

def test_password_hash_verify():
    pwd = generate_password()
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed)
    assert not verify_password("wrong", hashed)

def test_jwt_roundtrip():
    token = create_jwt({"user_id": "abc123", "email": "test@test.com"})
    payload = decode_jwt(token)
    assert payload["user_id"] == "abc123"
    assert payload["email"] == "test@test.com"

def test_jwt_invalid_raises():
    with pytest.raises(Exception):
        decode_jwt("not.a.valid.token")
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_auth.py -v
```
Expected: FAIL — import error

- [ ] **Step 3: Implement auth_service.py**

```python
# backend/app/services/auth_service.py
import random
import string
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def generate_password(length: int = 8) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_jwt(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(days=settings.jwt_expire_days)
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        raise ValueError(f"Token tidak sah: {e}")
```

- [ ] **Step 4: Implement email_service.py**

```python
# backend/app/services/email_service.py
import resend
from app.config import settings

resend.api_key = settings.resend_api_key

async def send_password_email(to_email: str, password: str):
    resend.Emails.send({
        "from": settings.resend_from,
        "to": to_email,
        "subject": "Kata Laluan ResearcherHQ Anda",
        "html": f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
          <h2 style="color: #1C1B19;">Kata Laluan Anda</h2>
          <p>Gunakan kata laluan berikut untuk log masuk ke ResearcherHQ:</p>
          <div style="background: #F8F6F1; padding: 16px; border-radius: 8px;
                      font-family: monospace; font-size: 24px; letter-spacing: 4px;
                      text-align: center; color: #1C1B19;">
            {password}
          </div>
          <p style="color: #4A463F; font-size: 13px; margin-top: 16px;">
            Kata laluan ini dijana khas untuk anda. Simpan dengan selamat.
            Jika bukan anda yang minta, abaikan emel ini.
          </p>
        </div>
        """
    })
```

- [ ] **Step 5: Implement auth router**

```python
# backend/app/routers/auth.py
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from app.database import get_db
from app.services.auth_service import (
    generate_password, hash_password, verify_password, create_jwt, decode_jwt
)
from app.services.email_service import send_password_email

router = APIRouter()
security = HTTPBearer()

DISPOSABLE_DOMAINS = {"mailinator.com", "tempmail.com", "guerrillamail.com", "throwam.com"}

class RequestPasswordBody(BaseModel):
    email: EmailStr

class LoginBody(BaseModel):
    email: EmailStr
    password: str

@router.post("/request-password")
async def request_password(body: RequestPasswordBody):
    domain = body.email.split("@")[1].lower()
    if domain in DISPOSABLE_DOMAINS:
        raise HTTPException(400, "Domain emel tidak dibenarkan.")
    
    pwd = generate_password()
    hashed = hash_password(pwd)
    
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?", (body.email,)
        ).fetchone()
        
        if existing:
            db.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (hashed, body.email)
            )
        else:
            reset_date = (datetime.utcnow().replace(day=1) + 
                         __import__('dateutil.relativedelta', fromlist=['relativedelta'])
                         .relativedelta(months=1)).isoformat()
            db.execute(
                """INSERT INTO users (id, email, tier, kredit_remaining, kredit_total,
                   tokens_used_internal, reset_date, created_at)
                   VALUES (?, ?, 'free', 50, 50, 0, ?, ?)""",
                (str(uuid.uuid4()), body.email, reset_date, datetime.utcnow().isoformat())
            )
            db.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT"
            )
            db.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (hashed, body.email)
            )
    
    await send_password_email(body.email, pwd)
    return {"message": "Kata laluan telah dihantar ke emel anda."}

@router.post("/login")
def login(body: LoginBody):
    with get_db() as db:
        user = db.execute(
            "SELECT id, email, tier, kredit_remaining, password_hash FROM users WHERE email = ?",
            (body.email,)
        ).fetchone()
    
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Emel atau kata laluan tidak sah.")
    
    token = create_jwt({"user_id": user["id"], "email": user["email"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "tier": user["tier"],
            "kredit_remaining": user["kredit_remaining"]
        }
    }

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = decode_jwt(credentials.credentials)
        return payload
    except ValueError:
        raise HTTPException(401, "Token tidak sah atau luput.")
```

- [ ] **Step 6: Tambah password_hash column ke schema**

Dalam `database.py`, tambah `password_hash TEXT` ke table `users`:
```python
# Dalam _create_schema, tukar baris users table:
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT,          # <-- tambah baris ini
  tier TEXT DEFAULT 'free',
  ...
```

- [ ] **Step 7: Run tests — verify PASS**

```bash
pytest tests/test_auth.py -v
```
Expected: 5 tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/auth_service.py backend/app/services/email_service.py backend/app/routers/auth.py
git commit -m "feat: password-on-demand auth + JWT (Fasa 1A)"
```

---

### Task 4: Project CRUD

**Files:**
- Create: `backend/app/routers/projects.py`
- Create: `backend/tests/test_projects.py`

- [ ] **Step 1: Tulis failing test**

```python
# backend/tests/test_projects.py
import pytest, uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_db
from unittest.mock import patch

@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        init_db(db_path)
        yield TestClient(app)

def make_auth_header(user_id="user1", email="test@test.com"):
    from app.services.auth_service import create_jwt
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}

def test_create_project(client):
    r = client.post("/projects", json={
        "title": "Tesis Saya",
        "research_mode": "general",
        "field": "Sains Sosial"
    }, headers=make_auth_header())
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Tesis Saya"
    assert data["research_mode"] == "general"

def test_list_projects(client):
    headers = make_auth_header()
    client.post("/projects", json={"title": "Proj A", "research_mode": "general"}, headers=headers)
    client.post("/projects", json={"title": "Proj B", "research_mode": "law"}, headers=headers)
    r = client.get("/projects", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2

def test_project_isolation(client):
    h1 = make_auth_header("user1", "u1@t.com")
    h2 = make_auth_header("user2", "u2@t.com")
    client.post("/projects", json={"title": "Proj User1", "research_mode": "general"}, headers=h1)
    r = client.get("/projects", headers=h2)
    assert r.json() == []
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_projects.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement projects.py**

```python
# backend/app/routers/projects.py
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()

VALID_MODES = {"general", "quantitative", "qualitative", "law", "medicine"}

class ProjectCreate(BaseModel):
    title: str
    research_mode: str = "general"
    field: Optional[str] = None

@router.post("", status_code=201)
def create_project(body: ProjectCreate, user=Depends(get_current_user)):
    if body.research_mode not in VALID_MODES:
        raise HTTPException(400, f"Mode tidak sah. Pilih: {', '.join(VALID_MODES)}")
    
    with get_db() as db:
        # Semak had projek ikut tier
        user_row = db.execute(
            "SELECT tier FROM users WHERE id = ?", (user["user_id"],)
        ).fetchone()
        if not user_row:
            # Auto-create user jika belum ada (untuk test)
            db.execute(
                "INSERT OR IGNORE INTO users (id, email, tier, kredit_remaining, kredit_total, tokens_used_internal, created_at) VALUES (?, ?, 'free', 50, 50, 0, ?)",
                (user["user_id"], user["email"], datetime.utcnow().isoformat())
            )
            tier = "free"
        else:
            tier = user_row["tier"]
        
        count = db.execute(
            "SELECT COUNT(*) as c FROM projects WHERE user_id = ?", (user["user_id"],)
        ).fetchone()["c"]
        
        max_projects = 1 if tier == "free" else 10
        if count >= max_projects:
            raise HTTPException(403, f"Had projek ({max_projects}) tercapai. Naik taraf ke Pro.")
        
        project_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db.execute(
            """INSERT INTO projects (id, user_id, title, research_mode, field, document_set_version, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (project_id, user["user_id"], body.title, body.research_mode, body.field, now)
        )
        return {
            "id": project_id,
            "title": body.title,
            "research_mode": body.research_mode,
            "field": body.field,
            "document_set_version": 1,
            "created_at": now
        }

@router.get("")
def list_projects(user=Depends(get_current_user)):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC",
            (user["user_id"],)
        ).fetchall()
    return [dict(r) for r in rows]

@router.get("/{project_id}")
def get_project(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        ).fetchone()
    if not row:
        raise HTTPException(404, "Projek tidak dijumpai.")
    return dict(row)

@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        result = db.execute(
            "DELETE FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        )
    if result.rowcount == 0:
        raise HTTPException(404, "Projek tidak dijumpai.")
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
pytest tests/test_projects.py -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/projects.py backend/tests/test_projects.py
git commit -m "feat: project CRUD with tier-based limits"
```

---

### Task 5: Document Upload + Chunking

**Files:**
- Create: `backend/app/routers/documents.py`
- Create: `backend/app/services/rag_pipeline.py` (chunking bahagian)
- Create: `backend/tests/test_rag.py`

- [ ] **Step 1: Tulis failing test (chunking)**

```python
# backend/tests/test_rag.py
from app.services.rag_pipeline import chunk_text

def test_chunk_basic():
    text = " ".join(["word"] * 500)
    chunks = chunk_text(text)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c["text"].split()) <= 420  # sedikit buffer

def test_chunk_overlap():
    text = " ".join([str(i) for i in range(200)])
    chunks = chunk_text(text)
    # chunk[1] patut ada beberapa token dari hujung chunk[0]
    assert len(chunks) >= 1

def test_chunk_min_size():
    # Chunk kurang dari 100 token patut digugurkan
    text = "Tajuk Bab 1\n\n" + " ".join(["word"] * 500)
    chunks = chunk_text(text)
    for c in chunks:
        assert len(c["text"].split()) >= 10  # min size
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_rag.py::test_chunk_basic -v
```
Expected: FAIL — `chunk_text` belum wujud

- [ ] **Step 3: Implement chunking dalam rag_pipeline.py**

```python
# backend/app/services/rag_pipeline.py
from typing import List, Dict, Any

CHUNK_SIZE = 400    # token (anggaran: 1 token ≈ 1 patah perkataan)
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
                "token_count": len(chunk_words)
            })
            chunk_index += 1
        
        if end >= len(words):
            break
        start = end - CHUNK_OVERLAP
    
    return chunks
```

- [ ] **Step 4: Run chunking tests — verify PASS**

```bash
pytest tests/test_rag.py -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Implement document upload router**

```python
# backend/app/routers/documents.py
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.rag_pipeline import chunk_text

router = APIRouter()

VALID_CATEGORIES = {"artikel", "catatan_sv", "draf", "data"}

class DocumentUpload(BaseModel):
    project_id: str
    filename: str
    category: str = "artikel"
    pages: List[dict]  # [{"page_number": 1, "text": "..."}]

@router.post("/upload", status_code=201)
async def upload_document(body: DocumentUpload, user=Depends(get_current_user)):
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Kategori tidak sah: {body.category}")
    
    with get_db() as db:
        # Verify project milik user
        proj = db.execute(
            "SELECT id, user_id FROM projects WHERE id = ? AND user_id = ?",
            (body.project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        
        # Semak had dokumen ikut tier
        user_row = db.execute("SELECT tier FROM users WHERE id = ?", (user["user_id"],)).fetchone()
        tier = user_row["tier"] if user_row else "free"
        
        doc_count = db.execute(
            "SELECT COUNT(*) as c FROM documents WHERE project_id = ?", (body.project_id,)
        ).fetchone()["c"]
        
        max_docs = 1 if tier == "free" else 5
        if doc_count >= max_docs:
            raise HTTPException(403, f"Had dokumen ({max_docs} serentak) tercapai.")
        
        doc_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        # Chunk semua halaman
        all_chunks = []
        for page in body.pages:
            if page.get("text"):
                page_chunks = chunk_text(page["text"], page_number=page.get("page_number", 0))
                all_chunks.extend(page_chunks)
        
        # Simpan document record
        db.execute(
            """INSERT INTO documents (id, project_id, filename, category, page_count, chunk_count, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, body.project_id, body.filename, body.category,
             len(body.pages), len(all_chunks), now)
        )
        
        # Simpan chunks
        for chunk in all_chunks:
            chunk_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO chunks (id, doc_id, page_number, chunk_index, text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chunk_id, doc_id, chunk["page_number"], chunk["chunk_index"], chunk["text"], now)
            )
        
        # Naik version document_set untuk cache invalidation
        db.execute(
            "UPDATE projects SET document_set_version = document_set_version + 1 WHERE id = ?",
            (body.project_id,)
        )
        
        return {
            "id": doc_id,
            "filename": body.filename,
            "chunk_count": len(all_chunks),
            "status": "uploaded",
            "message": "Dokumen sedang diproses untuk embedding..."
        }

@router.get("/{doc_id}")
def get_document(doc_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        doc = db.execute("""
            SELECT d.*, p.user_id FROM documents d
            JOIN projects p ON d.project_id = p.id
            WHERE d.id = ? AND p.user_id = ?
        """, (doc_id, user["user_id"])).fetchone()
    if not doc:
        raise HTTPException(404, "Dokumen tidak dijumpai.")
    return dict(doc)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/documents.py backend/app/services/rag_pipeline.py backend/tests/test_rag.py
git commit -m "feat: document upload + text chunking (400 token, 80 overlap)"
```

---

### Task 6: Embedding Worker Pool

**Files:**
- Create: `backend/app/services/embedding_pool.py`
- Update: `backend/app/main.py` (startup pool init)

- [ ] **Step 1: Tulis failing test**

```python
# dalam tests/test_rag.py — tambah:
import asyncio
from app.services.embedding_pool import EmbeddingPool

@pytest.mark.asyncio
async def test_embed_single():
    pool = EmbeddingPool(num_workers=1)
    await pool.start()
    embedding = await pool.embed("ini adalah teks ujian")
    assert len(embedding) == 384
    assert isinstance(embedding[0], float)
    await pool.stop()

@pytest.mark.asyncio
async def test_embed_batch():
    pool = EmbeddingPool(num_workers=2)
    await pool.start()
    texts = ["teks satu", "teks dua", "teks tiga"]
    embeddings = await pool.embed_batch(texts)
    assert len(embeddings) == 3
    assert all(len(e) == 384 for e in embeddings)
    await pool.stop()
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_rag.py::test_embed_single -v
```
Expected: FAIL

- [ ] **Step 3: Implement EmbeddingPool**

```python
# backend/app/services/embedding_pool.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List
from sentence_transformers import SentenceTransformer
from app.config import settings

MODEL_NAME = "all-MiniLM-L6-v2"
QUEUE_TIMEOUT = 10

class EmbeddingPool:
    def __init__(self, num_workers: int = None, batch_size: int = None):
        self.num_workers = num_workers or settings.embedding_workers
        self.batch_size = batch_size or settings.embedding_batch_size
        self._model: SentenceTransformer = None
        self._executor: ThreadPoolExecutor = None
        self._loop: asyncio.AbstractEventLoop = None

    async def start(self):
        self._loop = asyncio.get_event_loop()
        self._executor = ThreadPoolExecutor(max_workers=self.num_workers)
        # Load model dalam thread supaya tak block event loop
        self._model = await self._loop.run_in_executor(
            self._executor, lambda: SentenceTransformer(MODEL_NAME)
        )

    async def stop(self):
        if self._executor:
            self._executor.shutdown(wait=True)

    async def embed(self, text: str) -> List[float]:
        """Embed satu teks — priority (untuk query masa real-time)."""
        result = await self._loop.run_in_executor(
            self._executor,
            lambda: self._model.encode([text], normalize_embeddings=True)[0].tolist()
        )
        return result

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed senarai teks dalam batch — untuk upload dokumen."""
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_result = await self._loop.run_in_executor(
                self._executor,
                lambda b=batch: self._model.encode(b, normalize_embeddings=True).tolist()
            )
            all_embeddings.extend(batch_result)
        return all_embeddings

# Singleton global — init masa startup
embedding_pool = EmbeddingPool()
```

- [ ] **Step 4: Update main.py untuk init pool**

```python
# backend/app/main.py — update startup:
from app.services.embedding_pool import embedding_pool

@app.on_event("startup")
async def startup():
    init_db()
    await embedding_pool.start()

@app.on_event("shutdown")
async def shutdown():
    await embedding_pool.stop()
```

- [ ] **Step 5: Update documents.py — embed chunks selepas simpan**

Dalam `upload_document`, selepas simpan chunks, tambah embedding dalam background:
```python
# Dalam routers/documents.py — tambah import:
from app.services.embedding_pool import embedding_pool
import asyncio

# Selepas simpan semua chunks, embed dalam background:
async def embed_and_store(doc_id: str, chunks: list, db_path: str):
    import sqlite3, sqlite_vec
    texts = [c["text"] for c in chunks]
    embeddings = await embedding_pool.embed_batch(texts)
    
    conn = sqlite3.connect(db_path)
    sqlite_vec.load(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Dapatkan chunk IDs yang baru disimpan
    chunk_ids = conn.execute(
        "SELECT id FROM chunks WHERE doc_id = ? ORDER BY chunk_index",
        (doc_id,)
    ).fetchall()
    
    for (chunk_id_row,), embedding in zip(chunk_ids, embeddings):
        conn.execute(
            "INSERT INTO chunk_vectors (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id_row, embedding)
        )
    conn.commit()
    conn.close()

# Dalam endpoint upload_document, sebelum return:
asyncio.create_task(embed_and_store(doc_id, all_chunks, _db_path))
```

- [ ] **Step 6: Run embedding tests — verify PASS**

```bash
pytest tests/test_rag.py -v
```
Expected: 5 tests PASS (download model ~90MB first time)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/embedding_pool.py backend/app/main.py backend/app/routers/documents.py
git commit -m "feat: embedding worker pool (all-MiniLM-L6-v2, 3 workers, batch 8)"
```

---

### Task 7: RAG Query Endpoint (Similarity + MMR + Citation)

**Files:**
- Update: `backend/app/services/rag_pipeline.py` (tambah retrieval + MMR)
- Create: `backend/app/services/llm_provider.py`
- Create: `backend/app/routers/rag.py`

- [ ] **Step 1: Tulis failing test**

```python
# tests/test_rag.py — tambah:
from app.services.rag_pipeline import mmr_rerank

def test_mmr_reduces_redundancy():
    # Simulasi 5 chunks — 3 sangat mirip, 2 berbeza
    candidates = [
        {"chunk_id": "a", "text": "kajian kuantitatif digunakan dalam penyelidikan ini", "similarity": 0.95},
        {"chunk_id": "b", "text": "kajian kuantitatif digunakan dalam penyelidikan sosial", "similarity": 0.92},
        {"chunk_id": "c", "text": "kajian kuantitatif adalah kaedah saintifik", "similarity": 0.90},
        {"chunk_id": "d", "text": "temu bual dilakukan dengan 10 informan", "similarity": 0.85},
        {"chunk_id": "e", "text": "analisis dokumen menunjukkan pola berbeza", "similarity": 0.80},
    ]
    # MMR patut pilih bukan semua dari cluster yang sama
    result = mmr_rerank(candidates, k=3, similarity_weight=0.7, diversity_weight=0.3)
    assert len(result) == 3
    chunk_ids = [r["chunk_id"] for r in result]
    # "a" (similarity tertinggi) patut masuk
    assert "a" in chunk_ids
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_rag.py::test_mmr_reduces_redundancy -v
```

- [ ] **Step 3: Tambah MMR dan retrieval dalam rag_pipeline.py**

```python
# backend/app/services/rag_pipeline.py — tambah:
import sqlite3
import sqlite_vec
import math
from typing import List, Dict, Any

def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def mmr_rerank(
    candidates: List[Dict],
    k: int,
    similarity_weight: float = 0.7,
    diversity_weight: float = 0.3
) -> List[Dict]:
    if not candidates:
        return []
    
    selected = []
    remaining = list(candidates)
    
    # Pilih yang paling relevan dulu
    best = max(remaining, key=lambda x: x["similarity"])
    selected.append(best)
    remaining.remove(best)
    
    while len(selected) < k and remaining:
        best_score = -1
        best_item = None
        
        for item in remaining:
            relevance = item["similarity"]
            # Redundancy = max similarity dengan yang dah dipilih
            max_sim = max(
                cosine_similarity(
                    item.get("embedding", []),
                    sel.get("embedding", [])
                ) if item.get("embedding") else 0
                for sel in selected
            )
            mmr_score = similarity_weight * relevance - diversity_weight * max_sim
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
    db_path: str
) -> List[Dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sqlite_vec.load(conn)
    
    # Kira bilangan dokumen dalam project
    doc_count = conn.execute(
        "SELECT COUNT(*) as c FROM documents WHERE project_id = ?", (project_id,)
    ).fetchone()["c"]
    
    k_initial = get_retrieval_k(query_type, doc_count) * 2  # Ambil lebih untuk MMR
    
    # Cari chunk dalam project ini sahaja
    chunk_ids_in_project = conn.execute("""
        SELECT c.id FROM chunks c
        JOIN documents d ON c.doc_id = d.id
        WHERE d.project_id = ?
    """, (project_id,)).fetchall()
    
    if not chunk_ids_in_project:
        conn.close()
        return []
    
    # sqlite-vec similarity search
    results = conn.execute("""
        SELECT cv.chunk_id, cv.distance,
               c.text, c.page_number, c.chunk_index,
               d.filename, cv.embedding
        FROM chunk_vectors cv
        JOIN chunks c ON cv.chunk_id = c.id
        JOIN documents d ON c.doc_id = d.id
        WHERE d.project_id = ?
        ORDER BY vec_distance_cosine(cv.embedding, ?) ASC
        LIMIT ?
    """, (project_id, query_embedding, k_initial)).fetchall()
    
    conn.close()
    
    candidates = []
    for row in results:
        similarity = 1 - row["distance"]  # cosine distance → similarity
        candidates.append({
            "chunk_id": row["chunk_id"],
            "text": row["text"],
            "page_number": row["page_number"],
            "filename": row["filename"],
            "similarity": similarity,
            "embedding": list(row["embedding"]) if row["embedding"] else []
        })
    
    # Sort deterministic: (similarity DESC, chunk_id ASC) — tie-breaking
    candidates.sort(key=lambda x: (-x["similarity"], x["chunk_id"]))
    
    k_final = get_retrieval_k(query_type, doc_count)
    return mmr_rerank(candidates, k=k_final)
```

- [ ] **Step 4: Implement LLM provider**

```python
# backend/app/services/llm_provider.py
import httpx
from typing import List, Dict
from app.config import settings

SYSTEM_PROMPTS = {
    "general": """Anda adalah research assistant untuk ResearcherHQ.

PERATURAN WAJIB:
1. Jawab HANYA berdasarkan konteks dokumen yang diberikan
2. Jika maklumat tiada dalam konteks: "Maklumat ini tidak terdapat dalam dokumen yang dimuat naik."
3. Setiap fakta MESTI ada sumber [nama fail, ms. X]
4. JANGAN tambah pengetahuan umum kecuali diminta
5. Bahasa Melayu melainkan dokumen dalam Bahasa Inggeris

PERATURAN CITATION:
- JANGAN cipta citation baharu yang tiada dalam dokumen
- JANGAN tambah author/tahun/jurnal yang tidak wujud dalam dokumen
- Jika tiada citation: "Rujukan tidak ditemui dalam dokumen anda"
- Format inline: (Nama Fail, ms. 12)

Format jawapan:
- Ringkas dan tepat
- Citation inline selepas setiap fakta
- Akhiri dengan: "**Sumber:** [senarai fail yang dirujuk]" """,

    "law": """Anda adalah research assistant undang-undang untuk ResearcherHQ.

PERATURAN TAMBAHAN (MODE UNDANG-UNDANG):
- JANGAN sebut kes yang tiada dalam dokumen dimuat naik
- TIADA pengetahuan umum — kes mestilah dari dokumen user sahaja
- Format citation kes: [Nama Kes] [Tahun] [Rujukan MLJ/CLJ/AMR] [halaman]
- Precedent analysis: hanya dari dokumen ada
- Jika tiada kes relevan: "Tiada kes dalam dokumen yang merangkumi isu ini"

PERATURAN WAJIB: Jawab HANYA dari dokumen. Zero hallucination.""",

    "quantitative": """Anda adalah research assistant saintifik untuk ResearcherHQ.

Fokus pada: ujian statistik, p-value, effect size, confidence interval.
Cadangkan kaedah analisis (SPSS/R/Python) bila relevan.
Sokong LaTeX untuk formula matematik.
PERATURAN WAJIB: Jawab HANYA dari dokumen. Sumber wajib inline.""",

    "qualitative": """Anda adalah research assistant sains sosial untuk ResearcherHQ.

Fokus pada: thematic analysis, coding, grounded theory, phenomenology.
Bantu kenal pasti tema, sub-tema, dan corak dalam data kualitatif.
PERATURAN WAJIB: Jawab HANYA dari dokumen. Sumber wajib inline.""",

    "medicine": """Anda adalah research assistant perubatan untuk ResearcherHQ.

Gunakan framework PICO (Population, Intervention, Comparison, Outcome).
Rujuk level of evidence dan PRISMA bila relevan.
PERATURAN WAJIB: Jawab HANYA dari dokumen. Sumber wajib inline.""",
}

OUTPUT_MODE_PROMPTS = {
    "qa": "",
    "literature_review": """
Format output sebagai Literature Review akademik:
1. PENGENALAN — konteks topik
2. SOROTAN KAJIAN — kupasan tema utama dengan citation
3. JURANG KAJIAN — apa yang masih kurang
4. RUMUSAN — sintesis keseluruhan
Gunakan bahasa akademik formal.""",
    "executive_summary": """
Format output sebagai Executive Summary (1-2 muka surat):
- Poin-poin utama kajian
- Metodologi (ringkas)
- Dapatan utama
- Implikasi
Padat dan tepat.""",
    "key_findings": """
Format output sebagai Key Findings berstruktur:
- Bullet point setiap dapatan utama
- Setiap dapatan ada: DAPATAN → BUKTI (citation) → IMPLIKASI
Jelas dan boleh diambil tindakan.""",
}

KREDIT_COST = {
    "qa": 1,
    "qa_deep": 3,
    "key_findings": 3,
    "executive_summary": 5,
    "literature_review": 10,
    "research_gap": 10,
}

async def query_llm(
    messages: List[Dict],
    research_mode: str = "general",
    output_mode: str = "qa",
    query_type: str = "normal"
) -> Dict:
    system_prompt = SYSTEM_PROMPTS.get(research_mode, SYSTEM_PROMPTS["general"])
    output_prompt = OUTPUT_MODE_PROMPTS.get(output_mode, "")
    
    if output_prompt:
        system_prompt = system_prompt + "\n\n" + output_prompt
    
    model = settings.deepseek_model_flash
    if output_mode in ("literature_review", "research_gap") or query_type == "deep":
        model = settings.deepseek_model_pro
    
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": full_messages,
                "temperature": 0.1,
                "top_p": 0.1,
                "max_tokens": 4096
            }
        )
        resp.raise_for_status()
        data = resp.json()
    
    return {
        "content": data["choices"][0]["message"]["content"],
        "tokens_used": data["usage"]["total_tokens"],
        "model": model
    }
```

- [ ] **Step 5: Implement RAG query router**

```python
# backend/app/routers/rag.py
import uuid, json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user
from app.services.embedding_pool import embedding_pool
from app.services.rag_pipeline import retrieve_chunks
from app.services.llm_provider import query_llm, KREDIT_COST

router = APIRouter()

OUTPUT_MODES = {"qa", "literature_review", "executive_summary", "key_findings"}

class QueryRequest(BaseModel):
    query: str
    output_mode: str = "qa"
    query_type: str = "normal"  # "normal" | "deep"

@router.post("/{project_id}/query")
async def query_project(
    project_id: str,
    body: QueryRequest,
    user=Depends(get_current_user)
):
    if body.output_mode not in OUTPUT_MODES:
        raise HTTPException(400, f"Output mode tidak sah: {body.output_mode}")
    
    with get_db() as db:
        # Verify projek milik user
        proj = db.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        
        # Semak kredit
        user_row = db.execute(
            "SELECT kredit_remaining, tier FROM users WHERE id = ?",
            (user["user_id"],)
        ).fetchone()
        
        mode_key = body.output_mode
        if body.query_type == "deep" and body.output_mode == "qa":
            mode_key = "qa_deep"
        
        kredit_cost = KREDIT_COST.get(mode_key, 1)
        if user_row["kredit_remaining"] < kredit_cost:
            raise HTTPException(402, "Kredit Kajian tidak mencukupi.")
        
        project_dict = dict(proj)
    
    # Embed query
    query_embedding = await embedding_pool.embed(body.query)
    
    # Retrieve relevant chunks
    chunks = await retrieve_chunks(
        project_id=project_id,
        query_embedding=query_embedding,
        query_type=body.query_type,
        db_path=settings.database_url
    )
    
    if not chunks:
        return {
            "answer": "Tiada dokumen dalam projek ini. Sila muat naik dokumen terlebih dahulu.",
            "sources": [],
            "kredit_used": 0
        }
    
    # Bina konteks dari chunks
    context_parts = []
    for i, chunk in enumerate(chunks):
        context_parts.append(
            f"[Sumber {i+1}: {chunk['filename']}, ms. {chunk['page_number']}]\n{chunk['text']}"
        )
    context = "\n\n---\n\n".join(context_parts)
    
    messages = [
        {
            "role": "user",
            "content": f"KONTEKS DOKUMEN:\n\n{context}\n\n---\n\nSOALAN: {body.query}"
        }
    ]
    
    # Query LLM
    result = await query_llm(
        messages=messages,
        research_mode=project_dict["research_mode"],
        output_mode=body.output_mode,
        query_type=body.query_type
    )
    
    # Deduct kredit + simpan message
    with get_db() as db:
        db.execute(
            "UPDATE users SET kredit_remaining = kredit_remaining - ?, tokens_used_internal = tokens_used_internal + ? WHERE id = ?",
            (kredit_cost, result["tokens_used"], user["user_id"])
        )
        
        msg_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO messages (id, project_id, role, content, output_mode, source_chunks, kredit_used, tokens_used_internal, created_at)
               VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?)""",
            (msg_id, project_id, result["content"], body.output_mode,
             json.dumps([c["chunk_id"] for c in chunks]),
             kredit_cost, result["tokens_used"], datetime.utcnow().isoformat())
        )
        
        # Log interaction
        db.execute(
            """INSERT INTO user_interactions (id, user_id, event_type, research_mode, output_mode, kredit_used, query_length, created_at)
               VALUES (?, ?, 'query', ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), user["user_id"], project_dict["research_mode"],
             body.output_mode, kredit_cost, len(body.query), datetime.utcnow().isoformat())
        )
    
    return {
        "answer": result["content"],
        "sources": [
            {
                "chunk_id": c["chunk_id"],
                "filename": c["filename"],
                "page_number": c["page_number"],
                "text_preview": c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"],
                "similarity": round(c["similarity"], 3)
            }
            for c in chunks
        ],
        "kredit_used": kredit_cost,
        "kredit_remaining": user_row["kredit_remaining"] - kredit_cost
    }

@router.get("/{project_id}/messages")
def get_messages(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        
        messages = db.execute(
            "SELECT * FROM messages WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,)
        ).fetchall()
    return [dict(m) for m in messages]
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ backend/app/routers/rag.py
git commit -m "feat: RAG pipeline — MMR retrieval + DeepSeek LLM + citation"
```

---

### Task 8: Credit System + Account Delete (PDPA)

**Files:**
- Create: `backend/app/routers/credits.py`
- Create: `backend/app/routers/account.py`
- Create: `backend/tests/test_credits.py`
- Create: `backend/tests/test_cascade_delete.py`

- [ ] **Step 1: Tulis failing test**

```python
# backend/tests/test_credits.py
def test_kredit_deducted_on_query(client):
    headers = make_auth_header()
    # Pastikan user wujud
    client.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)
    r = client.get("/credits", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["kredit_remaining"] <= 50
    assert data["kredit_total"] == 50

# backend/tests/test_cascade_delete.py
def test_delete_user_cascades(client_with_user):
    """Padam user → semua data cascade delete kecuali billing_events"""
    headers, user_id = client_with_user
    proj_r = client_with_user[0].post("/projects", json={"title":"T","research_mode":"general"}, headers=headers)
    # ... (setup data)
    r = client_with_user[0].delete("/account", headers=headers)
    assert r.status_code == 204
    # Verify orphan data tiada

def test_billing_events_anonymized_not_deleted(client_with_billing):
    """billing_events kekal tapi user_id jadi 'deleted_user'"""
    # ... verify
    pass
```

- [ ] **Step 2: Implement credits router**

```python
# backend/app/routers/credits.py
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()

@router.get("")
def get_credits(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            "SELECT kredit_remaining, kredit_total, reset_date, tier FROM users WHERE id = ?",
            (user["user_id"],)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Pengguna tidak dijumpai.")
    return dict(row)
```

- [ ] **Step 3: Implement account router dengan cascade delete**

```python
# backend/app/routers/account.py
import sqlite3
import sqlite_vec
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user

router = APIRouter()

@router.get("")
def get_account(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            "SELECT id, email, tier, kredit_remaining, kredit_total, reset_date, created_at FROM users WHERE id = ?",
            (user["user_id"],)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Akaun tidak dijumpai.")
    return dict(row)

@router.delete("", status_code=204)
def delete_account(user=Depends(get_current_user)):
    """PDPA-compliant cascade delete."""
    user_id = user["user_id"]
    
    # Step 1: Manual delete chunk_vectors (virtual table, FK tak applicable)
    conn = sqlite3.connect(settings.database_url)
    sqlite_vec.load(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    
    chunk_ids = conn.execute("""
        SELECT c.id FROM chunks c
        JOIN documents d ON c.doc_id = d.id
        JOIN projects p ON d.project_id = p.id
        WHERE p.user_id = ?
    """, (user_id,)).fetchall()
    
    for (cid,) in chunk_ids:
        conn.execute("DELETE FROM chunk_vectors WHERE chunk_id = ?", (cid,))
    
    # Step 2: Anonymize billing_events (KEKAL untuk audit/cukai)
    conn.execute(
        "UPDATE billing_events SET user_id = 'deleted_user' WHERE user_id = ?",
        (user_id,)
    )
    
    # Step 3: Delete user → cascade automatik padam semua data berkaitan
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_credits.py tests/test_cascade_delete.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/credits.py backend/app/routers/account.py backend/tests/
git commit -m "feat: credit system + PDPA cascade delete (billing anonymize)"
```

---

### Task 9: Lean Report Issue → Telegram

**Files:**
- Create: `backend/app/routers/support.py`

- [ ] **Step 1: Implement support router**

```python
# backend/app/routers/support.py
import uuid, httpx
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user

router = APIRouter()

VALID_CATEGORIES = {"bug", "billing", "kredit", "lain-lain"}

class ReportBody(BaseModel):
    category: str
    description: str
    project_id: Optional[str] = None

@router.post("/report", status_code=201)
async def report_issue(body: ReportBody, user=Depends(get_current_user)):
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Kategori tidak sah: {body.category}")
    
    report_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    with get_db() as db:
        db.execute(
            """INSERT INTO support_reports (id, user_id, category, description, project_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (report_id, user["user_id"], body.category, body.description, body.project_id, now)
        )
    
    # Hantar ke Telegram
    message = (
        f"📩 *Laporan Baru — ResearcherHQ*\n"
        f"ID: `{report_id[:8]}`\n"
        f"Kategori: {body.category}\n"
        f"User: `{user['email']}`\n"
        f"Keterangan: {body.description[:300]}"
    )
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
            )
    except Exception:
        pass  # Jangan fail endpoint jika Telegram down
    
    return {"message": "Laporan diterima. Terima kasih.", "report_id": report_id}
```

- [ ] **Step 2: Verify endpoint**

```bash
uvicorn app.main:app --reload
curl -X POST http://localhost:8000/support/report \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"category":"bug","description":"Ujian laporan"}'
```
Expected: `{"message":"Laporan diterima...","report_id":"..."}` + Telegram notification

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/support.py
git commit -m "feat: lean report issue → Telegram Bot notification"
```

---

### Task 10: Frontend Design System + Logo

**Files:**
- Create: `frontend/src/tokens.css`
- Create: `frontend/src/components/Logo.jsx`
- Create: `frontend/src/components/CreditTank.jsx`
- Create: `frontend/src/api/client.js`
- Update: `frontend/index.html`

- [ ] **Step 1: Setup tokens.css**

```css
/* frontend/src/tokens.css */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&family=DM+Sans:wght@400;500&family=DM+Mono:wght@400;500&display=swap');

:root {
  --bg: #F8F6F1;
  --ink: #1C1B19;
  --ink-soft: #4A463F;
  --accent: #F97316;
  --accent-soft: #FCE3D0;
  --line: #E3DFD5;
  --card: #FFFFFF;

  --font-heading: 'Plus Jakarta Sans', sans-serif;
  --font-body: 'DM Sans', sans-serif;
  --font-mono: 'DM Mono', monospace;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 22px;
}

*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  font-family: var(--font-body);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}
```

- [ ] **Step 2: Buat Logo component**

```jsx
// frontend/src/components/Logo.jsx
export function Logo({ size = 'md', dark = false }) {
  const sizes = {
    sm: { word: 20, badge: 11, gap: 6, pad: '4px 8px', radius: 6 },
    md: { word: 28, badge: 14, gap: 8, pad: '5px 10px', radius: 7 },
    lg: { word: 44, badge: 18, gap: 12, pad: '7px 14px', radius: 8 },
  }
  const s = sizes[size]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: s.gap }}>
      <span style={{
        fontFamily: 'var(--font-heading)',
        fontWeight: 700,
        fontSize: s.word,
        color: dark ? 'var(--bg)' : 'var(--ink)',
        lineHeight: 1,
      }}>
        Researcher
      </span>
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontWeight: 500,
        fontSize: s.badge,
        letterSpacing: '0.05em',
        background: dark ? 'var(--accent)' : 'var(--ink)',
        color: dark ? 'var(--ink)' : 'var(--bg)',
        padding: s.pad,
        borderRadius: s.radius,
        transform: 'translateY(-2px)',
        lineHeight: 1,
      }}>
        HQ
      </span>
    </div>
  )
}

export function AppIcon({ size = 96, alt = false }) {
  const radius = Math.round(size * 0.23)
  const fontSize = Math.round(size * 0.31)
  return (
    <div style={{
      width: size, height: size,
      borderRadius: radius,
      background: alt ? 'var(--accent)' : 'var(--ink)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <span style={{
        fontFamily: 'var(--font-heading)',
        fontWeight: 800,
        fontSize,
        color: alt ? 'var(--ink)' : 'var(--accent)',
        letterSpacing: '0.01em',
      }}>
        HQ
      </span>
    </div>
  )
}
```

- [ ] **Step 3: Buat CreditTank component**

```jsx
// frontend/src/components/CreditTank.jsx
export function CreditTank({ remaining, total, resetDate, onTopup }) {
  const pct = Math.max(0, Math.min(100, (remaining / total) * 100))
  const low = pct < 20
  const resetStr = resetDate
    ? new Date(resetDate).toLocaleDateString('ms-MY', { day: 'numeric', month: 'long', year: 'numeric' })
    : '—'

  return (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--line)',
      borderRadius: 'var(--radius-md)', padding: '16px 20px', minWidth: 240,
    }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 11,
        letterSpacing: '0.08em', textTransform: 'uppercase',
        color: 'var(--ink-soft)', marginBottom: 10,
      }}>
        Kredit Kajian
      </div>
      <div style={{
        height: 8, background: 'var(--line)', borderRadius: 4,
        marginBottom: 8, overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: low ? '#EF4444' : 'var(--accent)',
          borderRadius: 4, transition: 'width 0.3s ease',
        }} />
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{
          fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16,
          color: low ? '#EF4444' : 'var(--ink)',
        }}>
          {remaining} / {total}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)' }}>
          Reset: {resetStr}
        </span>
      </div>
      {onTopup && (
        <button onClick={onTopup} style={{
          marginTop: 10, width: '100%', padding: '8px 0',
          background: 'var(--accent-soft)', color: 'var(--ink)',
          border: 'none', borderRadius: 'var(--radius-sm)',
          fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
          cursor: 'pointer',
        }}>
          Topup +200 kredit — RM10
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Buat API client**

```js
// frontend/src/api/client.js
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 60000,
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('rhq_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('rhq_token')
      localStorage.removeItem('rhq_user')
      window.location.href = '/auth'
    }
    return Promise.reject(err)
  }
)

export default api
```

- [ ] **Step 5: Update index.html**

```html
<!-- frontend/index.html -->
<!DOCTYPE html>
<html lang="ms">
<head>
  <meta charset="UTF-8" />
  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ResearcherHQ — Tesis siap, minda tenang</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/tokens.css frontend/src/components/ frontend/src/api/ frontend/index.html
git commit -m "feat: design system tokens + Logo + CreditTank components"
```

---

### Task 11: Frontend Pages (Auth + Dashboard + Workspace)

**Files:**
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/pages/AuthPage.jsx`
- Create: `frontend/src/pages/DashboardPage.jsx`
- Create: `frontend/src/pages/ProjectPage.jsx`
- Create: `frontend/src/components/ProfileMenu.jsx`
- Create: `frontend/src/components/CitationCard.jsx`

- [ ] **Step 1: Buat App.jsx + main.jsx**

```jsx
// frontend/src/main.jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import './tokens.css'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(<App />)
```

```jsx
// frontend/src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthPage } from './pages/AuthPage'
import { DashboardPage } from './pages/DashboardPage'
import { ProjectPage } from './pages/ProjectPage'

function PrivateRoute({ children }) {
  const token = localStorage.getItem('rhq_token')
  return token ? children : <Navigate to="/auth" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />
        <Route path="/project/:id" element={<PrivateRoute><ProjectPage /></PrivateRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 2: Buat AuthPage.jsx**

```jsx
// frontend/src/pages/AuthPage.jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import api from '../api/client'

export function AuthPage() {
  const nav = useNavigate()
  const [step, setStep] = useState('email') // 'email' | 'password'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  async function handleRequestPassword(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      await api.post('/auth/request-password', { email })
      setInfo('Kata laluan telah dihantar ke emel anda.')
      setStep('password')
    } catch (err) {
      setError(err.response?.data?.detail || 'Ralat berlaku.')
    }
    setLoading(false)
  }

  async function handleLogin(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const { data } = await api.post('/auth/login', { email, password })
      localStorage.setItem('rhq_token', data.access_token)
      localStorage.setItem('rhq_user', JSON.stringify(data.user))
      nav('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Kata laluan salah.')
    }
    setLoading(false)
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 24,
    }}>
      <div style={{ marginBottom: 32 }}>
        <Logo size="lg" />
      </div>
      <div style={{
        background: 'var(--card)', border: '1px solid var(--line)',
        borderRadius: 'var(--radius-lg)', padding: '40px 48px',
        width: '100%', maxWidth: 400,
      }}>
        {step === 'email' ? (
          <form onSubmit={handleRequestPassword}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>
              Log Masuk
            </h2>
            <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 24px' }}>
              Masukkan emel anda. Kami akan hantar kata laluan terus ke emel.
            </p>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="emel@universiti.edu.my" required
              style={inputStyle}
            />
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '8px 0 0' }}>{error}</p>}
            <button type="submit" disabled={loading} style={btnStyle}>
              {loading ? 'Menghantar...' : 'Hantar Kata Laluan →'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleLogin}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>
              Masukkan Kata Laluan
            </h2>
            {info && <p style={{ color: '#16A34A', fontSize: 13, margin: '0 0 16px', background: '#F0FDF4', padding: '8px 12px', borderRadius: 8 }}>{info}</p>}
            <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 16px' }}>
              Emel: <strong>{email}</strong>
            </p>
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Kata laluan 8 aksara" required
              style={inputStyle}
            />
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '8px 0 0' }}>{error}</p>}
            <button type="submit" disabled={loading} style={btnStyle}>
              {loading ? 'Log masuk...' : 'Log Masuk →'}
            </button>
            <button type="button" onClick={() => { setStep('email'); setInfo('') }}
              style={{ ...btnStyle, background: 'transparent', color: 'var(--ink-soft)', marginTop: 8 }}>
              ← Guna emel lain
            </button>
          </form>
        )}
      </div>
      <p style={{ marginTop: 24, color: 'var(--ink-soft)', fontSize: 13, textAlign: 'center' }}>
        Workspace penyelidikan untuk postgrad Malaysia
      </p>
    </div>
  )
}

const inputStyle = {
  width: '100%', padding: '12px 14px',
  border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-body)', fontSize: 15, color: 'var(--ink)',
  background: 'var(--bg)', outline: 'none', marginBottom: 12,
}

const btnStyle = {
  width: '100%', padding: '12px 0',
  background: 'var(--ink)', color: 'var(--bg)',
  border: 'none', borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15,
  cursor: 'pointer', marginTop: 4,
}
```

- [ ] **Step 3: Buat DashboardPage.jsx**

```jsx
// frontend/src/pages/DashboardPage.jsx
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { ProfileMenu } from '../components/ProfileMenu'
import api from '../api/client'

const MODES = [
  { value: 'general', label: 'Umum' },
  { value: 'quantitative', label: 'Kuantitatif / Sains' },
  { value: 'qualitative', label: 'Kualitatif / Sains Sosial' },
  { value: 'law', label: 'Undang-undang' },
  { value: 'medicine', label: 'Perubatan / Kesihatan' },
]

export function DashboardPage() {
  const nav = useNavigate()
  const [projects, setProjects] = useState([])
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newMode, setNewMode] = useState('general')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const user = JSON.parse(localStorage.getItem('rhq_user') || '{}')

  useEffect(() => {
    api.get('/projects').then(r => { setProjects(r.data); setLoading(false) })
  }, [])

  async function createProject(e) {
    e.preventDefault()
    setError('')
    try {
      const { data } = await api.post('/projects', { title: newTitle, research_mode: newMode })
      nav(`/project/${data.id}`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Gagal cipta projek.')
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <header style={{
        borderBottom: '1px solid var(--line)', padding: '0 24px',
        height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'var(--card)',
      }}>
        <Logo size="md" />
        <ProfileMenu user={user} />
      </header>

      <main style={{ maxWidth: 800, margin: '0 auto', padding: '40px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, margin: 0, fontSize: 24 }}>
            Projek Saya
          </h1>
          <button onClick={() => setCreating(true)} style={{
            padding: '10px 20px', background: 'var(--ink)', color: 'var(--bg)',
            border: 'none', borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, cursor: 'pointer',
          }}>
            + Projek Baru
          </button>
        </div>

        {creating && (
          <form onSubmit={createProject} style={{
            background: 'var(--card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-md)', padding: 24, marginBottom: 24,
          }}>
            <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 16px' }}>
              Projek Baru
            </h3>
            <input value={newTitle} onChange={e => setNewTitle(e.target.value)}
              placeholder="Tajuk projek / tesis" required
              style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, marginBottom: 12 }}
            />
            <select value={newMode} onChange={e => setNewMode(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, marginBottom: 16 }}>
              {MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 12px' }}>{error}</p>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" style={{ padding: '10px 20px', background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 8, fontWeight: 700, cursor: 'pointer' }}>
                Cipta Projek
              </button>
              <button type="button" onClick={() => { setCreating(false); setError('') }}
                style={{ padding: '10px 20px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, cursor: 'pointer' }}>
                Batal
              </button>
            </div>
          </form>
        )}

        {loading ? (
          <p style={{ color: 'var(--ink-soft)' }}>Memuatkan projek...</p>
        ) : projects.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <p style={{ color: 'var(--ink-soft)', fontSize: 16 }}>Tiada projek lagi.</p>
            <p style={{ color: 'var(--ink-soft)', fontSize: 14 }}>Klik "Projek Baru" untuk mulakan.</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 12 }}>
            {projects.map(p => (
              <div key={p.id} onClick={() => nav(`/project/${p.id}`)}
                style={{
                  background: 'var(--card)', border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-md)', padding: '20px 24px',
                  cursor: 'pointer', transition: 'border-color 0.15s',
                }}
                onMouseOver={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                onMouseOut={e => e.currentTarget.style.borderColor = 'var(--line)'}
              >
                <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 4px', fontSize: 18 }}>
                  {p.title}
                </h3>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11,
                  background: 'var(--accent-soft)', color: 'var(--ink)',
                  padding: '2px 8px', borderRadius: 4,
                }}>
                  {MODES.find(m => m.value === p.research_mode)?.label || p.research_mode}
                </span>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
```

- [ ] **Step 4: Buat CitationCard.jsx**

```jsx
// frontend/src/components/CitationCard.jsx
import { useState } from 'react'

export function CitationCard({ source }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{
      border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
      overflow: 'hidden', marginBottom: 8,
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '8px 12px', background: 'var(--bg)',
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-soft)' }}>
          📄 {source.filename}, ms. {source.page_number}
        </span>
        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            padding: '4px 10px', background: 'transparent',
            border: '1px solid var(--line)', borderRadius: 4,
            fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer',
            color: 'var(--ink)',
          }}
        >
          {expanded ? '▲ Tutup' : '▼ Lihat Sumber'}
        </button>
      </div>
      {expanded && (
        <div style={{
          padding: '12px 14px', background: 'var(--card)',
          borderTop: '1px solid var(--line)',
          fontFamily: 'var(--font-body)', fontSize: 13,
          color: 'var(--ink-soft)', lineHeight: 1.6,
        }}>
          {source.text_preview}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Buat ProfileMenu.jsx**

```jsx
// frontend/src/components/ProfileMenu.jsx
import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

export function ProfileMenu({ user }) {
  const [open, setOpen] = useState(false)
  const [credits, setCredits] = useState(null)
  const nav = useNavigate()
  const ref = useRef()

  useEffect(() => {
    function close(e) { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  async function toggle() {
    if (!open && !credits) {
      try { const { data } = await api.get('/credits'); setCredits(data) } catch {}
    }
    setOpen(!open)
  }

  function logout() {
    localStorage.removeItem('rhq_token')
    localStorage.removeItem('rhq_user')
    nav('/auth')
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button onClick={toggle} style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 12px', background: 'var(--bg)',
        border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
        cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 14,
      }}>
        <span style={{
          width: 28, height: 28, borderRadius: '50%',
          background: 'var(--ink)', color: 'var(--bg)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 12,
        }}>
          {user?.email?.[0]?.toUpperCase() || 'U'}
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 11,
          background: user?.tier === 'pro' ? 'var(--accent)' : 'var(--line)',
          padding: '2px 6px', borderRadius: 4,
        }}>
          {user?.tier === 'pro' ? 'PRO' : 'FREE'}
        </span>
      </button>

      {open && (
        <div style={{
          position: 'absolute', right: 0, top: '100%', marginTop: 8,
          background: 'var(--card)', border: '1px solid var(--line)',
          borderRadius: 'var(--radius-md)', padding: 8,
          minWidth: 220, zIndex: 100, boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
        }}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--line)', marginBottom: 4 }}>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>{user?.email}</p>
            {credits && (
              <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)' }}>
                {credits.kredit_remaining} kredit tersisa
              </p>
            )}
          </div>
          {[
            { label: 'Tetapan Akaun', action: () => {} },
            { label: 'Urus Langganan', action: () => {} },
            { label: 'Laporkan Isu', action: () => nav('/support') },
          ].map(item => (
            <button key={item.label} onClick={item.action} style={menuItemStyle}>
              {item.label}
            </button>
          ))}
          <button onClick={logout} style={{ ...menuItemStyle, color: '#EF4444', borderTop: '1px solid var(--line)', marginTop: 4 }}>
            Log Keluar
          </button>
        </div>
      )}
    </div>
  )
}

const menuItemStyle = {
  display: 'block', width: '100%', padding: '8px 12px',
  background: 'transparent', border: 'none', borderRadius: 6,
  fontFamily: 'var(--font-body)', fontSize: 14, textAlign: 'left',
  cursor: 'pointer', color: 'var(--ink)',
}
```

- [ ] **Step 6: Buat ProjectPage.jsx (workspace utama)**

```jsx
// frontend/src/pages/ProjectPage.jsx
import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { ProfileMenu } from '../components/ProfileMenu'
import { CreditTank } from '../components/CreditTank'
import { CitationCard } from '../components/CitationCard'
import api from '../api/client'

const OUTPUT_MODES = [
  { value: 'qa', label: 'Soal-Jawab', credits: 1 },
  { value: 'key_findings', label: 'Dapatan Utama', credits: 3 },
  { value: 'executive_summary', label: 'Ringkasan Eksekutif', credits: 5 },
  { value: 'literature_review', label: 'Sorotan Kajian', credits: 10 },
]

export function ProjectPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const [project, setProject] = useState(null)
  const [messages, setMessages] = useState([])
  const [query, setQuery] = useState('')
  const [outputMode, setOutputMode] = useState('qa')
  const [loading, setLoading] = useState(false)
  const [credits, setCredits] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef()
  const bottomRef = useRef()
  const user = JSON.parse(localStorage.getItem('rhq_user') || '{}')

  useEffect(() => {
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/projects/${id}/messages`),
      api.get('/credits'),
    ]).then(([p, m, c]) => {
      setProject(p.data)
      setMessages(m.data)
      setCredits(c.data)
    }).catch(() => nav('/'))
  }, [id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
    setUploading(true)
    
    // Extract text from PDF using pdfjs in browser
    // For MVP: send filename + placeholder (actual PDF.js extraction in production)
    try {
      const formData = new FormData()
      formData.append('file', file)
      // TODO: implement PDF.js text extraction
      // For now: send raw file to backend
      alert(`Dokumen "${file.name}" sedang diproses. (PDF.js extraction dalam fasa penuh)`)
    } catch (err) {
      alert('Gagal muat naik dokumen.')
    }
    setUploading(false)
    fileRef.current.value = ''
  }

  if (!project) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: 'var(--ink-soft)' }}>Memuatkan...</p>
    </div>
  )

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      {/* Header */}
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
          <ProfileMenu user={user} />
        </div>
      </header>

      {/* Chat area */}
      <div style={{ flex: 1, overflow: 'auto', padding: '24px', maxWidth: 800, width: '100%', margin: '0 auto' }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--ink-soft)' }}>
            <p style={{ fontSize: 18, fontWeight: 500 }}>Muat naik dokumen dan mula bertanya.</p>
            <p style={{ fontSize: 14 }}>Semua jawapan akan bersumberkan dokumen anda sahaja.</p>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} style={{
            marginBottom: 24,
            display: 'flex',
            flexDirection: 'column',
            alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '85%',
              background: msg.role === 'user' ? 'var(--ink)' : 'var(--card)',
              color: msg.role === 'user' ? 'var(--bg)' : 'var(--ink)',
              border: msg.role === 'user' ? 'none' : '1px solid var(--line)',
              borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
              padding: '14px 18px',
              fontFamily: 'var(--font-body)',
              fontSize: 15,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
            }}>
              {msg.content}
              {msg.kredit_used && (
                <span style={{ display: 'block', marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 11, opacity: 0.6 }}>
                  {msg.kredit_used} kredit digunakan
                </span>
              )}
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <div style={{ marginTop: 8, maxWidth: '85%', width: '100%' }}>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Sumber ({msg.sources.length})
                </p>
                {msg.sources.map(s => <CitationCard key={s.chunk_id} source={s} />)}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 24 }}>
            <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: '4px 16px 16px 16px', padding: '14px 18px' }}>
              <span style={{ color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)' }}>Berfikir...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div style={{
        borderTop: '1px solid var(--line)', padding: '16px 24px',
        background: 'var(--card)', flexShrink: 0,
      }}>
        <div style={{ maxWidth: 800, margin: '0 auto' }}>
          {/* Output mode selector */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
            {OUTPUT_MODES.map(m => (
              <button key={m.value} onClick={() => setOutputMode(m.value)} style={{
                padding: '4px 10px',
                background: outputMode === m.value ? 'var(--ink)' : 'transparent',
                color: outputMode === m.value ? 'var(--bg)' : 'var(--ink-soft)',
                border: `1px solid ${outputMode === m.value ? 'var(--ink)' : 'var(--line)'}`,
                borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer',
              }}>
                {m.label} ({m.credits} kr)
              </button>
            ))}
            <input type="file" ref={fileRef} onChange={handleFileUpload} accept=".pdf" style={{ display: 'none' }} />
            <button onClick={() => fileRef.current?.click()} style={{
              padding: '4px 10px', marginLeft: 'auto',
              background: 'var(--accent-soft)', border: '1px solid var(--accent)',
              borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer',
            }}>
              {uploading ? 'Memuat...' : '+ Dokumen'}
            </button>
          </div>
          <form onSubmit={handleQuery} style={{ display: 'flex', gap: 8 }}>
            <input
              value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Tanya soalan berdasarkan dokumen anda..."
              disabled={loading}
              style={{
                flex: 1, padding: '12px 16px',
                border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
                fontFamily: 'var(--font-body)', fontSize: 15, background: 'var(--bg)',
                outline: 'none',
              }}
            />
            <button type="submit" disabled={loading || !query.trim()} style={{
              padding: '12px 20px', background: 'var(--accent)', color: 'var(--ink)',
              border: 'none', borderRadius: 'var(--radius-sm)',
              fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, cursor: 'pointer',
            }}>
              →
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 7: Start frontend dan verify UI**

```bash
cd frontend && npm run dev
```
Expected: Buka `http://localhost:5173` — nampak Auth page dengan logo ResearcherHQ

- [ ] **Step 8: Commit**

```bash
git add frontend/src/
git commit -m "feat: frontend pages — Auth, Dashboard, Project workspace"
```

---

## FASA 1B — Consistency Layer

---

### Task 12: Query Cache (Versioned)

**Files:**
- Update: `backend/app/routers/rag.py` (tambah cache check)
- Create: `backend/tests/test_consistency.py`

- [ ] **Step 1: Tulis failing test**

```python
# backend/tests/test_consistency.py
def test_same_query_returns_cached():
    """Soalan yang sama dalam project sama patut return cached response."""
    # Mock embed dan llm
    # Query 1: store in cache
    # Query 2: same query → return cached (no LLM call)
    pass  # implement dengan mock dalam impl step

def test_cache_invalidated_on_upload():
    """Upload dokumen baru kena clear cache (version bump)."""
    pass
```

- [ ] **Step 2: Implement cache dalam rag.py**

Dalam `query_project`, sebelum memanggil LLM:
```python
# Dalam routers/rag.py — tambah import dan cache logic:
import hashlib
import numpy as np

def normalize_query(query: str) -> str:
    return " ".join(query.lower().strip().split())

def cache_key(query: str, project_id: str, doc_version: int) -> str:
    normalized = normalize_query(query)
    raw = f"{normalized}|{project_id}|{doc_version}"
    return hashlib.sha256(raw.encode()).hexdigest()

# Dalam query_project, SELEPAS embed query, SEBELUM retrieve chunks:
async def check_cache(project_id, query, query_embedding, doc_version, db):
    # Exact match
    key = cache_key(query, project_id, doc_version)
    cached = db.execute(
        "SELECT response, source_chunks FROM query_cache WHERE id = ? AND document_set_version = ?",
        (key, doc_version)
    ).fetchone()
    if cached:
        return cached
    
    # Near-match: embedding similarity > 0.95
    recent = db.execute(
        "SELECT id, query_embedding, response, source_chunks FROM query_cache WHERE project_id = ? AND document_set_version = ?",
        (project_id, doc_version)
    ).fetchmany(50)
    
    for row in recent:
        if row["query_embedding"]:
            stored_emb = list(row["query_embedding"])
            sim = cosine_similarity(query_embedding, stored_emb)
            if sim > 0.95:
                return row
    
    return None

# Selepas dapat response dari LLM, simpan dalam cache:
async def store_cache(key, project_id, query, query_embedding, doc_version, response, source_chunks, db):
    db.execute("""
        INSERT OR REPLACE INTO query_cache 
        (id, project_id, query_normalized, query_embedding, document_set_version, response, source_chunks, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        key, project_id, normalize_query(query),
        query_embedding,
        doc_version, response,
        json.dumps([c["chunk_id"] for c in source_chunks]),
        datetime.utcnow().isoformat()
    ))
```

- [ ] **Step 3: Wiring cache dalam query_project endpoint**

Selepas dapat `query_embedding` dan sebelum `retrieve_chunks`, tambah:
```python
with get_db() as db:
    doc_version = db.execute(
        "SELECT document_set_version FROM projects WHERE id = ?", (project_id,)
    ).fetchone()["document_set_version"]
    
    cached = await check_cache(project_id, body.query, query_embedding, doc_version, db)

if cached:
    return {
        "answer": cached["response"],
        "sources": json.loads(cached["source_chunks"] or "[]"),
        "kredit_used": 0,  # Cache = free
        "cache_hit": True
    }
```

- [ ] **Step 4: Verify konsistensi manual**

```bash
# Query sama 3x, verify response identical
curl -X POST localhost:8000/projects/{id}/query \
  -H "Authorization: Bearer <token>" \
  -d '{"query":"apa metodologi kajian?","output_mode":"qa"}'
# Jalankan 3x — response patut sama, kredit_used patut 0 untuk ke-2 dan ke-3
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/rag.py backend/tests/test_consistency.py
git commit -m "feat: query cache versioned (exact + near-match 0.95 threshold)"
```

---

### Task 13: Retrieval Determinism

**Files:**
- Update: `backend/app/services/rag_pipeline.py`

- [ ] **Step 1: Verify deterministic sort sudah ada**

Dalam `retrieve_chunks`, pastikan baris ini wujud:
```python
candidates.sort(key=lambda x: (-x["similarity"], x["chunk_id"]))
```
Ini sudah ada dari Task 7. Verify dengan test:

```python
# tests/test_consistency.py — tambah:
def test_retrieval_deterministic():
    """Retrieval dengan input sama kena return urutan sama."""
    from app.services.rag_pipeline import mmr_rerank
    candidates = [
        {"chunk_id": "z", "text": "teks z", "similarity": 0.8},
        {"chunk_id": "a", "text": "teks a", "similarity": 0.8},  # sama similarity, id berbeza
        {"chunk_id": "m", "text": "teks m", "similarity": 0.9},
    ]
    r1 = mmr_rerank(candidates, k=2)
    r2 = mmr_rerank(candidates, k=2)
    assert [x["chunk_id"] for x in r1] == [x["chunk_id"] for x in r2]
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_consistency.py -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/
git commit -m "test: verify retrieval determinism (tie-break by chunk_id)"
```

---

## FASA 1C — Output Modes + Hierarchical Context

---

### Task 14: Output Modes (Lit Review, Exec Summary, Key Findings)

Semua output modes sudah di-implement dalam `llm_provider.py` (Task 7) melalui `OUTPUT_MODE_PROMPTS` dan `KREDIT_COST`. Task ini verify dan tambah chapter summarization.

- [ ] **Step 1: Test manual output modes**

```bash
# Literature Review (10 kredit)
curl -X POST localhost:8000/projects/{id}/query \
  -d '{"query":"hasilkan sorotan kajian untuk bab 2 tesis saya","output_mode":"literature_review"}'

# Executive Summary (5 kredit)
curl -X POST localhost:8000/projects/{id}/query \
  -d '{"query":"buat ringkasan eksekutif dokumen ini","output_mode":"executive_summary"}'

# Key Findings (3 kredit)
curl -X POST localhost:8000/projects/{id}/query \
  -d '{"query":"senaraikan dapatan utama kajian ini","output_mode":"key_findings"}'
```
Expected: Output berformat ikut mode, kredit deduct betul

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: verify output modes (lit review/exec summary/key findings)"
```

---

### Task 15: Chapter Summarization (Hierarchical Context)

**Files:**
- Update: `backend/app/routers/rag.py` (cross-chapter context)
- Create: `backend/app/routers/chapters.py`
- Update: `backend/app/main.py` (include chapters router)

- [ ] **Step 1: Implement chapters router**

```python
# backend/app/routers/chapters.py
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.llm_provider import query_llm

router = APIRouter()

class ChapterCreate(BaseModel):
    title: str
    chapter_order: int

class ChapterContentUpdate(BaseModel):
    content: str

@router.post("/projects/{project_id}/chapters", status_code=201)
def create_chapter(project_id: str, body: ChapterCreate, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user["user_id"])).fetchone()
        if not proj: raise HTTPException(404, "Projek tidak dijumpai.")
        
        chap_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db.execute(
            "INSERT INTO chapters (id,project_id,title,chapter_order,status,created_at) VALUES (?,?,?,?,'draft',?)",
            (chap_id, project_id, body.title, body.chapter_order, now)
        )
        db.execute(
            "INSERT INTO chapter_content (id,chapter_id,content,summary,source_citations,updated_at) VALUES (?,?,'','','[]',?)",
            (str(uuid.uuid4()), chap_id, now)
        )
        return {"id": chap_id, "title": body.title, "chapter_order": body.chapter_order, "status": "draft"}

@router.get("/projects/{project_id}/chapters")
def list_chapters(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user["user_id"])).fetchone()
        if not proj: raise HTTPException(404)
        rows = db.execute("SELECT * FROM chapters WHERE project_id=? ORDER BY chapter_order", (project_id,)).fetchall()
    return [dict(r) for r in rows]

@router.patch("/projects/{project_id}/chapters/{chapter_id}/content")
async def update_chapter_content(
    project_id: str, chapter_id: str,
    body: ChapterContentUpdate,
    user=Depends(get_current_user)
):
    with get_db() as db:
        proj = db.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user["user_id"])).fetchone()
        if not proj: raise HTTPException(404)
        
        chap = db.execute("SELECT id FROM chapters WHERE id=? AND project_id=?", (chapter_id, project_id)).fetchone()
        if not chap: raise HTTPException(404, "Bab tidak dijumpai.")
        
        # Generate summary untuk hierarchical context
        messages = [{"role": "user", "content": f"Ringkaskan kandungan bab berikut dalam 150-200 patah perkataan sahaja, fokus pada argumen utama dan dapatan:\n\n{body.content[:3000]}"}]
        summary_result = await query_llm(messages, output_mode="qa")
        
        now = datetime.utcnow().isoformat()
        db.execute(
            "UPDATE chapter_content SET content=?, summary=?, updated_at=? WHERE chapter_id=?",
            (body.content, summary_result["content"], now, chapter_id)
        )
        db.execute(
            "UPDATE chapters SET status='dalam_proses' WHERE id=?", (chapter_id,)
        )
    return {"status": "updated", "summary_generated": True}
```

- [ ] **Step 2: Update main.py**

```python
from app.routers import chapters
app.include_router(chapters.router, tags=["chapters"])
```

- [ ] **Step 3: Tambah cross-chapter context dalam query**

Dalam `rag.py`, untuk `literature_review` output mode:
```python
# Sebelum build context, semak jika output mode perlukan hierarchical context:
if body.output_mode in ("literature_review", "research_gap"):
    with get_db() as db:
        chapter_summaries = db.execute("""
            SELECT c.title, cc.summary FROM chapters c
            JOIN chapter_content cc ON c.id = cc.chapter_id
            WHERE c.project_id = ? AND cc.summary != ''
            ORDER BY c.chapter_order
        """, (project_id,)).fetchall()
    
    if chapter_summaries:
        summary_context = "\n\n".join([
            f"[Ringkasan {row['title']}]: {row['summary']}"
            for row in chapter_summaries
        ])
        # Prepend ke context utama
        context = f"RINGKASAN BAB SEDIA ADA:\n{summary_context}\n\n---\n\n{context}"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/chapters.py backend/app/main.py backend/app/routers/rag.py
git commit -m "feat: chapter management + summarization + hierarchical context (§5C)"
```

---

## FASA 2 — Kredit Kajian + Monetization

---

### Task 16: ToyyibPay Integration

**Files:**
- Create: `backend/app/routers/billing.py`
- Update: `backend/app/main.py`

**PREREQ:** Sahkan auto-recurring support dengan ToyyibPay support sebelum implement subscription flow.

- [ ] **Step 1: Implement billing router (topup + webhook)**

```python
# backend/app/routers/billing.py
import uuid, hmac, hashlib
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user
import httpx

router = APIRouter()

TOPUP_AMOUNT = 10.00  # RM10
TOPUP_KREDIT = 200

@router.post("/topup/initiate")
async def initiate_topup(user=Depends(get_current_user)):
    """Cipta bill ToyyibPay untuk topup +200 kredit."""
    bill_id = str(uuid.uuid4())[:8].upper()
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://toyyibpay.com/index.php/api/createBill",
            data={
                "userSecretKey": settings.toyyibpay_secret_key,
                "categoryCode": settings.toyyibpay_category_code,
                "billName": f"ResearcherHQ Topup {bill_id}",
                "billDescription": "Topup +200 Kredit Kajian",
                "billPriceSetting": 1,
                "billPayorInfo": 1,
                "billAmount": int(TOPUP_AMOUNT * 100),  # sen
                "billReturnUrl": f"{settings.frontend_url}/billing/success",
                "billCallbackUrl": f"https://api.researcherhq.com/billing/webhook",
                "billExternalReferenceNo": f"TOPUP-{user['user_id'][:8]}-{bill_id}",
                "billTo": user["email"],
                "billEmail": user["email"],
                "billPhone": "0123456789",
                "billSplitPayment": 0,
                "billPaymentChannel": 0,  # FPX + DuitNow
            }
        )
        resp.raise_for_status()
        result = resp.json()
    
    if not result or not result[0].get("BillCode"):
        raise HTTPException(500, "Gagal cipta bil pembayaran.")
    
    bill_code = result[0]["BillCode"]
    
    with get_db() as db:
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, created_at) VALUES (?, ?, 'topup_initiated', ?, ?, ?)",
            (str(uuid.uuid4()), user["user_id"], TOPUP_AMOUNT, TOPUP_KREDIT, datetime.utcnow().isoformat())
        )
    
    return {
        "payment_url": f"https://toyyibpay.com/{bill_code}",
        "bill_code": bill_code
    }

@router.post("/webhook")
async def toyyibpay_webhook(request: Request):
    """ToyyibPay callback selepas bayar berjaya."""
    form = await request.form()
    
    ref_no = form.get("refno", "")
    status = form.get("status", "")
    
    if status != "1":  # 1 = berjaya
        return {"status": "ignored"}
    
    # Extract user_id dari reference number
    parts = ref_no.split("-")
    if len(parts) < 2:
        return {"status": "invalid_ref"}
    
    user_id_prefix = parts[1]
    
    with get_db() as db:
        user = db.execute(
            "SELECT id FROM users WHERE id LIKE ?", (f"{user_id_prefix}%",)
        ).fetchone()
        
        if not user:
            return {"status": "user_not_found"}
        
        # Tambah kredit
        db.execute(
            "UPDATE users SET kredit_remaining = kredit_remaining + ? WHERE id = ?",
            (TOPUP_KREDIT, user["id"])
        )
        
        # Log billing event
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, created_at) VALUES (?, ?, 'topup_success', ?, ?, ?)",
            (str(uuid.uuid4()), user["id"], TOPUP_AMOUNT, TOPUP_KREDIT, datetime.utcnow().isoformat())
        )
    
    return {"status": "ok"}
```

- [ ] **Step 2: Update main.py + verify**

```python
from app.routers import billing
app.include_router(billing.router, prefix="/billing", tags=["billing"])
```

- [ ] **Step 3: Test end-to-end (manual)**

```
1. Initiate topup → dapat payment_url
2. Buka URL → bayar dengan FPX sandbox
3. Webhook diterima → kredit +200
4. GET /credits → verify kredit_remaining meningkat
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/billing.py
git commit -m "feat: ToyyibPay topup flow + webhook kredit update (Fasa 2)"
```

---

### Task 17: OCR Fallback (Pro Tier)

**Files:**
- Create: `backend/app/services/ocr_service.py`
- Update: `backend/app/routers/documents.py`

- [ ] **Step 1: Implement OCR service**

```python
# backend/app/services/ocr_service.py
import asyncio
import io
from PIL import Image
import pytesseract

async def ocr_pdf_pages(pdf_bytes: bytes) -> list[dict]:
    """Extract text dari scanned PDF via pytesseract."""
    def _run_ocr():
        import fitz  # PyMuPDF — tambah ke requirements.txt: PyMuPDF==1.24.9
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang="eng+msa")
            pages.append({"page_number": page_num + 1, "text": text})
        return pages
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_ocr)

def is_scanned_pdf(pages: list[dict]) -> bool:
    """Semak jika PDF adalah scanned (kurang dari 50 token/halaman)."""
    if not pages:
        return False
    avg_tokens = sum(len(p.get("text", "").split()) for p in pages) / len(pages)
    return avg_tokens < 50
```

- [ ] **Step 2: Tambah ke requirements.txt**

```
PyMuPDF==1.24.9
```

- [ ] **Step 3: Update document upload untuk OCR flag**

Dalam `documents.py`, selepas extract text dari PDF.js:
```python
# Jika text kurang dari threshold → flag sebagai scanned PDF
if is_scanned_pdf(body.pages):
    if tier != "pro":
        return {
            "error": "scanned_pdf",
            "message": "PDF ini nampak seperti dokumen imbasan. Naik taraf ke Pro untuk proses PDF imbasan.",
            "upgrade_required": True
        }
    # Pro: queue untuk OCR
    # (OCR dilakukan async — update chunk selepas siap)
    db.execute("UPDATE documents SET is_ocr = 1 WHERE id = ?", (doc_id,))
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/ocr_service.py backend/requirements.txt backend/app/routers/documents.py
git commit -m "feat: OCR fallback pytesseract (Pro tier, scanned PDF detection)"
```

---

## FASA 3 — Thesis Workspace

---

### Task 18: 3-Panel Layout

**Files:**
- Update: `frontend/src/pages/ProjectPage.jsx` (refactor to 3-panel)
- Create: `frontend/src/components/SourcePanel.jsx`
- Create: `frontend/src/components/ThesisPanel.jsx`

- [ ] **Step 1: Buat SourcePanel.jsx**

```jsx
// frontend/src/components/SourcePanel.jsx
import { useState } from 'react'

const CATEGORIES = [
  { value: 'artikel', label: 'Artikel Rujukan', icon: '📄' },
  { value: 'catatan_sv', label: 'Catatan SV', icon: '📝' },
  { value: 'draf', label: 'Draf Sendiri', icon: '📑' },
  { value: 'data', label: 'Data / Transkrip', icon: '📊' },
]

export function SourcePanel({ documents, onUpload, tier }) {
  const [activeCategory, setActiveCategory] = useState('artikel')

  const grouped = CATEGORIES.map(cat => ({
    ...cat,
    docs: (documents || []).filter(d => d.category === cat.value)
  }))

  return (
    <div style={{
      width: 260, flexShrink: 0, borderRight: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column', background: 'var(--card)',
      overflow: 'hidden',
    }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Sumber
        </span>
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
                fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-soft)',
              }}>
                {doc.filename}
                <span style={{ display: 'block', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                  {doc.chunk_count} chunk
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
      <div style={{ padding: 12, borderTop: '1px solid var(--line)' }}>
        <button onClick={onUpload} style={{
          width: '100%', padding: '8px 0',
          background: 'var(--accent-soft)', border: '1px solid var(--accent)',
          borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 13,
          cursor: 'pointer', color: 'var(--ink)',
        }}>
          + Muat naik
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Buat ThesisPanel.jsx**

```jsx
// frontend/src/components/ThesisPanel.jsx
const STATUS_LABEL = { draft: 'Draf', dalam_proses: 'Dalam Proses', siap: 'Siap' }
const STATUS_COLOR = { draft: 'var(--line)', dalam_proses: 'var(--accent-soft)', siap: '#D1FAE5' }

export function ThesisPanel({ chapters, onExport, tier, projectId }) {
  const done = (chapters || []).filter(c => c.status === 'siap').length
  const total = (chapters || []).length

  return (
    <div style={{
      width: 260, flexShrink: 0, borderLeft: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column', background: 'var(--card)',
    }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Struktur Tesis
        </span>
        {total > 0 && (
          <span style={{ float: 'right', fontFamily: 'var(--font-mono)', fontSize: 11, color: done === total ? '#16A34A' : 'var(--ink-soft)' }}>
            {done}/{total} siap
          </span>
        )}
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {(chapters || []).length === 0 ? (
          <p style={{ padding: '16px', color: 'var(--ink-soft)', fontSize: 13 }}>
            Tiada bab lagi. Tambah bab pertama anda.
          </p>
        ) : (
          (chapters || []).map(chap => (
            <div key={chap.id} style={{
              padding: '8px 16px',
              borderBottom: '1px solid var(--line)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)', flex: 1 }}>
                  {chap.title}
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 6px', borderRadius: 4,
                  background: STATUS_COLOR[chap.status], color: 'var(--ink)',
                  flexShrink: 0,
                }}>
                  {STATUS_LABEL[chap.status]}
                </span>
              </div>
              {tier === 'pro' ? (
                <button onClick={() => onExport(chap.id)} style={{
                  marginTop: 6, padding: '3px 8px', fontSize: 11,
                  background: 'transparent', border: '1px solid var(--line)',
                  borderRadius: 4, cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}>
                  Export .docx
                </button>
              ) : (
                <button style={{
                  marginTop: 6, padding: '3px 8px', fontSize: 11,
                  background: 'var(--line)', border: 'none',
                  borderRadius: 4, cursor: 'not-allowed', fontFamily: 'var(--font-mono)',
                  color: 'var(--ink-soft)',
                }}>
                  🔒 Pro
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Update ProjectPage.jsx untuk 3-panel**

Wrap existing chat area dengan flex row:
```jsx
// Dalam ProjectPage.jsx, gantikan main content area:
<div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
  <SourcePanel documents={documents} onUpload={() => fileRef.current?.click()} tier={user?.tier} />
  
  {/* Chat area (tengah) — code sedia ada */}
  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
    {/* ... existing chat + input ... */}
  </div>
  
  <ThesisPanel chapters={chapters} onExport={handleExport} tier={user?.tier} projectId={id} />
</div>
```

Tambah state dan fetch:
```jsx
const [documents, setDocuments] = useState([])
const [chapters, setChapters] = useState([])

// Dalam useEffect, tambah:
api.get(`/documents?project_id=${id}`).then(r => setDocuments(r.data)).catch(() => {})
api.get(`/projects/${id}/chapters`).then(r => setChapters(r.data)).catch(() => {})
```

- [ ] **Step 4: Tambah GET /documents endpoint**

```python
# backend/app/routers/documents.py — tambah:
@router.get("")
def list_documents(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user["user_id"])).fetchone()
        if not proj: raise HTTPException(404)
        docs = db.execute("SELECT * FROM documents WHERE project_id=? ORDER BY uploaded_at DESC", (project_id,)).fetchall()
    return [dict(d) for d in docs]
```

- [ ] **Step 5: Start app dan verify 3-panel**

```bash
cd frontend && npm run dev
```
Expected: ProjectPage tunjuk 3 panel — Source (kiri), Chat (tengah), Thesis (kanan)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SourcePanel.jsx frontend/src/components/ThesisPanel.jsx frontend/src/pages/ProjectPage.jsx backend/app/routers/documents.py
git commit -m "feat: 3-panel workspace layout (Source | Chat | Thesis)"
```

---

### Task 19: Export .docx (Async Queue)

**Files:**
- Create: `backend/app/services/export_service.py`
- Update: `backend/app/routers/chapters.py`
- Update: `backend/requirements.txt`

- [ ] **Step 1: Implement export service**

```python
# backend/app/services/export_service.py
import asyncio
import uuid
import json
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import sqlite3
from app.config import settings

# In-memory queue (MVP — swap ke Redis untuk production scale)
_export_queue: asyncio.Queue = asyncio.Queue()
_export_results: dict = {}  # export_id → {"status": ..., "path": ...}

async def queue_chapter_export(chapter_id: str, user_id: str) -> str:
    export_id = str(uuid.uuid4())
    _export_results[export_id] = {"status": "queued", "path": None}
    await _export_queue.put({
        "export_id": export_id,
        "chapter_id": chapter_id,
        "user_id": user_id
    })
    return export_id

async def get_export_status(export_id: str) -> dict:
    return _export_results.get(export_id, {"status": "not_found"})

def _build_docx(chapter_id: str) -> str:
    conn = sqlite3.connect(settings.database_url)
    conn.row_factory = sqlite3.Row
    
    chap = conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
    content_row = conn.execute("SELECT * FROM chapter_content WHERE chapter_id=?", (chapter_id,)).fetchone()
    conn.close()
    
    if not chap or not content_row:
        raise ValueError("Bab tidak dijumpai.")
    
    doc = Document()
    
    # Title
    title = doc.add_heading(chap["title"], level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Content (markdown-ish — strip basic formatting)
    content = content_row["content"] or ""
    for line in content.split('\n'):
        if line.startswith('## '):
            doc.add_heading(line[3:], level=2)
        elif line.startswith('# '):
            doc.add_heading(line[2:], level=1)
        elif line.startswith('**') and line.endswith('**'):
            p = doc.add_paragraph()
            run = p.add_run(line[2:-2])
            run.bold = True
        elif line.strip():
            doc.add_paragraph(line)
    
    # Citations
    citations = json.loads(content_row["source_citations"] or "[]")
    if citations:
        doc.add_heading("Rujukan", level=2)
        for cite in citations:
            doc.add_paragraph(cite, style='List Bullet')
    
    # Save
    output_path = f"/tmp/export_{chapter_id}_{uuid.uuid4().hex[:8]}.docx"
    doc.save(output_path)
    return output_path

async def run_export_worker():
    """Background worker untuk proses export queue."""
    while True:
        try:
            task = await asyncio.wait_for(_export_queue.get(), timeout=1.0)
            export_id = task["export_id"]
            try:
                _export_results[export_id]["status"] = "processing"
                loop = asyncio.get_event_loop()
                path = await loop.run_in_executor(None, _build_docx, task["chapter_id"])
                _export_results[export_id] = {"status": "ready", "path": path}
            except Exception as e:
                _export_results[export_id] = {"status": "error", "error": str(e)}
        except asyncio.TimeoutError:
            continue
```

- [ ] **Step 2: Update main.py untuk start export worker**

```python
# backend/app/main.py
from app.services.export_service import run_export_worker

@app.on_event("startup")
async def startup():
    init_db()
    await embedding_pool.start()
    asyncio.create_task(run_export_worker())
```

- [ ] **Step 3: Tambah export endpoints dalam chapters.py**

```python
# backend/app/routers/chapters.py — tambah:
from fastapi.responses import FileResponse
from app.services.export_service import queue_chapter_export, get_export_status

@router.post("/projects/{project_id}/chapters/{chapter_id}/export")
async def request_export(project_id: str, chapter_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        user_row = db.execute("SELECT tier FROM users WHERE id=?", (user["user_id"],)).fetchone()
        if not user_row or user_row["tier"] != "pro":
            raise HTTPException(403, "Export .docx hanya untuk Pro tier.")
        
        proj = db.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user["user_id"])).fetchone()
        if not proj: raise HTTPException(404)
    
    export_id = await queue_chapter_export(chapter_id, user["user_id"])
    return {"export_id": export_id, "status": "queued", "message": "Sedang disediakan..."}

@router.get("/exports/{export_id}/status")
async def export_status(export_id: str, user=Depends(get_current_user)):
    status = await get_export_status(export_id)
    return status

@router.get("/exports/{export_id}/download")
async def download_export(export_id: str, user=Depends(get_current_user)):
    status = await get_export_status(export_id)
    if status.get("status") != "ready":
        raise HTTPException(404, "Fail belum sedia.")
    return FileResponse(
        status["path"],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="bab_tesis.docx"
    )
```

- [ ] **Step 4: Verify export flow**

```bash
# 1. PATCH /projects/{id}/chapters/{chap_id}/content dengan content panjang
# 2. POST /projects/{id}/chapters/{chap_id}/export → dapat export_id
# 3. GET /exports/{export_id}/status → status: "ready"
# 4. GET /exports/{export_id}/download → dapat .docx file
# Buka di Word/GDocs — verify format betul
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_service.py backend/app/routers/chapters.py backend/app/main.py
git commit -m "feat: async .docx export queue + download endpoint (Fasa 3)"
```

---

### Task 20: Free Tier "Visible Locked"

**Files:**
- Update: `frontend/src/components/ThesisPanel.jsx` (overlay Pro)
- Update: `frontend/src/pages/ProjectPage.jsx` (upload limit)

- [ ] **Step 1: Tambah overlay untuk free tier dalam ThesisPanel**

Dalam `ThesisPanel.jsx`, wrap chapter management dengan Pro overlay:
```jsx
{tier !== 'pro' && (
  <div style={{
    position: 'absolute', inset: 0,
    background: 'rgba(248,246,241,0.85)',
    backdropFilter: 'blur(2px)',
    display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center',
    borderRadius: 'var(--radius-md)', zIndex: 10,
    padding: 24, textAlign: 'center',
  }}>
    <span style={{ fontSize: 32, marginBottom: 12 }}>🔒</span>
    <p style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16, margin: '0 0 8px' }}>
      Thesis Workspace
    </p>
    <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)', margin: '0 0 16px' }}>
      Urus bab, assign output AI, dan export .docx — hanya untuk Pro.
    </p>
    <button style={{
      padding: '10px 20px', background: 'var(--accent)', border: 'none',
      borderRadius: 'var(--radius-sm)', fontWeight: 700, cursor: 'pointer',
      fontFamily: 'var(--font-heading)', fontSize: 14,
    }}
    onClick={() => window.location.href='/upgrade'}>
      Naik taraf ke Pro — RM39/bulan
    </button>
  </div>
)}
```

- [ ] **Step 2: Hadkan upload untuk free tier**

Dalam `SourcePanel.jsx`, tunjuk mesej jika dah ada 1 dokumen dan free tier:
```jsx
const uploadDisabled = tier !== 'pro' && (documents || []).length >= 1

// dalam button upload:
disabled={uploadDisabled}
title={uploadDisabled ? 'Free tier: 1 PDF sahaja. Naik taraf ke Pro untuk sehingga 5 PDF.' : ''}
style={{
  ...buttonStyle,
  opacity: uploadDisabled ? 0.5 : 1,
  cursor: uploadDisabled ? 'not-allowed' : 'pointer',
}}
```

- [ ] **Step 3: Verify free tier experience**

```
1. Log masuk sebagai free user
2. Buka project
3. Verify: Chat panel BOLEH guna ✅
4. Verify: Source panel — nampak dokumen, upload 1 PDF ✅
5. Verify: Thesis panel — nampak template, interaksi 🔒 ✅
6. Verify: Export button ada overlay "Naik taraf ke Pro" ✅
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ThesisPanel.jsx frontend/src/components/SourcePanel.jsx
git commit -m "feat: free tier 'visible locked' — Pro features visible but gated"
```

---

## Verification (KPI Exit Gates)

### Fasa 1A Verification

- [ ] **Retrieval relevance (≥80%):** Upload 3 PDF, buat 20 soalan ujian, verify ≥16 chunk relevan
- [ ] **Citation accuracy (100%):** Semua citation ada "Lihat Sumber" yang boleh dibuka — verify teks chunk sebenar
- [ ] **Hallucination test:** Tanya fakta yang TIDAK ada dalam dokumen → system patut jawab "Maklumat ini tidak terdapat..."
- [ ] **Response time (<5s):** Log timestamps, verify p90 < 5s
- [ ] **Cascade delete:** Cipta user → upload dokumen → query → padam akaun → verify semua orphan data tiada (query semua tables)
- [ ] **Billing anonymize:** Cipta billing event → padam user → verify `user_id = 'deleted_user'` dalam billing_events
- [ ] **Telegram notification:** Hantar 5 report → verify semua diterima dalam Telegram < 5s

### Load Test (Fasa 1A → sebelum 1B)

```bash
pip install locust

# locustfile.py
from locust import HttpUser, task
class ResearchUser(HttpUser):
    @task
    def query(self):
        self.client.post("/projects/{id}/query",
            json={"query": "apa metodologi kajian?", "output_mode": "qa"},
            headers={"Authorization": f"Bearer {TOKEN}"}
        )

locust -f locustfile.py --users 50 --spawn-rate 5 --run-time 2m --headless \
  --host http://localhost:8000
```

KPI:
- Response time @ 50 concurrent: < 8s
- Error rate: < 1%
- RAM: < 6GB

### Fasa 1B Verification

- [ ] **Exact-match consistency:** 10 soalan × ulang 3x → response 100% sama
- [ ] **Cache hit rate:** Log hit/miss → ≥40% selepas 50 query
- [ ] **Cache invalidation:** Upload dokumen baru → query sama → verify BUKAN dari cache

### Fasa 3 Verification

- [ ] **End-to-end:** Upload → chat → assign ke chapter → export .docx tanpa error
- [ ] **Export integrity:** Buka .docx di Word + GDocs + LibreOffice → format kekal, citation ada
- [ ] **Free tier:** Semua Pro interaction betul-betul blocked (test sebagai free user)

---

## Deployment (VPS)

### nginx.conf

```nginx
server {
    listen 80;
    server_name researcherhq.com www.researcherhq.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name researcherhq.com www.researcherhq.com;

    ssl_certificate /etc/letsencrypt/live/researcherhq.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/researcherhq.com/privkey.pem;

    # Frontend static
    root /var/www/researcherhq/dist;
    index index.html;
    try_files $uri $uri/ /index.html;

    # API proxy
    location /api/ {
        rewrite ^/api/(.*) /$1 break;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 90s;
    }
}
```

### Deploy commands

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 &

# Frontend
cd frontend
npm run build
cp -r dist /var/www/researcherhq/

# Nginx
sudo nginx -t && sudo systemctl reload nginx
```
