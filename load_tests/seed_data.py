#!/usr/bin/env python3
"""Seed load test DB with 10 users, 10 projects, 50 chunks + vectors.

Run AFTER backend is started (so init_db has run) but before locust:
  DATABASE_URL=/tmp/rhq_loadtest.db python load_tests/seed_data.py
"""
import os, sys, sqlite3, struct, random, uuid
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import sqlite_vec
from passlib.context import CryptContext
from app.database import init_db

DB_PATH = os.environ.get("DATABASE_URL", "/tmp/rhq_loadtest.db")
TEST_PASSWORD = "LoadTest123!"
NUM_USERS = 10
CHUNKS_PER_PROJECT = 5

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _rand_emb() -> bytes:
    v = [random.gauss(0, 1) for _ in range(384)]
    norm = sum(x * x for x in v) ** 0.5 or 1.0
    return struct.pack("384f", *[x / norm for x in v])


def seed():
    conn = init_db(DB_PATH)
    now = datetime.utcnow().isoformat()
    reset = date(2026, 8, 1).isoformat()

    for i in range(1, NUM_USERS + 1):
        uid = str(uuid.uuid4())
        email = f"loadtest{i}@researcherhq-test.com"
        pw_hash = _pwd_ctx.hash(TEST_PASSWORD)

        conn.execute(
            """INSERT OR IGNORE INTO users
               (id, email, password_hash, tier, kredit_remaining, kredit_total,
                tokens_used_internal, reset_date, created_at)
               VALUES (?, ?, ?, 'pro', 999, 999, 0, ?, ?)""",
            (uid, email, pw_hash, reset, now),
        )

        pid = str(uuid.uuid4())
        conn.execute(
            """INSERT OR IGNORE INTO projects
               (id, user_id, title, research_mode, field, document_set_version, created_at)
               VALUES (?, ?, ?, 'general', 'Computer Science', 1, ?)""",
            (pid, uid, f"Projek Ujian {i}", now),
        )

        did = str(uuid.uuid4())
        conn.execute(
            """INSERT OR IGNORE INTO documents
               (id, project_id, filename, category, page_count, chunk_count, uploaded_at)
               VALUES (?, ?, 'sample.pdf', 'artikel', 5, ?, ?)""",
            (did, pid, CHUNKS_PER_PROJECT, now),
        )

        for j in range(CHUNKS_PER_PROJECT):
            cid = str(uuid.uuid4())
            text = (
                f"Kajian ini meneliti aspek {j} dalam bidang Computer Science. "
                "Metodologi kualitatif digunakan untuk menganalisis data. "
                "Dapatan menunjukkan hubungan yang signifikan antara pembolehubah. "
            ) * 10
            conn.execute(
                """INSERT OR IGNORE INTO chunks
                   (id, doc_id, page_number, chunk_index, text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (cid, did, j + 1, j, text, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO chunk_vectors(chunk_id, embedding) VALUES (?, ?)",
                (cid, _rand_emb()),
            )

    conn.commit()
    conn.close()
    print(f"[seed_data] OK — 10 users, 10 projects, {NUM_USERS * CHUNKS_PER_PROJECT} chunks → {DB_PATH}")


if __name__ == "__main__":
    seed()
