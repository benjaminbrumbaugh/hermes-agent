"""Model continuation is not a newly accepted human transcript turn."""

from unittest.mock import patch

import pytest

from agent.codex_responses_adapter import _chat_messages_to_responses_input
from agent.compaction_display import project_compaction_message_for_display
from agent.context_compressor import ContextCompressor, SUMMARY_PREFIX, _INFLIGHT_TASK_REPLAY_HEADER, _SUMMARY_END_MARKER, _MERGED_PRIOR_CONTEXT_HEADER, _MERGED_SUMMARY_DELIMITER, _content_text_for_contains, _strip_historical_media
from agent.conversation_compression import compress_context
from hermes_state import SessionDB
from hermes_state_timeline import get_session_timeline, get_session_messages_around
from run_agent import AIAgent

ASK = "Inspect the storage bug without changing unrelated files."
IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="


def _agent(db, sid):
    agent = AIAgent(api_key="test-key", base_url="https://example.invalid/v1", model="test/model",
                    quiet_mode=True, session_db=db, session_id=sid, skip_context_files=True,
                    skip_memory=True, enabled_toolsets=[])
    agent.compression_in_place = True
    agent.context_compressor = ContextCompressor(model="test/model", protect_first_n=1,
                                                protect_last_n=3, quiet_mode=True)
    agent.context_compressor.tail_token_budget = 250
    return agent


def _groups(start):
    for index in range(start, start + 10):
        cid = f"call_{index}"
        yield {"role": "assistant", "content": "", "tool_calls": [{"id": cid, "type": "function",
               "function": {"name": "inspect", "arguments": '{"fixture":"' + 'x' * 440 + '"}'}}]}
        yield {"role": "tool", "tool_call_id": cid, "content": "result:" + "r" * 110}


def _visible(rows):
    return [view for row in rows if (view := project_compaction_message_for_display(row)) is not None]


def _assert_wire(messages):
    wire = _chat_messages_to_responses_input(messages, current_issuer_kind="codex_backend")
    text = lambda row: "".join(p.get("text", "") for p in row.get("content", []) if isinstance(p, dict))
    boundary = next(i for i, row in enumerate(wire) if _SUMMARY_END_MARKER in text(row))
    live = [text(row).rsplit(_SUMMARY_END_MARKER, 1)[-1] for row in wire[boundary:] if row.get("role") == "user"]
    assert sum(ASK in part for part in live) == 1
    assert sum(_INFLIGHT_TASK_REPLAY_HEADER in part for part in live) == 1
    assert not any("display_metadata" in row or "message_uid" in row for row in wire)


@pytest.mark.parametrize("multipart", [False, True], ids=["text", "multipart-text"])
def test_real_compaction_reopen_keeps_accepted_turn_not_model_replay(tmp_path, multipart):
    path = tmp_path / "state.db"
    db = SessionDB(path)
    sid = "continuation"
    db.create_session(sid, "desktop")
    db.create_session("sibling", "desktop")
    db.append_message("sibling", "user", ASK, timestamp=1.0)
    sibling = db.get_messages("sibling", include_inactive=True)
    payload = [{"type": "text", "text": ASK}] if multipart else ASK
    messages = [{"role": "user", "content": "Opening request", "timestamp": 1.0},
                {"role": "assistant", "content": "Opening completed", "timestamp": 2.0}]
    for index in range(3):
        messages.extend([{"role": "user", "content": f"Completed request {index}", "timestamp": 4.0 + index * 2},
                         {"role": "assistant", "content": "Completed:" + "a" * 2000, "timestamp": 5.0 + index * 2}])
    messages.append({"role": "user", "content": payload, "timestamp": 15.0})
    messages.extend(_groups(0))
    agent = _agent(db, sid)
    try:
        agent._flush_messages_to_session_db(messages)
        accepted = db.get_messages(sid)[8]
        for cycle in range(3):
            if cycle:
                # Cycle one continues the same task; cycle two accepts identical text independently.
                if cycle == 2:
                    messages.extend([{"role": "assistant", "content": "Completed", "timestamp": 20.0 + cycle},
                                     {"role": "user", "content": payload, "timestamp": 30.0 + cycle}])
                messages.extend(_groups(cycle * 10))
                agent._flush_messages_to_session_db(messages)
            before = db.get_messages(sid, include_compacted=True)
            accepted_users = [row for row in _visible(before) if row["role"] == "user"]
            with patch.object(ContextCompressor, "_call_summary_llm", return_value="## Completed Actions\nEarlier requests completed.\n## Active State\nInspecting storage.") as transport:
                messages, _ = compress_context(agent, messages, approx_tokens=90_000, system_message="fixture", force=True)
                assert transport.called
            assert agent._last_compaction_in_place
            _assert_wire(messages)
            assert all(_INFLIGHT_TASK_REPLAY_HEADER not in str(row["content"]) for row in _visible(messages))
            agent._flush_messages_to_session_db(messages)
            db.close()
            db = SessionDB(path)
            model, resume = db.get_resume_conversations(sid)
            _assert_wire(model)
            rows = db.get_messages(sid, include_compacted=True)
            users = [row for row in _visible(rows) if row["role"] == "user"]
            assert [(row["message_uid"], row["content"], row["timestamp"]) for row in users] == [
                (row["message_uid"], row["content"], row["timestamp"]) for row in accepted_users]
            assert users[4]["message_uid"] == accepted["message_uid"]
            assert users[4]["content"] == accepted["content"]
            assert [row["content"] for row in _visible(resume) if row["role"] == "user"] == [row["content"] for row in users]
            assert all(_INFLIGHT_TASK_REPLAY_HEADER not in str(row["content"]) for row in _visible(rows))
            for latest in (False, True):
                expected = rows[::-1][1:][:3][::-1] if latest else rows[1:4]
                assert db.get_messages(sid, include_compacted=True, limit=3, offset=1, latest=latest) == expected
            assert [entry["preview"] for entry in get_session_timeline(db, sid)["entries"]] == ["Opening request"] + [f"Completed request {i}" for i in range(3)] + [ASK] * (1 + int(cycle == 2))
            assert db.get_messages("sibling", include_inactive=True) == sibling
            db._execute_write(lambda conn: conn.execute("UPDATE messages SET display_order=NULL, display_identity=NULL WHERE session_id=?", (sid,)))
            db.close()
            db = SessionDB(path, read_only=True)
            legacy = db.get_messages(sid, include_compacted=True)
            assert [(row["message_uid"], row["content"]) for row in legacy] == [(row["message_uid"], row["content"]) for row in rows]
            for latest in (False, True):
                expected = legacy[::-1][1:][:3][::-1] if latest else legacy[1:4]
                assert db.get_messages(sid, include_compacted=True, limit=3, offset=1, latest=latest) == expected
            db.close()
            db = SessionDB(path)
            messages = db.get_messages_as_conversation(sid, include_row_ids=True)
            agent = _agent(db, sid)
    finally:
        db.close()


@pytest.mark.parametrize("multipart", [False, True], ids=["text", "image"])
def test_existing_replay_requires_source_identity_and_never_rewrites_model_history(tmp_path, multipart):
    # A genuine prior-tail user may quote the exact generated prefix; only the
    # synthetic suffix after the summary is omitted, never that accepted text.
    literal = _INFLIGHT_TASK_REPLAY_HEADER + "\n" + ASK
    prior = {"role": "user", "content": _MERGED_PRIOR_CONTEXT_HEADER + "\n" + literal + "\n\n" +
             _MERGED_SUMMARY_DELIMITER + "\n" + SUMMARY_PREFIX + "\nContext\n" +
             _SUMMARY_END_MARKER + "\n" + literal}
    assert project_compaction_message_for_display(prior)["content"] == literal
    path = tmp_path / "state.db"
    db = SessionDB(path)
    db.create_session("history", "desktop")
    db.create_session("sibling", "desktop")
    payload = ([{"type": "text", "text": ASK}, {"type": "image_url", "image_url": {"url": IMAGE}}]
               if multipart else ASK)
    original = {"role": "user", "content": payload, "timestamp": 1.0}
    _agent(db, "history")._flush_messages_to_session_db([original, {"role": "assistant", "content": "Working", "timestamp": 2.0}])
    source = db.get_messages("history")[0]
    replay = dict(original)
    replay.pop("_db_persisted", None)
    replay["content"] = ([{"type": "text", "text": _INFLIGHT_TASK_REPLAY_HEADER + "\n"}] + payload
                         if multipart else _INFLIGHT_TASK_REPLAY_HEADER + "\n" + ASK)
    carrier = {"role": "user", "content": SUMMARY_PREFIX + "\nContext\n" + _SUMMARY_END_MARKER,
               "_compressed_summary": True, "display_kind": "hidden", "timestamp": 3.0}
    db.archive_and_compact("history", [carrier, {"role": "assistant", "content": "Working", "timestamp": 4.0}, replay])
    # Header-looking independently accepted text has no source witness; never hide it by text alone.
    authored = db.append_message("history", "user", _INFLIGHT_TASK_REPLAY_HEADER + "\n" + ASK, timestamp=1.0)
    db.append_message("sibling", "user", _INFLIGHT_TASK_REPLAY_HEADER + "\n" + ASK,
                      timestamp=1.0, message_uid=original["message_uid"])
    for indexed in (True, False):
        if not indexed:
            db._execute_write(lambda conn: conn.execute("UPDATE messages SET display_order=NULL, display_identity=NULL"))
        db.close()
        db = SessionDB(path, read_only=True)
        try:
            audit = [tuple(row) for row in db._read_all("SELECT * FROM messages ORDER BY id")]
            rows = db.get_messages("history", include_compacted=True)
            visible = _visible(rows)
            assert [row["id"] for row in visible if row["role"] == "user"] == [source["id"], authored]
            assert visible[0]["content"] == source["content"]
            _, resume = db.get_resume_conversations("history")
            assert [row["content"] for row in _visible(resume) if row["role"] == "user"] == [source["content"], _INFLIGHT_TASK_REPLAY_HEADER + "\n" + ASK]
            entries = get_session_timeline(db, "history")["entries"]
            assert [entry["row_id"] for entry in entries] == [source["id"], authored]
            jump = get_session_messages_around(db, "history", source["id"])
            assert jump is not None and jump["messages"][0]["id"] == source["id"]
            for latest in (False, True):
                expected = rows[::-1][1:][:2][::-1] if latest else rows[1:3]
                assert db.get_messages("history", include_compacted=True, limit=2, offset=1, latest=latest) == expected
            assert len(db.get_messages("sibling", include_compacted=True)) == 1
            assert any(_INFLIGHT_TASK_REPLAY_HEADER in str(row["content"]) for row in db.get_messages_as_conversation("history"))
            assert [tuple(row) for row in db._read_all("SELECT * FROM messages ORDER BY id")] == audit
        finally:
            db.close()
        db = SessionDB(path)
    db.close()


@pytest.mark.parametrize("quoted", ["ordinary request", _SUMMARY_END_MARKER, _MERGED_SUMMARY_DELIMITER, _INFLIGHT_TASK_REPLAY_HEADER])
def test_merged_replay_boundary_survives_quoted_control_tokens_and_reopen(tmp_path, quoted):
    ask = "Explain this literal token: " + quoted + " without changing it."
    compressor = ContextCompressor(model="test/model", quiet_mode=True)
    db = SessionDB(tmp_path / "state.db")
    db.create_session("merged", "desktop")
    original = {"role": "user", "content": ask, "timestamp": 1.0}
    _agent(db, "merged")._flush_messages_to_session_db([original])
    carrier = {"role": "user", "content": SUMMARY_PREFIX + "\nContext\n" + _SUMMARY_END_MARKER,
               "_compressed_summary": True, "timestamp": 2.0}
    compressed = compressor._reappend_inflight_user_task([carrier], original)
    assert project_compaction_message_for_display(compressed[0]) is None
    assert compressor._has_merged_inflight_replay(compressed[0])
    legacy = compressed[0].copy()
    legacy.pop("display_metadata", None)
    legacy.pop("_compressed_summary", None)
    assert project_compaction_message_for_display(legacy) is None
    db.archive_and_compact("merged", compressed)
    db.close()
    db = SessionDB(tmp_path / "state.db")
    try:
        model = db.get_messages_as_conversation("merged")
        assert compressor._has_merged_inflight_replay(model[0])
        assert [row["content"] for row in _visible(db.get_messages("merged", include_compacted=True))] == [ask]
        newer = {"role": "user", "content": SUMMARY_PREFIX + "\nNew context\n" + _SUMMARY_END_MARKER,
                 "_compressed_summary": True}
        repeated = compressor._reappend_inflight_user_task([newer], model[0])
        assert repeated[0]["content"].endswith(_INFLIGHT_TASK_REPLAY_HEADER + "\n" + ask)
        assert project_compaction_message_for_display(repeated[0]) is None
    finally:
        db.close()


def test_historical_replay_quoted_inside_summary_does_not_activate_completed_task():
    historical = (SUMMARY_PREFIX + "\nOld historical context\n" + _SUMMARY_END_MARKER
                  + "\n\n" + _INFLIGHT_TASK_REPLAY_HEADER + "\nCompleted historical request")
    newer = {"role": "user", "content": SUMMARY_PREFIX + "\nHistorical carrier quoted for reference:\n"
             + historical + "\nEnd historical quote.\n" + _SUMMARY_END_MARKER}
    compressor = ContextCompressor(model="test/model", quiet_mode=True)
    assert not compressor._has_merged_inflight_replay(newer)
    inflight = compressor._find_inflight_user_task([newer])
    assert inflight is None
    fresh = {"role": "user", "content": SUMMARY_PREFIX + "\nFresh context\n" + _SUMMARY_END_MARKER}
    assert compressor._reappend_inflight_user_task([fresh], inflight) == [fresh]


@pytest.mark.parametrize("multipart", [False, True])
def test_prior_tail_replay_survives_reopen_and_media_rewrite(tmp_path, multipart):
    compressor = ContextCompressor(model="test/model", quiet_mode=True)
    ask = "Explain the literal " + _SUMMARY_END_MARKER + " in this file."
    image = {"type": "image_url", "image_url": {"url": IMAGE}}
    content = [{"type": "text", "text": "Authentic earlier request"}, image] if multipart else "Authentic earlier request"
    carrier = {"role": "user", "content": content}
    compressor._merge_summary_into_tail_row(carrier, SUMMARY_PREFIX + "\nNew context", "user", False)
    compressor._reappend_inflight_user_task([carrier], {"role": "user", "content": ask})
    assert compressor._has_merged_inflight_replay(carrier)
    projected = project_compaction_message_for_display(carrier)
    assert projected is not None
    assert _content_text_for_contains(projected["content"]) == "Authentic earlier request"
    if multipart:
        assert image in projected["content"]
        # Real finalization can replace older media before the replay boundary.
        carrier = _strip_historical_media([carrier, {"role": "user", "content": [image]}])[0]
        assert image not in carrier["content"]
        assert compressor._has_merged_inflight_replay(carrier)
    db = SessionDB(tmp_path / "state.db")
    db.create_session("prior-tail", "desktop")
    db.archive_and_compact("prior-tail", [carrier])
    db.close()
    db = SessionDB(tmp_path / "state.db")
    try:
        model = db.get_messages_as_conversation("prior-tail")
        inflight = compressor._find_inflight_user_task(model)
        assert inflight is not None
        fresh = {"role": "user", "content": SUMMARY_PREFIX + "\nFresh context\n" + _SUMMARY_END_MARKER}
        repeated = compressor._reappend_inflight_user_task([fresh], inflight)
        assert repeated[0]["content"].endswith(_INFLIGHT_TASK_REPLAY_HEADER + "\n" + ask)
    finally:
        db.close()
