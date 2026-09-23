"""
Persistent conversation memory backed by SQLite.

Design choice: memory is per session_id, not global. A CLI run, a web
session, and an API caller can each maintain their own thread without
stepping on each other. Swap this module out for Postgres/Redis later
without touching the orchestration code -- the public functions are the
contract.
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,   -- JSON-encoded content blocks (text and/or tool_use/tool_result)
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id);
"""


@contextmanager
def _connect(db_path: str | None = None):
    path = db_path or settings.db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_message(session_id: str, role: str, content: Any, db_path: str | None = None) -> None:
    """Store one turn. `content` is whatever the chat client expects/returns
    for a message's `content` field -- a string, or a list of content blocks."""
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, json.dumps(content), time.time()),
        )


def get_history(session_id: str, limit: int | None = None, db_path: str | None = None) -> list[dict]:
    """Return messages oldest-first, ready to hand to the assistant's chat client."""
    limit = limit or settings.max_history_messages
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    rows.reverse()
    return [{"role": role, "content": json.loads(content)} for role, content in rows]


def clear_session(session_id: str, db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
