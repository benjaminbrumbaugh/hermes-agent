"""Session brief: a running, human-facing summary of a conversation, refreshed off the critical path.

One small auxiliary call after a completed turn (same off-path daemon-thread pattern as
``agent.title_generator``) produces or iteratively updates a structured document — goal, current state,
completed work, blockers, key decisions — that the desktop right sidebar renders. It is a sidecar for the
person, not the model: nothing here is injected into the prompt, so per-conversation caching is untouched.

Iterative update: the previous brief plus only the turns since it was written are sent, never the whole
transcript, so cost is bounded by turn size rather than conversation length."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import weakref
from typing import Any, Callable, Dict, List, Optional

from agent.auxiliary_client import call_llm
from agent.message_content import flatten_message_text

logger = logging.getLogger(__name__)

TASK_NAME = "session_brief"
BRIEF_VERSION = 1

# Output budget: five short sections as JSON; a reasoning model's thinking must fit too.
BRIEF_MAX_TOKENS = 1200
# Per-message body cap handed to the model (head+tail elision), and the whole-delta cap.
_MESSAGE_CHARS = 1800
_DELTA_CHARS = 24000
_TOOL_ARGS_CHARS = 300

_UPGRADE_THREADS: "weakref.WeakSet[threading.Thread]" = weakref.WeakSet()

# (brief dict) -> None; the gateway pushes it to the client.
BriefCallback = Callable[[Dict[str, Any]], None]
FailureCallback = Callable[[str, BaseException], None]

_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "status": {"type": "string"},
        "completed": {"type": "array", "items": {"type": "string"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "decisions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["goal", "status", "completed", "blockers", "decisions"],
    "additionalProperties": False,
}
_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "session_brief", "strict": True, "schema": _BRIEF_SCHEMA},
}

_SYSTEM_PROMPT = """You maintain a short running brief of a conversation between a user and an AI agent, for the user to glance at when they return. Reply with ONLY a JSON object matching this shape:

{"goal": string, "status": string, "completed": [string], "blockers": [string], "decisions": [string]}

- goal: what the user is trying to accomplish overall, in their own terms, one sentence. If the objective changed, state the newest controlling request.
- status: where things stand right now, 1-3 sentences: what just happened, what is in progress, what comes next. Present tense. Say plainly if work is finished, partial, or waiting on the user.
- completed: concrete outcomes achieved so far (files changed, results found, decisions delivered), newest last, at most 8 short items. Merge, never duplicate.
- blockers: what is stopping progress or needs the user, with the exact action needed. Empty array if none.
- decisions: material choices made and why, at most 6 short items.

Be factual and specific; never invent progress. Prefer the user's nouns over internal jargon. Keep every string under 200 characters."""


def wait_for_brief_updates(timeout: float = 10.0) -> None:
    """Bounded join of in-flight brief threads; never raises."""
    deadline = time.monotonic() + timeout
    for thread in list(_UPGRADE_THREADS):
        thread.join(max(0.0, deadline - time.monotonic()))


def _brief_config() -> dict:
    from hermes_cli.config import load_config_readonly
    return ((load_config_readonly() or {}).get("auxiliary") or {}).get(TASK_NAME) or {}


def brief_enabled() -> bool:
    from utils import is_truthy_value
    return is_truthy_value(_brief_config().get("enabled"), default=True)


def _elide(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = limit - head - 5
    return f"{text[:head]} ... {text[-tail:]}"


def _render_turn_delta(messages: List[Any]) -> str:
    """Labeled, trimmed text of the turns since the last brief; tool results elided, think blocks dropped."""
    from agent.agent_runtime_helpers import strip_think_blocks
    from agent.context_compressor import _redact_compaction_text

    parts: List[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role == "system":
            continue
        content = _redact_compaction_text(flatten_message_text(msg.get("content")) or "")
        if role == "assistant" and content:
            content = strip_think_blocks(None, content)
        content = _elide(content, _MESSAGE_CHARS)
        if role == "assistant" and msg.get("tool_calls"):
            calls = []
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                args = _redact_compaction_text(str(fn.get("arguments", "")))
                calls.append(f"  {fn.get('name', '?')}({_elide(args, _TOOL_ARGS_CHARS)})")
            content += "\n[Tool calls:\n" + "\n".join(calls) + "\n]"
        if role == "tool":
            parts.append(f"[TOOL RESULT]: {content}")
        elif content:
            parts.append(f"[{role.upper()}]: {content}")
    return _elide("\n\n".join(parts), _DELTA_CHARS)


def _build_messages(previous: Optional[Dict[str, Any]], delta_text: str) -> List[Dict[str, str]]:
    if previous:
        prior = json.dumps({k: previous.get(k) for k in _BRIEF_SCHEMA["properties"]}, ensure_ascii=False)
        user = (
            f"Previous brief:\n{prior}\n\nNew conversation turns since that brief:\n{delta_text}\n\n"
            "Update the brief to reflect the new turns. Carry forward what is still true, revise what changed, "
            "drop items that are no longer relevant."
        )
    else:
        user = f"Conversation so far:\n{delta_text}\n\nWrite the brief."
    return [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user}]


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_brief(content: str) -> Optional[Dict[str, Any]]:
    raw = (content or "").strip()
    fenced = _FENCE_RE.search(raw)
    if fenced:
        raw = fenced.group(1)
    elif not raw.startswith("{"):
        start = raw.find("{")
        if start < 0:
            return None
        raw = raw[start:]
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("goal"), str):
        return None
    return parsed


def normalize_brief(parsed: Dict[str, Any], *, message_count: int) -> Dict[str, Any]:
    """Coerce a model reply into the persisted shape; every list is strings, every string trimmed."""
    def _strs(value: Any, cap: int) -> List[str]:
        if not isinstance(value, list):
            return []
        out = [str(v).strip() for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
        return out[:cap]

    return {
        "version": BRIEF_VERSION,
        "goal": str(parsed.get("goal") or "").strip(),
        "status": str(parsed.get("status") or "").strip(),
        "completed": _strs(parsed.get("completed"), 8),
        "blockers": _strs(parsed.get("blockers"), 6),
        "decisions": _strs(parsed.get("decisions"), 6),
        "updated_at": time.time(),
        "message_count": int(message_count),
    }


def _response_text(response: Any) -> str:
    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError):
        return ""


def generate_brief(
    previous: Optional[Dict[str, Any]], delta_messages: List[Any], *, message_count: int,
    main_runtime: Optional[dict] = None, timeout: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """One auxiliary call; None when the delta is empty or the reply is not a brief."""
    delta_text = _render_turn_delta(delta_messages)
    if not delta_text.strip():
        return None
    response = call_llm(
        task=TASK_NAME,
        messages=_build_messages(previous, delta_text),
        max_tokens=BRIEF_MAX_TOKENS, temperature=None, timeout=timeout, main_runtime=main_runtime,
        extra_body={"response_format": _RESPONSE_FORMAT},
    )
    parsed = _parse_brief(_response_text(response))
    if parsed is None:
        logger.debug("Session brief reply was not a brief; keeping the previous one")
        return None
    return normalize_brief(parsed, message_count=message_count)


def update_session_brief(
    session_db: Any, session_id: str, delta_messages: List[Any], *, message_count: int,
    main_runtime: Optional[dict] = None, brief_callback: Optional[BriefCallback] = None,
    failure_callback: Optional[FailureCallback] = None,
) -> None:
    """Thread body: read the previous brief, call the model, persist, notify. Never raises."""
    try:
        previous = session_db.get_session_brief(session_id)
        timeout = _brief_config().get("timeout")
        brief = generate_brief(
            previous, delta_messages, message_count=message_count, main_runtime=main_runtime,
            timeout=float(timeout) if timeout else None,
        )
        if brief is None:
            return
        if not session_db.set_session_brief(session_id, brief):
            logger.debug("Session brief write matched no row for %s", session_id)
            return
        if brief_callback is not None:
            brief_callback(brief)
    except Exception as exc:
        logger.debug("Session brief update failed for %s", session_id, exc_info=True)
        if failure_callback is not None:
            try:
                failure_callback(TASK_NAME, exc)
            except Exception:
                pass


def _turns_since(messages: List[Any], previous: Optional[Dict[str, Any]]) -> List[Any]:
    """Messages appended after the previous brief's ``message_count``; whole transcript on the first brief.

    A count past the current length (compression shrank the list) falls back to the whole transcript so the
    next brief rebuilds from what survived."""
    if not previous:
        return list(messages)
    seen = int(previous.get("message_count") or 0)
    if seen <= 0 or seen > len(messages):
        return list(messages)
    return list(messages[seen:])


def maybe_update_brief(agent: Any, messages: List[Any]) -> Optional[threading.Thread]:
    """Start the post-turn brief refresh for the main agent; None when skipped.

    Skipped for subagents, non-persisted runs, cron sessions and when the config disables it."""
    session_db = getattr(agent, "_session_db", None)
    session_id = getattr(agent, "session_id", None)
    if not session_db or not session_id or not getattr(agent, "_session_db_created", False):
        return None
    if getattr(agent, "_persist_disabled", False) or int(getattr(agent, "_delegate_depth", 0) or 0) > 0:
        return None
    if str(getattr(agent, "platform", "") or "").lower() in {"cron", "subagent"}:
        return None
    if not brief_enabled():
        return None
    try:
        previous = session_db.get_session_brief(session_id)
    except Exception:
        logger.debug("Session brief read failed; rebuilding from the full transcript", exc_info=True)
        previous = None
    delta = _turns_since(messages, previous)
    if not any(isinstance(m, dict) and m.get("role") == "user" for m in delta):
        return None
    main_runtime = {
        k: getattr(agent, k, None)
        for k in ("model", "provider", "base_url", "api_key", "api_mode", "session_id")
    }
    from agent.memory_provider import spawn_context_thread
    thread = spawn_context_thread(
        update_session_brief, name="session-brief",
        args=(session_db, session_id, [dict(m) if isinstance(m, dict) else m for m in delta]),
        kwargs=dict(
            message_count=len(messages), main_runtime=main_runtime,
            brief_callback=getattr(agent, "_on_session_brief", None),
            failure_callback=getattr(agent, "_emit_auxiliary_failure", None),
        ),
    )
    _UPGRADE_THREADS.add(thread)
    thread.start()
    return thread
