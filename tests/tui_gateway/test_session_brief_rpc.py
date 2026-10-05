"""RPC-level tests for ``session.brief`` (tui_gateway).

The desktop Brief pane keys by the SELECTED stored session id, and most conversations a user
clicks in the list are not live in this process. ``session.brief`` therefore resolves like
``session.archive``: a live runtime id first, else a stored id/key through the profile db.
Regression: the handler was session-scoped only, so every non-live selection errored and the
pane kept showing the previous conversation's brief.
"""

import pytest

import tui_gateway.server as srv
import tui_gateway.methods_session  # noqa: F401  (registers the RPC methods)
from hermes_state import SessionDB


@pytest.fixture
def db(tmp_path, monkeypatch):
    database = SessionDB(tmp_path / "state.db")
    monkeypatch.setattr(srv, "_get_db", lambda: database)
    try:
        yield database
    finally:
        database.close()


def _call(method: str, params: dict) -> dict:
    return srv._methods[method](1, params)


def _brief(goal: str) -> dict:
    return {
        "version": 1, "goal": goal, "status": "s", "completed": [], "blockers": [], "decisions": [],
        "updated_at": 1.0, "message_count": 2,
    }


def test_brief_resolves_stored_id_without_live_session(db):
    db.create_session("stored-chat", source="desktop")
    assert db.set_session_brief("stored-chat", _brief("ship it"))
    assert srv._find_live_session_by_key("stored-chat") is None

    envelope = _call("session.brief", {"session_id": "stored-chat"})
    assert "error" not in envelope, envelope
    assert envelope["result"]["brief"]["goal"] == "ship it"


def test_brief_is_null_for_a_stored_session_without_one(db):
    db.create_session("fresh", source="desktop")
    envelope = _call("session.brief", {"session_id": "fresh"})
    assert "error" not in envelope, envelope
    assert envelope["result"]["brief"] is None


def test_brief_requires_a_session_id(db):
    assert _call("session.brief", {})["error"]["code"] == 4006


def test_task_hierarchy_crosses_result_and_event_contracts():
    """Neither reconnect snapshots nor refresh events may strip resumable parent context."""
    from tui_gateway.contracts.events import SessionBriefPayload
    from tui_gateway.contracts.sessions import SessionBriefResult

    parent = {"id": "bridge", "parent_id": None, "goal": "Investigating the Mayor ↔ Hermes bridge",
              "status": "paused", "detail": "Return after fixing the brief"}
    child = {"id": "brief", "parent_id": "bridge", "goal": "Fixing conversation summaries",
             "status": "in_progress", "detail": "Task model implementation underway"}
    brief = {**_brief("Fixing conversation summaries"), "version": 3, "tasks": [parent, child]}
    brief.pop("decisions")
    snapshot = SessionBriefResult.model_validate({"brief": brief}).model_dump()
    update = SessionBriefPayload.model_validate({"session_id": "chat", "brief": brief}).model_dump()
    assert snapshot["brief"]["tasks"] == update["brief"]["tasks"] == [parent, child]
