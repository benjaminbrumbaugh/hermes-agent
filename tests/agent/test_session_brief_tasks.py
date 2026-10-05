"""V3 task history is longitudinal conversation work, not execution telemetry."""
import json
from types import SimpleNamespace

from agent import session_brief
from hermes_state import SessionDB


def task(identity, goal, status, parent=None):
    return dict(id=identity, parent_id=parent, goal=goal, status=status, detail="Observed state")


def test_generation_retains_parent_and_missing_history_through_compression(monkeypatch, tmp_path):
    db = SessionDB(tmp_path / "state.db")
    db.create_session("root", "tui")
    replies = iter([
        dict(goal="Repair calendar sync", status="RUNNING: Repair underway", blockers=[], tasks=[
            task("repair", "Repair calendar sync", "in_progress"),
            task("inspect", "Inspect duplicate alerts", "completed", "repair")]),
        dict(goal="Explain calendar permissions", status="DONE: Permissions explained", blockers=[], tasks=[
            task("repair", "Repair calendar sync", "paused"),
            task("permissions", "Explain calendar permissions", "completed", "repair")]),
        dict(goal="Resume calendar repair", status="RUNNING: Repair underway", blockers=[], tasks=[
            task("repair", "Repair calendar sync", "in_progress")]),
    ])
    calls = []
    def reply(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(next(replies))))])
    monkeypatch.setattr(session_brief, "call_llm", reply)
    monkeypatch.setattr(session_brief, "_brief_config", lambda: {})
    for sid, request, count in [("root", "Repair calendar sync", 2), ("root", "First explain permissions", 4)]:
        session_brief.update_session_brief(db, sid, [dict(role="user", content=request),
            dict(role="assistant", content="Permissions explained; calendar repair paused.")], message_count=count)
    assert db.try_acquire_compression_lock("root", "holder", ttl_seconds=60)
    db.publish_compression_child(parent_session_id="root", child_session_id="tip", source="tui",
        system_prompt="p", messages=[dict(role="user", content="summary")], compression_lock_holder="holder")
    session_brief.update_session_brief(db, "tip", [dict(role="user", content="Resume calendar repair"),
        dict(role="assistant", content="Calendar repair underway.")], message_count=2)
    stored = db.get_session_brief("tip")
    assert stored["version"] == 3
    by_id = {item["id"]: item for item in stored["tasks"]}
    assert by_id["repair"]["status"] == "in_progress"
    assert by_id["inspect"]["status"] == by_id["permissions"]["status"] == "completed"
    assert by_id["permissions"]["parent_id"] == "repair"
    assert db.get_session_brief("root")["tasks"][0]["status"] == "paused"
    assert '"id": "inspect"' in calls[1]["messages"][1]["content"]
    assert set(calls[0]["extra_body"]["response_format"]["json_schema"]["schema"]["properties"]) == {"goal", "status", "tasks", "blockers"}
    assert calls[0]["max_tokens"] >= 3000
    assert stored["completed"] == []  # Never manufacture legacy feature outcomes.
    # Another refresh can add history after this model call reads its previous context.
    def concurrent_reply(**kwargs):
        current = db.get_session_brief("tip")
        assert db.set_session_brief("tip", dict(current, tasks=current["tasks"] + [
            task("review", "Review calendar repair", "completed", "repair")]))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
            dict(goal="Resume calendar repair", status="RUNNING: Repair underway", blockers=[], tasks=[]))))])
    monkeypatch.setattr(session_brief, "call_llm", concurrent_reply)
    seen = []
    session_brief.update_session_brief(db, "tip", [dict(role="user", content="Continue calendar repair")],
        message_count=4, brief_callback=seen.append)
    assert seen == [db.get_session_brief("tip")]
    assert any(item["id"] == "review" for item in seen[0]["tasks"])
    db.close()


def test_overlapping_refresh_retains_latest_omitted_task_state(monkeypatch, tmp_path):
    db = SessionDB(tmp_path / "state.db")
    db.create_session("s", "tui")
    prior = dict(version=3, goal="Repair sync", status="RUNNING: Repair underway", completed=[], blockers=[],
        updated_at=1, message_count=2, tasks=[task("repair", "Repair sync", "in_progress")])
    assert db.set_session_brief("s", prior)
    paused = dict(prior["tasks"][0], status="paused", detail="Resume after explaining permissions")
    def concurrent_reply(**kwargs):
        assert db.set_session_brief("s", dict(prior, updated_at=2, tasks=[paused]))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
            dict(goal="Explain permissions", status="DONE: Permissions explained", blockers=[], tasks=[]))))])
    monkeypatch.setattr(session_brief, "_brief_config", lambda: {})
    monkeypatch.setattr(session_brief, "call_llm", concurrent_reply)
    seen = []
    session_brief.update_session_brief(db, "s", [dict(role="user", content="Explain permissions")],
        message_count=4, update_order=3, brief_callback=seen.append)
    assert db.get_session_brief("s")["tasks"] == [paused]
    assert seen == [db.get_session_brief("s")]
    resumed = dict(paused, status="in_progress", detail="Permissions explained; repair resumed")
    monkeypatch.setattr(session_brief, "call_llm", lambda **kw: SimpleNamespace(choices=[
        SimpleNamespace(message=SimpleNamespace(content=json.dumps(dict(
            goal="Resume sync repair", status="RUNNING: Repair resumed", blockers=[], tasks=[resumed]))))]))
    session_brief.update_session_brief(db, "s", [dict(role="user", content="Resume sync repair")],
        message_count=6, update_order=4, brief_callback=seen.append)
    assert db.get_session_brief("s")["tasks"] == [resumed]
    assert seen[-1] == db.get_session_brief("s")
    db.close()


def test_first_v3_refresh_rebuilds_bounded_paired_historical_outcomes(monkeypatch):
    monkeypatch.setattr(session_brief, "brief_enabled", lambda: True)
    monkeypatch.setattr(session_brief, "_brief_config", lambda: {})
    captured = []
    reply = dict(goal="Review calendar repair", status="UNCLEAR: Review pending", tasks=[], blockers=[])
    monkeypatch.setattr(session_brief, "call_llm", lambda **kw: captured.append(kw) or SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))]))
    messages = []
    for index in range(12):
        messages.extend([dict(role="user", content=f"Explain calendar issue {index}"),
                         dict(role="assistant", content=f"HISTORICAL OUTCOME {index}: explanation delivered")])
    messages.extend([dict(role="assistant", content="OLD PLAN", tool_calls=[{}]),
                     dict(role="user", content="Review calendar repair"),
                     dict(role="assistant", content="Current review pending")])
    class DB:
        def get_messages(self, sid, **kwargs):
            return messages
        def get_session_brief(self, sid):
            return dict(version=2, goal="Calendar repair", completed=["Legacy feature milestone"], message_count=24)
        def set_session_brief(self, sid, brief):
            return True
    agent = SimpleNamespace(_session_db=DB(), session_id="s", _session_db_created=True)
    thread = session_brief.maybe_update_brief(agent, messages)
    assert thread is not None
    thread.join(10)
    assert not thread.is_alive()
    evidence = captured[0]["messages"][1]["content"]
    assert "[HISTORICAL TASK OUTCOME EVIDENCE" in evidence
    assert "HISTORICAL OUTCOME 11" in evidence and "Explain calendar issue 11" in evidence
    # The contract now keeps initial subject-setting outcomes plus bounded recent history.
    assert "HISTORICAL OUTCOME 0:" in evidence
    assert "HISTORICAL OUTCOME 2:" not in evidence
    assert "OLD PLAN" not in evidence
    assert "[LATEST ASSISTANT TURN]: Current review pending" in evidence
    assert "[LATEST DIRECT USER TURN]: Review calendar repair" in evidence


def test_legacy_rebuild_recovers_compacted_subject_without_undone_requests(monkeypatch, tmp_path):
    db = SessionDB(tmp_path / "state.db")
    db.create_session("s", "tui")
    db.append_message("s", "user", "Investigate bidirectional communication between Gas City Mayor and Hermes")
    db.append_message("s", "assistant", "Bridge investigation delivered; integration remains unfinished")
    db._execute_write(lambda conn: conn.execute("UPDATE messages SET active=0, compacted=1 WHERE session_id='s'"))
    undone = db.append_message("s", "user", "UNDONE REQUEST: replace the bridge with calendar sync")
    db._execute_write(lambda conn: conn.execute("UPDATE messages SET active=0, compacted=0 WHERE id=?", (undone,)))
    db.append_message("s", "user", "Check in")
    db.append_message("s", "assistant", "Mayor reply pending")
    assert db.set_session_brief("s", dict(version=2, goal="Check in", status="RUNNING: Reply pending",
        completed=[], blockers=[], updated_at=1, message_count=4))
    monkeypatch.setattr(session_brief, "brief_enabled", lambda: True)
    monkeypatch.setattr(session_brief, "_brief_config", lambda: {})
    captured = []
    reply = dict(goal="Check Gas City Mayor to Hermes bridge progress", status="RUNNING: Mayor reply pending",
        tasks=[], blockers=[])
    monkeypatch.setattr(session_brief, "call_llm", lambda **kw: captured.append(kw) or SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))]))
    agent = SimpleNamespace(_session_db=db, session_id="s", _session_db_created=True)
    thread = session_brief.maybe_update_brief(agent, db.get_messages("s"))
    assert thread is not None
    thread.join(10)
    assert not thread.is_alive()
    evidence = captured[0]["messages"][1]["content"]
    assert "Investigate bidirectional communication between Gas City Mayor and Hermes" in evidence
    assert "UNDONE REQUEST" not in evidence
    assert "[LATEST DIRECT USER TURN]: Check in" in evidence
    db.close()


def test_malformed_task_updates_do_not_replace_unresolved_parent(monkeypatch, tmp_path):
    db = SessionDB(tmp_path / "state.db")
    db.create_session("s", "tui")
    prior = dict(version=3, goal="Repair sync", status="RUNNING: Repair underway", completed=[], blockers=[],
        updated_at=1, message_count=2, tasks=[task("parent", "Repair sync", "paused"),
            task("child", "Inspect alerts", "completed", "parent")])
    assert db.set_session_brief("s", prior)
    malformed = [
        [task("parent", "Repair sync", "completed"), task("parent", "Repair sync", "pending")],
        [task("a", "Inspect alerts", "pending", "b"), task("b", "Repair alerts", "pending", "a")],
        [task("new", "Inspect sync", "pending", "missing")],
        [task("parent", "Repair sync", "paused", "child")],
        [task("parent", "Repair sync", "unknown")],
        [dict(id="new", parent_id=None, goal="Inspect sync", status="pending")],
        "not a task list",
    ]
    monkeypatch.setattr(session_brief, "_brief_config", lambda: {})
    seen = []
    for tasks in malformed:
        reply = dict(goal="Inspect sync", status="UNCLEAR: Inspection pending", tasks=tasks, blockers=[])
        monkeypatch.setattr(session_brief, "call_llm", lambda **kw: SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))]))
        session_brief.update_session_brief(db, "s", [dict(role="user", content="Inspect sync")],
            message_count=4, brief_callback=seen.append)
        assert db.get_session_brief("s")["tasks"] == prior["tasks"]
        assert db.get_session_brief("s")["goal"] == prior["goal"]
        assert db.set_session_brief("s", dict(prior, tasks=tasks, updated_at=2)) is False
    assert seen == []
    db.close()
