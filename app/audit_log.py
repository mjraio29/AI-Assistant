"""
Audit log: records every tool call Robert makes -- which tool, with what
arguments, what came back, and how long it took. Useful for debugging day
to day, and it doubles as exactly the kind of tool-use audit trail a
security-conscious deployment would want (see the README's note on
red-teaming Robert).

SQLite-backed, same pattern as app.memory and app.long_term_memory: a
db_path parameter defaults to the real database but can be overridden,
which is what makes this testable without touching the real log.
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    result TEXT NOT NULL,
    duration_ms REAL NOT NULL,
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


def _summarize(value, max_len: int = 300) -> str:
    text = json.dumps(value, default=str)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def log_tool_call(tool_name: str, arguments: dict, result, duration_ms: float, db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO tool_call_log (tool_name, arguments, result, duration_ms, created_at) VALUES (?, ?, ?, ?, ?)",
            (tool_name, json.dumps(arguments, default=str), _summarize(result), duration_ms, time.time()),
        )


def get_recent_calls(limit: int = 100, db_path: str | None = None) -> list[dict]:
    """Most recent first."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT tool_name, arguments, result, duration_ms, created_at FROM tool_call_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"tool_name": r[0], "arguments": r[1], "result": r[2], "duration_ms": r[3], "created_at": r[4]}
        for r in rows
    ]


def clear_log(db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM tool_call_log")
