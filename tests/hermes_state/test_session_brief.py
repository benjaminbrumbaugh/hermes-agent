"""Session brief storage: one document per row, resolved across the compression lineage."""
import pytest

from hermes_state import SessionDB


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    return SessionDB(tmp_path / "state.db")


def _compress(db, parent, child):
    holder = f"holder-{child}"
    assert db.try_acquire_compression_lock(parent, holder, ttl_seconds=60)
    db.publish_compression_child(
        parent_session_id=parent, child_session_id=child, source="tui", system_prompt="p",
        messages=[{"role": "user", "content": f"summary for {child}"}], compression_lock_holder=holder)


def _brief(goal, count):
    return {"version": 1, "goal": goal, "status": "s", "completed": [], "blockers": [], "decisions": [],
            "updated_at": 1.0, "message_count": count}


def test_brief_written_before_compression_is_readable_from_the_child(db):
    db.create_session("root", "tui")
    db.append_message("root", "user", "hello")
    assert db.get_session_brief("root") is None
    assert db.set_session_brief("root", _brief("ship it", 2))
    _compress(db, "root", "tip")
    assert db.get_session_brief("tip")["goal"] == "ship it"


def test_newer_brief_on_the_tip_shadows_the_root(db):
    db.create_session("root", "tui")
    db.append_message("root", "user", "hello")
    db.set_session_brief("root", _brief("old", 2))
    _compress(db, "root", "tip")
    db.set_session_brief("tip", _brief("new", 3))
    assert db.get_session_brief("tip")["goal"] == "new"
    assert db.get_session_brief("root")["goal"] == "old"


def test_set_brief_on_missing_row_reports_false(db):
    assert db.set_session_brief("ghost", _brief("x", 1)) is False
