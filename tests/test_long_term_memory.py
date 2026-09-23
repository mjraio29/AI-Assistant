import tempfile
from pathlib import Path

from app.long_term_memory import add_fact, clear_facts, delete_fact, get_facts


def _tmp_db():
    return str(Path(tempfile.mkdtemp()) / "test.db")


def test_add_and_get_facts():
    db = _tmp_db()
    add_fact("User's name is Michael", db_path=db)
    add_fact("User prefers metric units", db_path=db)

    facts = get_facts(db_path=db)

    assert len(facts) == 2
    assert facts[0]["fact"] == "User's name is Michael"
    assert facts[1]["fact"] == "User prefers metric units"


def test_add_fact_rejects_empty_string():
    db = _tmp_db()
    result = add_fact("   ", db_path=db)
    assert "error" in result
    assert get_facts(db_path=db) == []


def test_delete_fact_removes_only_that_one():
    db = _tmp_db()
    add_fact("keep this", db_path=db)
    add_fact("delete this", db_path=db)
    facts = get_facts(db_path=db)
    to_delete = next(f["id"] for f in facts if f["fact"] == "delete this")

    delete_fact(to_delete, db_path=db)

    remaining = get_facts(db_path=db)
    assert len(remaining) == 1
    assert remaining[0]["fact"] == "keep this"


def test_clear_facts_removes_everything():
    db = _tmp_db()
    add_fact("fact one", db_path=db)
    add_fact("fact two", db_path=db)

    clear_facts(db_path=db)

    assert get_facts(db_path=db) == []


def test_facts_persist_across_separate_calls_same_db():
    db = _tmp_db()
    add_fact("persisted fact", db_path=db)
    # Simulate a fresh process reading the same db file
    facts = get_facts(db_path=db)
    assert facts[0]["fact"] == "persisted fact"
