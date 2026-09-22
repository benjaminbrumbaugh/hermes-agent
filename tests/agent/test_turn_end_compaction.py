"""``compression.timing: after_reply`` — threshold compaction at the END of a completed turn.

Contract: the eager pass reuses the preflight trigger, runs only after the turn's own persist,
re-persists the compacted set, rebuilds ``messages`` in place (the host and the gateway hold that
object), and is a strict no-op for the default timing, interrupted/failed turns, subagents, and
anything the preflight gate would have skipped.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from agent.conversation_compression import (
    COMPACTION_TIMING_NEXT_TURN, COMPACTION_TIMING_TURN_END, normalize_compaction_timing,
)
from agent.turn_finalizer import finalize_turn


class _Compressor:
    def __init__(self, *, threshold_tokens=1_000, over=True):
        self.threshold_tokens = threshold_tokens
        self.context_length = 10_000
        self.protect_first_n = 0
        self.protect_last_n = 1
        self.last_prompt_tokens = 0
        self._over = over

    def should_compress(self, tokens):
        return self._over

    def should_defer_preflight_to_real_usage(self, _tokens):
        return False

    def get_active_compression_failure_cooldown(self):
        return None


class FakeAgent:
    def __init__(self, *, timing=COMPACTION_TIMING_TURN_END, over=True):
        self.max_iterations = 90
        self.iteration_budget = SimpleNamespace(remaining=10, used=1, max_total=90)
        self.quiet_mode = True
        self.model = "test-model"
        self.provider = "test-provider"
        self.base_url = ""
        self.session_id = "sess-test"
        self.context_compressor = _Compressor(over=over)
        self.compression_enabled = True
        self.compression_timing = timing
        self._delegate_depth = 0
        self._persist_disabled = False
        self._cached_system_prompt = "sys"
        self._usage_anchor = None
        self._request_pressure_anchored = False
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_cache_read_tokens = 0
        self.session_cache_write_tokens = 0
        self.session_reasoning_tokens = 0
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.session_total_tokens = 0
        self.session_estimated_cost_usd = 0
        self.session_cost_status = "unknown"
        self.session_cost_source = "test"
        self._tool_guardrail_halt_decision = None
        self._interrupt_message = None
        self._response_was_previewed = True
        self._skill_nudge_interval = 0
        self._iters_since_skill = 0
        self.valid_tool_names = []
        self.persist_calls: list[tuple[list[dict[str, Any]], Any]] = []
        self.compress_calls: list[dict[str, Any]] = []
        self.statuses: list[str] = []
        self._persist_user_message_idx: int | None = 0
        self._persist_user_message_override: Any = None
        self._persist_user_message_timestamp: float | None = None
        self._last_compaction_in_place = True
        self._last_compression_attempt_recorded = False

    # -- compaction seam -------------------------------------------------
    def _compress_context(self, messages, system_message, *, approx_tokens, task_id):
        self.compress_calls.append({
            "n": len(messages), "system_message": system_message,
            "approx_tokens": approx_tokens, "task_id": task_id,
        })
        # Summary + the surviving tail (the current turn's user message and reply).
        return [{"role": "user", "content": "[summary]"}, *messages[-2:]], system_message

    def _persist_session(self, messages, conversation_history):
        self.persist_calls.append(([dict(m) for m in messages], conversation_history))

    # -- finalize_turn collaborators -------------------------------------
    def _handle_max_iterations(self, messages, api_call_count):
        raise AssertionError("not expected")

    def _emit_status(self, text, *_args, **_kwargs):
        self.statuses.append(text)

    def _safe_print(self, *_args, **_kwargs):
        pass

    def _save_trajectory(self, *_args, **_kwargs):
        pass

    def _cleanup_task_resources(self, *_args, **_kwargs):
        pass

    def _drop_trailing_empty_response_scaffolding(self, messages):
        pass

    def _apply_persist_user_message_override(self, messages):
        pass

    def _file_mutation_verifier_enabled(self):
        return False

    def _turn_completion_explainer_enabled(self):
        return False

    def _drain_pending_steer(self):
        return None

    def clear_interrupt(self):
        pass

    def _sync_external_memory_for_turn(self, **_kwargs):
        pass


def _transcript(user_text="question 3"):
    return [
        {"role": "user", "content": "question 1"},
        {"role": "assistant", "content": "answer 1"},
        {"role": "user", "content": "question 2"},
        {"role": "assistant", "content": "answer 2"},
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": "answer 3"},
    ]


def _finalize(agent, messages, **overrides):
    kwargs = dict(
        final_response="answer 3", api_call_count=1, interrupted=False, failed=False,
        messages=messages, conversation_history=[], effective_task_id="task", turn_id="turn",
        user_message="question 3", original_user_message="question 3",
        _should_review_memory=False, _turn_exit_reason="final_response", system_message="ephemeral",
    )
    kwargs.update(overrides)
    return finalize_turn(agent, **kwargs)


@pytest.fixture(autouse=True)
def _no_plugin_hooks(monkeypatch):
    monkeypatch.setattr("hermes_cli.plugins.invoke_hook", lambda *_a, **_kw: [])


def test_after_reply_compacts_after_durable_persist_and_repersists():
    """The reply is persisted FIRST, then the compacted set; the host's ``messages`` object is the
    compacted transcript so the next turn (and the gateway's cached history) starts on it."""
    agent = FakeAgent()
    messages = _transcript()

    result = _finalize(agent, messages)

    assert len(agent.compress_calls) == 1
    call = agent.compress_calls[0]
    assert call["n"] == 6 and call["system_message"] == "ephemeral" and call["task_id"] == "task"
    # First persist: the full turn (reply durable before any archive). Second: the compacted set.
    assert [len(m) for m, _ in agent.persist_calls] == [6, 3]
    assert agent.persist_calls[1][0][0]["content"] == "[summary]"
    assert result["messages"] is messages
    assert [m["content"] for m in messages] == ["[summary]", "question 3", "answer 3"]
    # The persist-override anchor followed this turn's user message into the rebuilt list.
    assert agent._persist_user_message_idx == 1
    assert any("Turn-end compression" in s for s in agent.statuses)


def test_after_reply_rotation_hands_full_compacted_list_to_persist():
    """A rotated session (not in-place) persists with a ``None`` baseline so the child session
    receives the whole compacted transcript — the same contract as the preflight pass."""
    agent = FakeAgent()
    agent._last_compaction_in_place = False

    _finalize(agent, _transcript())

    assert agent.persist_calls[1][1] is None


def test_default_timing_never_compacts_at_turn_end():
    agent = FakeAgent(timing=COMPACTION_TIMING_NEXT_TURN)
    messages = _transcript()

    _finalize(agent, messages)

    assert agent.compress_calls == []
    assert len(agent.persist_calls) == 1 and len(messages) == 6


@pytest.mark.parametrize("flag", ["interrupted", "failed"])
def test_interrupted_or_failed_turn_skips_eager_compaction(flag):
    agent = FakeAgent()
    messages = _transcript()

    _finalize(agent, messages, **{flag: True})

    assert agent.compress_calls == []
    assert len(messages) == 6


@pytest.mark.parametrize(
    "attr, value",
    [("_delegate_depth", 1), ("_persist_disabled", True), ("compression_enabled", False)],
)
def test_subagents_forks_and_disabled_compression_skip_eager_pass(attr, value):
    agent = FakeAgent()
    setattr(agent, attr, value)

    _finalize(agent, _transcript())

    assert agent.compress_calls == []


def test_under_threshold_is_a_no_op_with_single_persist():
    agent = FakeAgent(over=False)
    messages = _transcript()

    _finalize(agent, messages)

    assert agent.compress_calls == []
    assert len(agent.persist_calls) == 1
    assert agent.statuses == []


def test_compressor_skip_path_leaves_transcript_and_persist_untouched():
    """``_compress_context`` returning its input (lock held, breaker, nothing summarizable) must
    not trigger a second persist or mutate the list."""
    agent = FakeAgent()
    agent._compress_context = lambda messages, system_message, **_kw: (messages, system_message)
    messages = _transcript()

    _finalize(agent, messages)

    assert len(agent.persist_calls) == 1 and len(messages) == 6


def test_summarizer_failure_never_costs_the_persisted_reply():
    """The eager pass is its own guarded cleanup step: an exception surfaces as a cleanup error
    while the reply already reached durable storage and ``result`` still carries it."""
    agent = FakeAgent()

    def boom(*_a, **_kw):
        raise RuntimeError("summarizer down")

    agent._compress_context = boom
    messages = _transcript()

    result = _finalize(agent, messages)

    assert result["final_response"] == "answer 3"
    assert len(agent.persist_calls) == 1 and len(messages) == 6


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, COMPACTION_TIMING_NEXT_TURN),
        ("", COMPACTION_TIMING_NEXT_TURN),
        ("bogus", COMPACTION_TIMING_NEXT_TURN),
        ("after_reply", COMPACTION_TIMING_TURN_END),
        (" After-Reply ", COMPACTION_TIMING_TURN_END),
        ("before_next_turn", COMPACTION_TIMING_NEXT_TURN),
    ],
)
def test_normalize_compaction_timing(raw, expected):
    assert normalize_compaction_timing(raw) == expected


def test_config_key_reaches_agent_through_the_compression_parser():
    """``compression.timing`` in config.yaml lands on ``agent.compression_timing`` via the same
    parser every other compression key uses; absent/unknown falls back to the default."""
    from agent.agent_init import _parse_compression_config

    stub = SimpleNamespace(model="test-model", provider=None, base_url="")
    assert _parse_compression_config(stub, {"compression": {"timing": "after_reply"}}).timing == (
        COMPACTION_TIMING_TURN_END
    )
    assert _parse_compression_config(stub, {"compression": {}}).timing == COMPACTION_TIMING_NEXT_TURN
    assert _parse_compression_config(stub, {"compression": {"timing": "later"}}).timing == (
        COMPACTION_TIMING_NEXT_TURN
    )


def test_desktop_schema_exposes_timing_as_a_select():
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    from hermes_cli.web_server_config import CONFIG_SCHEMA

    entry = CONFIG_SCHEMA["compression.timing"]
    assert entry["type"] == "select"
    assert DEFAULT_CONFIG["compression"]["timing"] in entry["options"]
    assert set(entry["options"]) == {COMPACTION_TIMING_NEXT_TURN, COMPACTION_TIMING_TURN_END}


# ── End-to-end: real AIAgent + real SessionDB ──


def _real_agent(tmp_path, monkeypatch, *, timing):
    """Real ``AIAgent`` wired to a real ``SessionDB`` with ``compression.timing`` read from a
    temp-``HERMES_HOME`` config.yaml through the same parser production uses."""
    from hermes_state import SessionDB
    from tests.agent.test_compression_concurrent_fork import _build_agent_with_db

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text(f"compression:\n  timing: {timing}\n")
    monkeypatch.setattr("hermes_cli.plugins.invoke_hook", lambda *_a, **_kw: [])
    monkeypatch.setattr("agent.auxiliary_client.set_runtime_main", lambda *a, **k: None)

    db = SessionDB(db_path=home / "state.db")
    sid = "TURN_END_E2E"
    db.create_session(sid, source="cli")
    agent = _build_agent_with_db(db, sid)
    agent.compression_enabled = True
    cc = agent.context_compressor
    # The shared stub drops everything but a fixed tail; keep the real last two rows so the
    # durable transcript can be checked for the reply that just landed.
    cc.compress.side_effect = lambda messages, *a, **k: [
        {"role": "user", "content": "[CONTEXT COMPACTION] summary"}, *messages[-2:],
    ]
    cc.threshold_tokens = 1_000
    cc.context_length = 10_000
    cc.summary_target_ratio = 0.20
    cc.protect_first_n = 0
    cc.protect_last_n = 1
    cc.awaiting_real_usage_after_compression = False
    cc.should_compress = lambda tokens: tokens >= 1_000
    cc.should_defer_preflight_to_real_usage = lambda _t: False
    cc.get_active_compression_failure_cooldown = lambda *a, **k: None
    cc.emit_automatic_compaction_status = True
    del cc.get_automatic_compaction_status_message
    agent._cached_system_prompt = "SYSTEM"
    agent._delegate_depth = 0
    return db, sid, agent


def _e2e_turn(agent, monkeypatch):
    history = [{"role": "user", "content": f"m{i} " + "x" * 400} for i in range(12)]
    # The prior turns are already durable rows (what a live session has before this turn).
    agent._session_db.replace_messages(agent.session_id, history)
    history = agent._session_db.get_messages_as_conversation(agent.session_id)
    messages = [*history, {"role": "user", "content": "latest"}, {"role": "assistant", "content": "reply"}]
    agent._persist_user_message_idx = len(messages) - 2
    monkeypatch.setattr("agent.turn_context.estimate_request_tokens_rough", lambda *a, **k: 5_000)
    result = finalize_turn(
        agent, final_response="reply", api_call_count=1, interrupted=False, failed=False,
        messages=messages, conversation_history=history, effective_task_id="task", turn_id="turn",
        user_message="latest", original_user_message="latest", _should_review_memory=False,
        _turn_exit_reason="final_response", system_message=None,
    )
    return messages, result


def test_e2e_after_reply_config_compacts_and_persists_through_real_agent(tmp_path, monkeypatch):
    """config.yaml → parser → ``agent.compression_timing`` → finalize → real compressor call →
    durable SessionDB rows hold the compacted transcript with the reply intact."""
    db, sid, agent = _real_agent(tmp_path, monkeypatch, timing="after_reply")
    assert agent.compression_timing == COMPACTION_TIMING_TURN_END

    messages, result = _e2e_turn(agent, monkeypatch)

    agent.context_compressor.compress.assert_called_once()
    assert result["messages"] is messages
    assert messages[0]["content"].startswith("[CONTEXT COMPACTION]")
    live = db.get_messages_as_conversation(agent.session_id)
    assert live and live[0]["content"].startswith("[CONTEXT COMPACTION]")
    assert live[-1]["role"] == "assistant" and live[-1]["content"] == "reply"


def test_e2e_default_config_leaves_turn_end_alone(tmp_path, monkeypatch):
    db, sid, agent = _real_agent(tmp_path, monkeypatch, timing="before_next_turn")
    assert agent.compression_timing == COMPACTION_TIMING_NEXT_TURN

    messages, _ = _e2e_turn(agent, monkeypatch)

    agent.context_compressor.compress.assert_not_called()
    assert len(messages) == 14
    assert len(db.get_messages_as_conversation(sid)) == 14


def test_e2e_after_reply_defers_to_a_held_compression_lock(tmp_path, monkeypatch):
    """Another holder's per-session lock makes the eager pass a strict no-op — the reply is still
    persisted, nothing rotates, and the foreign lease is untouched."""
    db, sid, agent = _real_agent(tmp_path, monkeypatch, timing="after_reply")
    assert db.try_acquire_compression_lock(sid, "external_holder") is True

    messages, _ = _e2e_turn(agent, monkeypatch)

    agent.context_compressor.compress.assert_not_called()
    assert agent.session_id == sid
    assert db.get_compression_lock_holder(sid) == "external_holder"
    assert len(messages) == 14
    assert db.get_messages_as_conversation(sid)[-1]["content"] == "reply"
