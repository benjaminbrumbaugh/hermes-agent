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
    assert "decisions" not in db.get_session_brief("tip")


def test_newer_brief_on_the_tip_shadows_the_root(db):
    db.create_session("root", "tui")
    db.append_message("root", "user", "hello")
    db.set_session_brief("root", _brief("old", 2))
    _compress(db, "root", "tip")
    db.set_session_brief("tip", _brief("new", 3))
    assert db.get_session_brief("tip")["goal"] == "new"
    assert db.get_session_brief("root")["goal"] == "old"


def test_refresh_order_accepts_compaction_and_rejects_stale_write(db):
    db.create_session("s", "tui")
    newer = _brief("new", 4)
    assert db.set_session_brief("s", newer)
    compacted = _brief("compacted", 2)
    compacted["updated_at"] = 2.0
    assert db.set_session_brief("s", compacted)
    stale = _brief("old", 4)
    stale["updated_at"] = 1.5
    assert db.set_session_brief("s", stale) is False
    assert db.get_session_brief("s")["goal"] == "compacted"


def test_set_brief_on_missing_row_reports_false(db):
    assert db.set_session_brief("ghost", _brief("x", 1)) is False


def test_persistence_merges_explicit_task_updates_without_losing_inherited_work(db):
    db.create_session("root", "tui")
    parent = dict(id="repair", parent_id=None, goal="Repair sync", status="paused", detail="Resume after review")
    child = dict(id="review", parent_id="repair", goal="Review sync logs", status="completed", detail="Review delivered")
    prior = dict(_brief("Review sync logs", 8), version=3, tasks=[parent, child])
    assert db.set_session_brief("root", prior)
    _compress(db, "root", "tip")
    update = dict(_brief("Resume sync repair", 2), version=3, updated_at=2,
        tasks=[dict(parent, status="in_progress")])
    assert db.set_session_brief("tip", update)
    assert db.get_session_brief("tip")["tasks"] == [dict(parent, status="in_progress"), child]
    assert db.get_session_brief("root")["tasks"] == [parent, child]
    assert db.set_session_brief("tip", dict(update, updated_at=3, tasks=[]))
    assert db.get_session_brief("tip")["tasks"] == [dict(parent, status="in_progress"), child]
    assert db.set_session_brief("tip", dict(update, updated_at=4, tasks=[dict(child, parent_id=None)])) is False
    assert db.get_session_brief("tip")["tasks"] == [dict(parent, status="in_progress"), child]
