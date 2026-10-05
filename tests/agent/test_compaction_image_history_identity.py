"""Compaction copies preserve occurrence identity across text/media projections."""

from unittest.mock import patch

from agent.codex_responses_adapter import _chat_messages_to_responses_input
from agent.context_compressor import ContextCompressor, _INFLIGHT_TASK_REPLAY_HEADER, _SUMMARY_END_MARKER
from agent.conversation_compression import compress_context
from hermes_state import SessionDB
from run_agent import AIAgent

OLD = "Explain this old chart; do not edit anything."
CURRENT = "Fix only the new storage bug."
IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="


def _agent(db, sid):
    agent = AIAgent(api_key="test-key", base_url="https://example.invalid/v1", model="test/model",
                    quiet_mode=True, session_db=db, session_id=sid,
                    skip_context_files=True, skip_memory=True, enabled_toolsets=[])
    agent.compression_in_place = True
    compressor = ContextCompressor(model="test/model", protect_first_n=1, protect_last_n=3, quiet_mode=True)
    compressor.tail_token_budget = 250
    agent.context_compressor = compressor
    return agent


def _groups(start):
    for index in range(start, start + 10):
        cid = f"call_{index}"
        yield {"role": "assistant", "content": "", "tool_calls": [{"id": cid, "type": "function",
               "function": {"name": "inspect", "arguments": '{"fixture":"' + 'x' * 440 + '"}'}}]}
        yield {"role": "tool", "tool_call_id": cid, "content": "result:" + "r" * 110}


def _wire_assertions(messages, *, keeps_opening_image):
    wire = _chat_messages_to_responses_input(messages, current_issuer_kind="codex_backend")
    image_rows = [m for m in wire if any(p.get("type") == "input_image" for p in m.get("content", []) if isinstance(p, dict))]
    # Head protection deliberately decays after the first compaction; this fix
    # must preserve initial grounding, not fossilize the opening image forever.
    assert len(image_rows) == int(keeps_opening_image)
    text = lambda m: "".join(p.get("text", "") for p in m.get("content", []) if isinstance(p, dict))
    boundary = next(i for i, m in enumerate(wire) if _SUMMARY_END_MARKER in text(m))
    if keeps_opening_image:
        assert image_rows[0]["role"] == "user"
        assert text(image_rows[0]) == OLD
        image_part = next(p for p in image_rows[0]["content"] if p.get("type") == "input_image")
        assert image_part["image_url"] == IMAGE
        assert wire.index(image_rows[0]) < boundary  # history, not renewed authorization
    live = [text(m).rsplit(_SUMMARY_END_MARKER, 1)[-1] for m in wire[boundary:] if m.get("role") == "user"]
    assert sum(CURRENT in t for t in live) == 1
    assert all(OLD not in t for t in live)
    assert sum(_INFLIGHT_TASK_REPLAY_HEADER in t for t in live) == 1
    calls = {m["call_id"] for m in wire if m.get("type") == "function_call"}
    results = {m["call_id"] for m in wire if m.get("type") == "function_call_output"}
    assert calls == results and calls
    assert not any("message_uid" in m or "display_metadata" in m for m in wire)


def test_image_request_keeps_original_display_position_through_compaction_resume(tmp_path):
    path = tmp_path / "state.db"
    db = SessionDB(path)
    sid = "image-history"
    db.create_session(sid, "desktop")
    db.create_session("sibling", "desktop")
    db.append_message("sibling", "user", OLD, timestamp=1.0)
    sibling = db.get_messages("sibling", include_inactive=True)
    agent = _agent(db, sid)
    messages = [{"role": "user", "content": [{"type": "text", "text": OLD},
                {"type": "image_url", "image_url": {"url": IMAGE}}], "timestamp": 1.0},
                {"role": "assistant", "content": "Chart explained.", "timestamp": 2.0}]
    for i in range(3):
        messages.extend([{"role": "user", "content": f"Later request {i}", "timestamp": 3.0 + i * 2},
                         {"role": "assistant", "content": "Completed:" + "a" * 2000, "timestamp": 4.0 + i * 2}])
    messages.append({"role": "user", "content": CURRENT, "timestamp": 20.0})
    messages.extend(_groups(0))
    try:
        agent._flush_messages_to_session_db(messages)
        original = db.get_messages(sid)[0]
        current = next(m for m in db.get_messages(sid) if m["content"] == CURRENT)
        assert original["content"] == OLD + "\n[screenshot]"
        assert original["message_uid"] == messages[0]["message_uid"]
        for cycle in range(3):
            if cycle:
                messages.extend(_groups(cycle * 10))
                agent._flush_messages_to_session_db(messages)
            # Stub only the summarizer transport, not assembly, leases, persistence or projection.
            with patch.object(agent.context_compressor, "_call_summary_llm", return_value="## Completed Actions\nEarlier requests completed.\n## Active State\nInspecting storage."):
                compressed, _ = compress_context(agent, messages, approx_tokens=90_000, system_message="fixture", force=True)
            assert agent._last_compaction_in_place
            assert len(compressed) < len(messages)
            _wire_assertions(compressed, keeps_opening_image=cycle == 0)
            agent._flush_messages_to_session_db(compressed)
            db.close()
            db = SessionDB(path)
            messages = db.get_messages_as_conversation(sid, include_row_ids=True)
            _wire_assertions(messages, keeps_opening_image=cycle == 0)
            display = db.get_messages(sid, include_compacted=True)
            model_resume, desktop_resume = db.get_resume_conversations(sid)
            _wire_assertions(model_resume, keeps_opening_image=cycle == 0)
            assert sum(m.get("message_uid") == original["message_uid"] for m in desktop_resume) == 1
            assert desktop_resume[0]["message_uid"] == original["message_uid"]
            old_rows = [m for m in display if m["message_uid"] == original["message_uid"]]
            assert len(old_rows) == 1, "text projection and image copy are one accepted turn"
            assert display[0]["message_uid"] == original["message_uid"], "old image must not become a fresh turn"
            assert sum(m["message_uid"] == current["message_uid"] for m in display) == 1
            assert any(m["message_uid"] == current["message_uid"] and m["content"].endswith(CURRENT) for m in display)
            orders = db._read_all("SELECT display_order FROM messages WHERE session_id = ? AND message_uid = ? AND (active=1 OR compacted=1)",
                                  (sid, original["message_uid"]))
            assert {r[0] for r in orders} == {original["id"]}
            assert db.get_messages("sibling", include_inactive=True) == sibling
            agent = _agent(db, sid)
    finally:
        db.close()


def test_legacy_read_only_paging_folds_shared_uid_but_not_a_later_accepted_turn(tmp_path):
    path = tmp_path / "state.db"
    db = SessionDB(path)
    db.create_session("history", "desktop")
    agent = _agent(db, "history")
    original = {"role": "user", "content": [{"type": "text", "text": OLD},
                {"type": "image_url", "image_url": {"url": IMAGE}}], "timestamp": 1.0}
    later = {"role": "user", "content": OLD + "\n[screenshot]", "timestamp": 3.0}
    agent._flush_messages_to_session_db([original, {"role": "assistant", "content": "done", "timestamp": 2.0}, later])
    assert original["message_uid"] != later["message_uid"]
    # A compaction generation retains multipart grounding and the later ask.
    db.archive_and_compact("history", [dict(original), {"role": "assistant", "content": "context", "timestamp": 2.0}, dict(later)])
    # Legacy read-only stores cannot backfill the display index. Exercise the
    # bounded scan, not the normal indexed page, without changing transcripts.
    db._execute_write(lambda conn: conn.execute("UPDATE messages SET display_order = NULL, display_identity = NULL"))
    db.close()
    db = SessionDB(path, read_only=True)
    try:
        rows = db.get_messages("history", include_compacted=True)
        users = [m for m in rows if m["role"] == "user"]
        assert [m["message_uid"] for m in users] == [original["message_uid"], later["message_uid"]]
        for latest in (False, True):
            paged = db.get_messages("history", include_compacted=True, limit=2, offset=1, latest=latest)
            expected = rows[::-1][1:][:2][::-1] if latest else rows[1:3]
            assert paged == expected
    finally:
        db.close()
