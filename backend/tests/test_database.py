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
