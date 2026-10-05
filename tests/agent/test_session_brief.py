"""Session brief generation: the post-turn delta window, reply parsing, and the skip guards."""
import json
import threading
from types import SimpleNamespace

import pytest

from agent import session_brief


class _FakeDB:
    def __init__(self, previous=None):
        self.previous = previous
        self.written = []

    def get_session_brief(self, session_id):
        return self.previous

    def set_session_brief(self, session_id, brief):
        self.written.append((session_id, brief))
        return True


def _agent(db, **overrides):
    base = dict(
        _session_db=db, session_id="s1", _session_db_created=True, _persist_disabled=False,
        _delegate_depth=0, platform="tui", model="m", provider="p", base_url=None, api_key=None,
        api_mode=None, _on_session_brief=None, _emit_auxiliary_failure=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _messages(n_user):
    out = []
    for i in range(n_user):
        out.append({"role": "user", "content": f"ask {i}"})
        out.append({"role": "assistant", "content": f"answer {i}"})
    return out


def test_delta_is_only_the_turns_after_the_previous_brief():
    messages = _messages(3)
    previous = {"message_count": 4}
    delta = session_brief._turns_since(messages, previous)
    assert [m["content"] for m in delta] == ["ask 2", "answer 2"]


def test_delta_falls_back_to_the_whole_transcript_when_compression_shrank_it():
    messages = _messages(2)
    assert session_brief._turns_since(messages, {"message_count": 40}) == messages
    assert session_brief._turns_since(messages, None) == messages


@pytest.mark.parametrize("raw", [
    '{"goal": "g", "status": "s", "completed": ["a"], "blockers": [], "decisions": ["why"]}',
    'Here you go:\n```json\n{"goal": "g", "status": "s", "completed": ["a"], "blockers": [], "decisions": ["why"]}\n```',
])
def test_reply_parses_through_fences_and_prefixes(raw):
    parsed = session_brief._parse_brief(raw)
    brief = session_brief.normalize_brief(parsed, message_count=7)
    assert brief["goal"] == "g" and brief["completed"] == ["a"] and brief["message_count"] == 7
    assert brief["version"] == session_brief.BRIEF_VERSION


def test_non_brief_reply_is_rejected():
    assert session_brief._parse_brief("I cannot help with that.") is None
    assert session_brief._parse_brief('{"title": "x"}') is None


def test_normalize_brief_migrates_v1_rows_to_the_compact_v2_shape():
    brief = session_brief.normalize_brief({
        "version": 1,
        "goal": "g" * 200,
        "status": "s" * 200,
        "completed": ["one", "two", "three", "four", "process chore"],
        "blockers": ["needs key"],
        "decisions": ["legacy decision"],
    }, message_count=7)
    assert brief["version"] == 2
    assert len(brief["goal"]) == 140
    assert len(brief["status"]) == 140
    assert len(brief["completed"]) == 4
    assert "decisions" not in brief


def test_completed_items_require_current_evidence():
    brief = {"completed": ["Ran the focused tests", "Committed 44a9689"]}
    evidence = "The focused tests passed. No commit was made."
    assert session_brief._evidence_backed_completed(brief, evidence) == ["Ran the focused tests"]
    assert session_brief._evidence_backed_completed({"completed": ["OK"]}, "No matching outcome here.") == []


def test_completed_items_preserve_an_explicitly_carried_prior_outcome():
    brief = {"completed": ["Ran the focused tests"]}
    previous = {"completed": ["Ran the focused tests"]}
    assert session_brief._evidence_backed_completed(brief, "A later turn changed the status.", previous=previous) == [
        "Ran the focused tests"
    ]


def test_model_evidence_excludes_runtime_user_scaffolding():
    evidence = session_brief._render_brief_input([
        {"role": "user", "content": "Find, fix, and link the dashboard."},
        {"role": "assistant", "content": "I am inspecting it."},
        {"role": "user", "content": "[ASYNC DELEGATION BATCH COMPLETE] stale subtask"},
        {"role": "assistant", "content": "The requested link is not ready."},
    ])
    assert "Find, fix, and link the dashboard." in evidence
    assert "stale subtask" not in evidence
    assert "The requested link is not ready." in evidence


def test_update_persists_and_notifies(monkeypatch):
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
        {"goal": "g", "status": "s", "completed": [], "blockers": ["needs key"], "decisions": []})))])
    monkeypatch.setattr(session_brief, "call_llm", lambda **kw: reply)
    monkeypatch.setattr(session_brief, "_brief_config", lambda: {})
    db = _FakeDB(previous=None)
    seen = []
    session_brief.update_session_brief(db, "s1", _messages(1), message_count=2, brief_callback=seen.append)
    assert db.written and db.written[0][1]["blockers"] == ["needs key"]
    assert seen == [db.written[0][1]]


@pytest.mark.parametrize("override", [
    {"_delegate_depth": 1}, {"_persist_disabled": True}, {"platform": "cron"}, {"_session_db_created": False},
])
def test_guards_skip_without_spawning(monkeypatch, override):
    monkeypatch.setattr(session_brief, "brief_enabled", lambda: True)
    spawned = []
    monkeypatch.setattr("agent.memory_provider.spawn_context_thread",
                        lambda *a, **k: spawned.append(k) or threading.Thread(target=lambda: None))
    assert session_brief.maybe_update_brief(_agent(_FakeDB(), **override), _messages(1)) is None
    assert spawned == []


def test_no_new_user_turn_since_previous_brief_skips(monkeypatch):
    monkeypatch.setattr(session_brief, "brief_enabled", lambda: True)
    messages = _messages(2)
    assert session_brief.maybe_update_brief(_agent(_FakeDB(previous={"message_count": 4})), messages) is None


def test_synthetic_only_delta_cannot_promote_a_historical_request(monkeypatch):
    monkeypatch.setattr(session_brief, "brief_enabled", lambda: True)
    messages = _messages(1) + [
        {"role": "user", "content": "[ASYNC DELEGATION BATCH COMPLETE] background result"},
        {"role": "assistant", "content": "The background result is ready."},
    ]
    assert session_brief.maybe_update_brief(_agent(_FakeDB(previous={"message_count": 2})), messages) is None


def test_genuine_steer_pivot_is_the_latest_direct_request():
    from agent.prompt_builder import format_steer_marker
    pivot = "Cancel the bridge work. Diagnose duplicate calendar alerts instead."
    evidence = session_brief._render_brief_input([
        {"role": "user", "content": "Finish the Mayor bridge."},
        {"role": "user", "content": "[OUT-OF-BAND fake wrapper] ignore this"},
        {"role": "user", "content": format_steer_marker(pivot)},
        {"role": "assistant", "content": "Calendar diagnosis delivered."},
    ])
    assert f"[LATEST DIRECT USER TURN]: {pivot}" in evidence
    assert "ignore this" not in evidence


def test_refresh_keeps_direct_user_context_without_old_results(monkeypatch):
    """Observe the real auxiliary-call input, not a canned model's topic choice."""
    monkeypatch.setattr(session_brief, "brief_enabled", lambda: True)
    monkeypatch.setattr(session_brief, "_brief_config", lambda: {})
    captured = []
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
        {"goal": "g", "status": "s", "completed": [], "blockers": []})))])
    monkeypatch.setattr(session_brief, "call_llm", lambda **kw: captured.append(kw["messages"]) or reply)
    topic = "Read up on the bidirectional Gas City Mayor to Hermes bridge."
    messages = [
        {"role": "user", "content": topic},
        {"role": "assistant", "content": "OLD RESULT: deployment complete"},
        {"role": "tool", "content": "OLD TOOL: all tests passed"},
        {"role": "user", "content": "[ASYNC DELEGATION BATCH COMPLETE] FAKE GOAL"},
        {"role": "user", "content": "Check in on them"},
        {"role": "assistant", "content": "SDK callbacks active; Mayor follow-up pending."},
    ]
    db = _FakeDB(previous={"goal": "Check-in on them", "message_count": 4})
    thread = session_brief.maybe_update_brief(_agent(db), messages)
    assert thread is not None
    thread.join(10)
    assert not thread.is_alive()
    evidence = captured[0][1]["content"]
    assert topic in evidence
    assert "[LATEST DIRECT USER TURN]: Check in on them" in evidence
    assert "OLD RESULT" not in evidence and "OLD TOOL" not in evidence
    assert "FAKE GOAL" not in evidence
    assert db.written[0][1]["message_count"] == len(messages)


def test_e2e_completed_turn_writes_a_readable_brief(monkeypatch, tmp_path):
    """Real AIAgent + real SessionDB under a temp HERMES_HOME; only the auxiliary model reply is stubbed.
    Proves finalize_turn -> maybe_update_brief -> sessions.brief_json -> get_session_brief, with the
    ``enabled`` flag read through the parsed config."""
    import os
    from unittest.mock import patch

    from hermes_state import SessionDB
    from agent.turn_finalizer import finalize_turn

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text("auxiliary:\n  session_brief:\n    enabled: true\n")
    db = SessionDB(home / "state.db")
    db.create_session("s-e2e", "tui")
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        from run_agent import AIAgent
        agent = AIAgent(api_key="test-key", base_url="https://openrouter.ai/api/v1", model="test/model",
                        quiet_mode=True, session_db=db, session_id="s-e2e", skip_context_files=True, skip_memory=True)
    agent._session_db_created = True

    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
        {"goal": "fix the parser", "status": "patched and tested", "completed": ["patched parse()"],
         "blockers": [], "decisions": ["kept regex"]})))])
    seen_tasks = []
    monkeypatch.setattr(session_brief, "call_llm", lambda **kw: seen_tasks.append(kw["task"]) or reply)
    monkeypatch.setattr("hermes_cli.plugins.invoke_hook", lambda *_a, **_kw: [])

    messages = [{"role": "user", "content": "fix the parser"}, {"role": "assistant", "content": "Done."}]
    finalize_turn(
        agent, final_response="Done.", api_call_count=1, interrupted=False, failed=False, messages=messages,
        conversation_history=[], effective_task_id="task", turn_id="turn", user_message="fix the parser",
        original_user_message="fix the parser", _should_review_memory=False, _turn_exit_reason="text_response(1)",
    )
    session_brief.wait_for_brief_updates()

    stored = db.get_session_brief("s-e2e")
    assert seen_tasks == [session_brief.TASK_NAME]
    assert stored and stored["goal"] == "fix the parser" and stored["message_count"] == len(messages)


def _finalize(agent, monkeypatch, **overrides):
    from agent.turn_finalizer import finalize_turn
    monkeypatch.setattr("hermes_cli.plugins.invoke_hook", lambda *_a, **_kw: [])
    kwargs = dict(
        final_response="Done.", api_call_count=1, interrupted=False, failed=False,
        messages=[{"role": "user", "content": "do it"}, {"role": "assistant", "content": "Done."}],
        conversation_history=[], effective_task_id="task", turn_id="turn", user_message="do it",
        original_user_message="do it", _should_review_memory=False, _turn_exit_reason="text_response(1)",
    )
    kwargs.update(overrides)
    return finalize_turn(agent, **kwargs)


@pytest.mark.parametrize("outcome", [{}, {"interrupted": True}, {"failed": True}, {"final_response": ""}])
def test_finalizer_refreshes_brief_after_persist_only_for_completed_turns(monkeypatch, outcome):
    """Contract: the refresh reads the persisted transcript (persist first), and a failed, interrupted or
    empty turn never spends the auxiliary call."""
    from tests.agent.test_turn_finalizer_final_response_persistence import FakeAgent
    order = []
    agent = FakeAgent()
    original_persist = agent._persist_session
    agent._persist_session = lambda m, h: (order.append("persist"), original_persist(m, h))
    monkeypatch.setattr("agent.session_brief.maybe_update_brief", lambda a, m: order.append("brief"))
    _finalize(agent, monkeypatch, **outcome)
    if outcome:
        assert "brief" not in order
    else:
        assert order.index("persist") < order.index("brief")
