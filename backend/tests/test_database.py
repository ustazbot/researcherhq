import sqlite3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite_vec
from app.database import init_db

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
    assert required.issubset(tables), f"Missing tables: {required - tables}"
    conn.close()

def test_foreign_keys_enabled(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    result = conn.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1, "Foreign keys must be enabled"
    conn.close()

def test_wal_mode(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    result = conn.execute("PRAGMA journal_mode").fetchone()
    assert result[0] == "wal", f"Expected WAL mode, got: {result[0]}"
    conn.close()

def test_chunk_vectors_virtual_table(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    # chunk_vectors is a virtual table — check it exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_vectors'"
    )
    assert cursor.fetchone() is not None, "chunk_vectors virtual table must exist"
    conn.close()

def test_users_schema(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    # Verify users table has required columns
    cursor = conn.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cursor.fetchall()}
    required = {"id", "email", "password_hash", "tier", "kredit_remaining", "kredit_total", "reset_date", "created_at"}
    assert required.issubset(cols), f"Missing columns: {required - cols}"
    conn.close()

def test_migration_user_profile_columns(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    assert "name" in cols
    assert "institution" in cols
    conn.close()

def test_migration_project_onboarding_columns(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
    assert "output_target" in cols
    assert "degree_level" in cols
    assert "proposal_status" in cols
    assert "citation_style" in cols
    conn.close()


def test_get_db_sets_wal_mode(tmp_path):
    """get_db() must explicitly set WAL on each connection (Gap 2 fix)."""
    import app.database as db_module
    db_path = str(tmp_path / "getdb_wal.db")
    init_db(db_path)  # create schema
    orig = db_module._db_path
    db_module._db_path = db_path
    try:
        with db_module.get_db() as conn:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0] == "wal", f"get_db() connection not in WAL mode: {result[0]}"
    finally:
        db_module._db_path = orig


def test_get_db_concurrent_writes_no_lock_error(tmp_path):
    """50 threads writing concurrently must not raise OperationalError (Gap 1 fix)."""
    import threading, app.database as db_module
    db_path = str(tmp_path / "concurrent.db")
    init_db(db_path)
    orig = db_module._db_path
    db_module._db_path = db_path
    errors = []

    def writer(i):
        try:
            import uuid
            from datetime import datetime
            with db_module.get_db() as c:
                c.execute(
                    "INSERT INTO users (id, email, password_hash, created_at) VALUES (?,?,?,?)",
                    (str(uuid.uuid4()), f"u{i}@t.com", "x", datetime.utcnow().isoformat())
                )
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert not errors, f"Concurrent write errors: {errors}"
    db_module._db_path = orig
