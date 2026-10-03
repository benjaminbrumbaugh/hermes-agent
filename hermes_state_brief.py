"""Session brief mixin for SessionDB: the human-facing running summary of a conversation.

One JSON document per session row (``sessions.brief_json``). Reads walk the lineage tip -> root and
return the newest row that carries one, so a brief written before a compression rotation stays visible
on the child; a fresh write on the child then shadows it."""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, Optional

logger = logging.getLogger("hermes_state")


def _wire_brief(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Project a persisted v1/v2 row onto the current four-field wire contract.

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
        "blockers": _strings(parsed.get("blockers"), 6),
        "updated_at": _number(parsed.get("updated_at"), 0.0),
        "message_count": int(_number(parsed.get("message_count"), 0)),
    }


class SessionBriefMixin:
    """Persist and resolve the per-lineage session brief."""

    def set_session_brief(self, session_id: str, brief: Dict[str, Any]) -> bool:
        """Store *brief* on ``session_id``'s row. Returns False when no row matched."""
        if not session_id or not isinstance(brief, dict):
            return False
        payload = json.dumps(brief, ensure_ascii=False)

        def _do(conn):
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
                return _wire_brief(parsed)
        return None
