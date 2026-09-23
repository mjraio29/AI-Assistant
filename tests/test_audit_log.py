import tempfile
from pathlib import Path

from app.audit_log import clear_log, get_recent_calls, log_tool_call


def _tmp_db():
    return str(Path(tempfile.mkdtemp()) / "test.db")


def test_log_and_get_recent_calls_roundtrip():
    db = _tmp_db()
    log_tool_call("calculator", {"expression": "2+2"}, {"result": 4}, 12.3, db_path=db)

    calls = get_recent_calls(db_path=db)

    assert len(calls) == 1
    assert calls[0]["tool_name"] == "calculator"
    assert "2+2" in calls[0]["arguments"]
    assert calls[0]["duration_ms"] == 12.3


def test_get_recent_calls_returns_newest_first():
    db = _tmp_db()
    log_tool_call("first", {}, {}, 1.0, db_path=db)
    log_tool_call("second", {}, {}, 1.0, db_path=db)

    calls = get_recent_calls(db_path=db)

    assert calls[0]["tool_name"] == "second"
    assert calls[1]["tool_name"] == "first"


def test_get_recent_calls_empty_db_returns_empty():
    db = _tmp_db()
    assert get_recent_calls(db_path=db) == []


def test_clear_log_removes_entries():
    db = _tmp_db()
    log_tool_call("calculator", {}, {}, 1.0, db_path=db)

    clear_log(db_path=db)

    assert get_recent_calls(db_path=db) == []


def test_long_result_gets_summarized():
    db = _tmp_db()
    huge_result = {"text": "x" * 5000}
    log_tool_call("fetch_page", {"url": "https://example.com"}, huge_result, 5.0, db_path=db)

    calls = get_recent_calls(db_path=db)

    assert len(calls[0]["result"]) < 400
    assert calls[0]["result"].endswith("...")
