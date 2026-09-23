"""
Long-term memory: facts that persist across sessions and app restarts,
separate from the per-session conversation history in app.memory.

app.memory gives Robert context within one conversation. This module is
what lets him remember your name or preferences in a brand new chat --
facts here get folded into the system prompt on every turn, in every
session, until you remove them.
"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS long_term_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    created_at REAL NOT NULL
);
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


def add_fact(fact: str, db_path: str | None = None) -> dict:
    fact = fact.strip()
    if not fact:
        return {"error": "Empty fact, nothing saved."}
    with _connect(db_path) as conn:
        conn.execute("INSERT INTO long_term_facts (fact, created_at) VALUES (?, ?)", (fact, time.time()))
    return {"saved": fact}


def get_facts(limit: int = 100, db_path: str | None = None) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, fact FROM long_term_facts ORDER BY id ASC LIMIT ?", (limit,)
        ).fetchall()
    return [{"id": r[0], "fact": r[1]} for r in rows]


def delete_fact(fact_id: int, db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM long_term_facts WHERE id = ?", (fact_id,))


def clear_facts(db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM long_term_facts")
