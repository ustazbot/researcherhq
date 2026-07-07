import uuid
import sqlite3
import sqlite_vec
from contextlib import contextmanager
from datetime import datetime
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

    CREATE TABLE IF NOT EXISTS chat_sessions (
      id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
      title TEXT DEFAULT 'Chat Baru',
      conversation_summary TEXT DEFAULT '',
      created_at TEXT,
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
      session_id TEXT REFERENCES chat_sessions(id) ON DELETE CASCADE,
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

    # Migration: Task 31 — chat_sessions table + session_id on messages
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
          id TEXT PRIMARY KEY,
          project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
          title TEXT DEFAULT 'Chat Baru',
          conversation_summary TEXT DEFAULT '',
          created_at TEXT,
          updated_at TEXT
        )
    """)

    msg_cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "session_id" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN session_id TEXT REFERENCES chat_sessions(id) ON DELETE CASCADE")

    # Backfill: create default session per project for orphan messages
    projects_with_orphan_msgs = conn.execute("""
        SELECT DISTINCT project_id FROM messages WHERE session_id IS NULL
    """).fetchall()

    now = datetime.utcnow().isoformat()
    for row in projects_with_orphan_msgs:
        pid = row[0]
        default_session_id = str(uuid.uuid4())
        conn.execute("""
            INSERT OR IGNORE INTO chat_sessions (id, project_id, title, created_at, updated_at)
            VALUES (?, ?, 'Perbualan Awal', ?, ?)
        """, (default_session_id, pid, now, now))
        conn.execute("""
            UPDATE messages SET session_id = ?
            WHERE project_id = ? AND session_id IS NULL
        """, (default_session_id, pid))

    # Migration: Security audit F2 — atomic webhook idempotency.
    # Partial unique index only on the credit-granting success events, so
    # two concurrent identical callbacks cannot both grant. Scoped to
    # success events so repeated admin 'manual_adjustment' rows (which reuse
    # reference_no 'ADMIN-<email>') and 'initiated' rows are unaffected.
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_success_unique
        ON billing_events(reference_no, event_type)
        WHERE event_type IN ('topup_success', 'upgrade_success')
    """)

    # Migration: Task 36C-1 — survey analysis (constructs + analyses)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS survey_constructs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        position INTEGER NOT NULL,
        FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS survey_construct_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        construct_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        UNIQUE(construct_id, question_id),
        FOREIGN KEY (construct_id) REFERENCES survey_constructs(id) ON DELETE CASCADE,
        FOREIGN KEY (question_id) REFERENCES survey_questions(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_construct_items_construct ON survey_construct_items(construct_id);

    CREATE TABLE IF NOT EXISTS survey_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_id INTEGER NOT NULL,
        analysis_type TEXT NOT NULL,
        data_source TEXT NOT NULL,
        params_json TEXT NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_survey_analyses_survey ON survey_analyses(survey_id);
    """)

    # Migration: Task 36C-3 — AI interpretation snapshot on analyses
    analysis_cols = [row["name"] for row in conn.execute("PRAGMA table_info(survey_analyses)").fetchall()]
    if "interpretation_json" not in analysis_cols:
        conn.execute("ALTER TABLE survey_analyses ADD COLUMN interpretation_json TEXT")

    # Migration: Task 36A — survey module Fasa A (Bina)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS surveys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT 'Survey',
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS survey_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        position INTEGER NOT NULL,
        FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS survey_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        section_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        question_type TEXT NOT NULL,
        options_json TEXT,
        likert_points INTEGER,
        is_reversed INTEGER NOT NULL DEFAULT 0,
        position INTEGER NOT NULL,
        FOREIGN KEY (section_id) REFERENCES survey_sections(id) ON DELETE CASCADE
    );
    """)

    # Migration: Task 36B — survey publish lifecycle + response collection
    survey_cols = {r[1] for r in conn.execute("PRAGMA table_info(surveys)").fetchall()}
    if "share_token" not in survey_cols:
        conn.execute("ALTER TABLE surveys ADD COLUMN share_token TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_surveys_share_token ON surveys(share_token)")
    if "mode" not in survey_cols:
        conn.execute("ALTER TABLE surveys ADD COLUMN mode TEXT")
    if "published_at" not in survey_cols:
        conn.execute("ALTER TABLE surveys ADD COLUMN published_at TEXT")
    if "closed_at" not in survey_cols:
        conn.execute("ALTER TABLE surveys ADD COLUMN closed_at TEXT")
    if "response_cap" not in survey_cols:
        conn.execute("ALTER TABLE surveys ADD COLUMN response_cap INTEGER NOT NULL DEFAULT 100")

    # Migration: Task 36C-4 — external data import metadata (NULL for non-imported surveys)
    if "import_filename" not in survey_cols:
        conn.execute("ALTER TABLE surveys ADD COLUMN import_filename TEXT")
    if "imported_at" not in survey_cols:
        conn.execute("ALTER TABLE surveys ADD COLUMN imported_at TEXT")
    if "imported_row_count" not in survey_cols:
        conn.execute("ALTER TABLE surveys ADD COLUMN imported_row_count INTEGER")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS survey_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_id INTEGER NOT NULL,
        is_pilot INTEGER NOT NULL DEFAULT 0,
        submitted_at TEXT NOT NULL,
        ip_hash TEXT NOT NULL,
        FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_survey_responses_survey ON survey_responses(survey_id);

    CREATE TABLE IF NOT EXISTS survey_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        response_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        answer_value TEXT,
        FOREIGN KEY (response_id) REFERENCES survey_responses(id) ON DELETE CASCADE,
        FOREIGN KEY (question_id) REFERENCES survey_questions(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_survey_answers_response ON survey_answers(response_id);
    """)

    # Migration: Task 32A — documents extra columns
    doc_cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "source_type" not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN source_type TEXT DEFAULT 'upload'")
    if "content_level" not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN content_level TEXT DEFAULT 'full_text'")
    if "openalex_id" not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN openalex_id TEXT")
    if "external_metadata" not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN external_metadata TEXT")

    conn.commit()


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
