import tempfile
from pathlib import Path

from app.memory import clear_session, get_history, save_message


def _tmp_db():
    return str(Path(tempfile.mkdtemp()) / "test.db")


def test_save_and_get_history_roundtrip():
    db = _tmp_db()
    save_message("s1", "user", "hello", db_path=db)
    save_message("s1", "assistant", [{"type": "text", "text": "hi there"}], db_path=db)

    history = get_history("s1", db_path=db)

    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "hello"}
    assert history[1]["role"] == "assistant"
    assert history[1]["content"][0]["text"] == "hi there"


def test_history_is_isolated_per_session():
    db = _tmp_db()
    save_message("a", "user", "msg for a", db_path=db)
    save_message("b", "user", "msg for b", db_path=db)

    assert len(get_history("a", db_path=db)) == 1
    assert len(get_history("b", db_path=db)) == 1
    assert get_history("a", db_path=db)[0]["content"] == "msg for a"


def test_history_respects_limit_and_order():
    db = _tmp_db()
    for i in range(5):
        save_message("s", "user", f"msg{i}", db_path=db)

    history = get_history("s", limit=2, db_path=db)

    assert len(history) == 2
    assert [m["content"] for m in history] == ["msg3", "msg4"]


def test_clear_session_removes_only_that_session():
    db = _tmp_db()
    save_message("keep", "user", "stay", db_path=db)
    save_message("drop", "user", "go", db_path=db)

    clear_session("drop", db_path=db)

    assert get_history("keep", db_path=db) == [{"role": "user", "content": "stay"}]
    assert get_history("drop", db_path=db) == []
