"""Session brief mixin for SessionDB: the human-facing running summary of a conversation.

One JSON document per session row (``sessions.brief_json``). Reads walk the lineage tip -> root and
return the newest row that carries one, so a brief written before a compression rotation stays visible
on the child; a fresh write on the child then shadows it."""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, Optional

from agent.session_brief_tasks import normalize_tasks

logger = logging.getLogger("hermes_state")


def _wire_brief(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Project a persisted row onto the current wire contract, with empty legacy tasks.

    Reads can encounter rows written before the v2 contract removed ``decisions``. Keeping the migration
    at the persistence boundary means every gateway method and event receives a strict, current shape while
    the original row remains untouched for recovery and audit purposes.
    """
    def _strings(value: Any, cap: int) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:140] for item in value
                if isinstance(item, (str, int, float)) and str(item).strip()][:cap]

    def _number(value: Any, default: float | int) -> float | int:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) else default

    return {
        "version": int(_number(parsed.get("version"), 1)),
        "goal": str(parsed.get("goal") or "").strip()[:140],
        "status": str(parsed.get("status") or "").strip()[:140],
        "completed": _strings(parsed.get("completed"), 4),
        "tasks": normalize_tasks(parsed.get("tasks")),
        "blockers": _strings(parsed.get("blockers"), 6),
        "updated_at": _number(parsed.get("updated_at"), 0.0),
        "message_count": int(_number(parsed.get("message_count"), 0)),
    }


class SessionBriefMixin:
    """Persist and resolve the per-lineage session brief."""

    def set_session_brief(self, session_id: str, brief: Dict[str, Any]) -> bool:
        """Store *brief* if its refresh order is not older than the row's current brief.

        Post-turn auxiliary updates run independently, so a slower earlier turn must not overwrite a newer
        brief. Returns False when no row matched or when the write lost that ordering race.
        """
        if not session_id or not isinstance(brief, dict):
            return False
        lineage = list(reversed(self._session_lineage_root_to_tip(session_id)))

        def _ordering_key(value: Any) -> tuple[float, int]:
            if not isinstance(value, dict):
                return (0.0, 0)
            try:
                updated_at = float(value.get("updated_at") or 0.0)
            except (TypeError, ValueError, OverflowError):
                updated_at = 0.0
            if not math.isfinite(updated_at):
                updated_at = 0.0
            try:
                message_count = max(0, int(value.get("message_count") or 0))
            except (TypeError, ValueError, OverflowError):
                message_count = 0
            return (updated_at, message_count)

        def _do(conn):
            row = conn.execute("SELECT brief_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return 0
            if row[0]:
                try:
                    current = json.loads(row[0])
                except (TypeError, ValueError):
                    current = None
                if _ordering_key(current) > _ordering_key(brief):
                    return 0
            previous_tasks = []
            for sid in lineage:
                prior_row = conn.execute("SELECT brief_json FROM sessions WHERE id = ?", (sid,)).fetchone()
                if prior_row is None or not prior_row[0]:
                    continue
                try:
                    prior = json.loads(prior_row[0])
                    if not isinstance(prior, dict):
                        continue
                    previous_tasks = normalize_tasks(prior.get("tasks"))
                except (TypeError, ValueError):
                    continue
                break
            try:
                merged = dict(brief, tasks=normalize_tasks(brief.get("tasks"), previous_tasks))
            except ValueError:
                return 0
            payload = json.dumps(merged, ensure_ascii=False)
            return conn.execute(
                "UPDATE sessions SET brief_json = ? WHERE id = ?", (payload, session_id),
            ).rowcount

        return self._execute_write(_do) > 0

    def get_session_brief(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Newest brief on the lineage that contains ``session_id`` (tip first), or None."""
        if not session_id:
            return None
        for sid in reversed(self._session_lineage_root_to_tip(session_id)):
            row = self._read_one("SELECT brief_json FROM sessions WHERE id = ?", (sid,))
            if row is None or not row[0]:
                continue
            try:
                parsed = json.loads(row[0])
            except (TypeError, ValueError):
                logger.debug("unparsable brief_json on session %s", sid)
                continue
            if isinstance(parsed, dict):
                try:
                    return _wire_brief(parsed)
                except ValueError:
                    logger.debug("invalid task hierarchy on session %s", sid)
                    continue
        return None
