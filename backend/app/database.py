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
      password_hash TEXT,
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

    CREATE TABLE IF NOT EXISTS rate_limit_events (
      id TEXT PRIMARY KEY,
      scope_key TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_rate_limit_scope_time ON rate_limit_events(scope_key, created_at);

    CREATE TABLE IF NOT EXISTS voice_profile (
      id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
      style_notes TEXT NOT NULL,
      sample_excerpt TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_voice_profile_project ON voice_profile(project_id);

    CREATE TABLE IF NOT EXISTS admin_action_log (
      id TEXT PRIMARY KEY,
      admin_email TEXT NOT NULL,
      action TEXT NOT NULL,
      target_type TEXT NOT NULL,
      target_id TEXT NOT NULL,
      details TEXT,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_admin_log_target ON admin_action_log(target_type, target_id);

    CREATE TABLE IF NOT EXISTS supervisor_feedback (
      id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
      doc_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
      chapter_id TEXT REFERENCES chapters(id) ON DELETE SET NULL,
      feedback_text TEXT NOT NULL,
      status TEXT DEFAULT 'open',
      created_at TEXT,
      resolved_at TEXT
    );
    """)

    # chunk_vectors virtual table — created separately from executescript
    # because executescript commits the transaction before each statement,
    # and some sqlite-vec versions require the extension to be loaded first.
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
          chunk_id TEXT,
          embedding FLOAT[384]
        )
    """)

    # Migration: add reference_no to billing_events for idempotency + audit
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(billing_events)").fetchall()]
    if "reference_no" not in cols:
        conn.execute("ALTER TABLE billing_events ADD COLUMN reference_no TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_billing_reference_no ON billing_events(reference_no)")

    # Migration: add is_suspended to users for admin suspend action
    user_cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "is_suspended" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_suspended INTEGER DEFAULT 0")

    # Migration: add password_is_permanent for Opsyen B login model
    if "password_is_permanent" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN password_is_permanent INTEGER DEFAULT 0")

    # Migration: Task 1 — profile columns for onboarding redesign
    if "name" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN name TEXT")
    if "institution" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN institution TEXT")

    # Migration: Task 1 — project onboarding metadata columns
    proj_cols = [row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()]
    if "output_target" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN output_target TEXT DEFAULT 'thesis'")
    if "degree_level" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN degree_level TEXT")
    if "proposal_status" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN proposal_status TEXT")
    if "citation_style" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN citation_style TEXT DEFAULT 'APA7'")

    # Migration: Task 19 — section_type untuk Document Assembly ordering
    chap_cols = [row["name"] for row in conn.execute("PRAGMA table_info(chapters)").fetchall()]
    if "section_type" not in chap_cols:
        conn.execute("ALTER TABLE chapters ADD COLUMN section_type TEXT DEFAULT 'chapter'")

    # Migration: Task 12B — voice profile per project
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_profile (
              id TEXT PRIMARY KEY,
              project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
              style_notes TEXT NOT NULL,
              sample_excerpt TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_voice_profile_project
            ON voice_profile(project_id)
        """)
    except Exception:
        pass

    # Migration: Task 27 — sample_analysis column for voice_profile
    voice_cols = [row["name"] for row in conn.execute("PRAGMA table_info(voice_profile)").fetchall()]
    if "sample_analysis" not in voice_cols:
        conn.execute("ALTER TABLE voice_profile ADD COLUMN sample_analysis TEXT")

    # Migration: Task 28 — supervisor_feedback table
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS supervisor_feedback (
                id TEXT PRIMARY KEY,
                project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
                doc_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
                chapter_id TEXT REFERENCES chapters(id) ON DELETE SET NULL,
                feedback_text TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                created_at TEXT,
                resolved_at TEXT
            )
        """)
    except Exception:
        pass

    # Migration: Task 23 — rolling 30-day billing model
    user_cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "kredit_subscription" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN kredit_subscription INTEGER DEFAULT 50")
    if "kredit_topup" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN kredit_topup INTEGER DEFAULT 0")
    if "subscription_start_date" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN subscription_start_date TEXT")

    # Backfill: existing users get subscription_start_date = created_at, seed kredit_subscription
    conn.execute("""
        UPDATE users
        SET subscription_start_date = created_at,
            kredit_subscription = kredit_remaining,
            kredit_topup = 0
        WHERE subscription_start_date IS NULL
    """)

    # Migration: Task 30 — language preferences
    user_cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "chat_language" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN chat_language TEXT DEFAULT 'bm'")

    proj_cols = [row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()]
    if "output_language" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN output_language TEXT DEFAULT 'bm'")


@contextmanager
def get_db():
    conn = sqlite3.connect(_db_path, timeout=30)  # ponytail: 30s gives SQLite room to drain write queue
    conn.row_factory = sqlite3.Row
    sqlite_vec.load(conn)
    conn.execute("PRAGMA journal_mode=WAL")  # defensive: set per-connection in case DB was opened before init_db
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
