"""
Lightweight session registry for the desktop app.

`app.memory` already persists messages per session_id, keyed in SQLite -- but
it has no concept of a human-readable title or "list all my sessions". This
module is a thin JSON sidecar that adds exactly that, so the sidebar can show
"Resume prep" instead of a raw UUID.
"""
import json
import time
import uuid
from pathlib import Path

from app.config import settings
from app.memory import clear_session

_REGISTRY_PATH = Path(settings.db_path).parent / "sessions.json"


def _load() -> dict:
    if not _REGISTRY_PATH.exists():
        return {}
    return json.loads(_REGISTRY_PATH.read_text())


def _save(data: dict) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(data, indent=2))


def list_sessions() -> list[dict]:
    """Most recently updated first."""
    data = _load()
    sessions = [{"session_id": sid, **meta} for sid, meta in data.items()]
    sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
    return sessions


def create_session(title: str = "New chat") -> str:
    session_id = str(uuid.uuid4())
    data = _load()
    now = time.time()
    data[session_id] = {"title": title, "created_at": now, "updated_at": now}
    _save(data)
    return session_id


def touch_session(session_id: str, title: str | None = None) -> None:
    """Bump updated_at (for sidebar ordering) and optionally rename -- used to
    auto-title a session from the user's first message."""
    data = _load()
    if session_id not in data:
        data[session_id] = {"title": title or "New chat", "created_at": time.time(), "updated_at": time.time()}
    else:
        data[session_id]["updated_at"] = time.time()
        if title:
            data[session_id]["title"] = title
    _save(data)


def delete_session(session_id: str) -> None:
    data = _load()
    data.pop(session_id, None)
    _save(data)
    clear_session(session_id)
