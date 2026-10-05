"""Task identity and longitudinal merging for the human-facing brief sidecar."""
from typing import Any

TASK_STATES = ("pending", "in_progress", "waiting", "paused", "timed_wait", "completed", "cancelled")
_TASK_KEYS = ("id", "parent_id", "goal", "status", "detail")


def normalize_tasks(value: Any, previous: Any = None) -> list[dict]:
    """Merge explicit updates by ID; reject an invalid graph without losing prior work.

    IDs and parent links are identity, not display strings: never trim them or silently
    reparent an existing task. No history cap can discard an unresolved ancestor.
    """
    tasks: dict[str, dict] = {}
    for batch in (previous, value):
        if batch is None:
            continue
        if not isinstance(batch, list):
            raise ValueError("tasks must be a list")
        seen = set()
        for item in batch:
            if not isinstance(item, dict) or any(key not in item for key in _TASK_KEYS):
                raise ValueError("incomplete task")
            identity = item["id"]
            parent = item["parent_id"]
            if not isinstance(identity, str) or not identity.strip() or identity != identity.strip() or len(identity) > 128:
                raise ValueError("invalid task ID")
            if parent is not None and (not isinstance(parent, str) or not parent.strip() or parent != parent.strip() or len(parent) > 128):
                raise ValueError("invalid parent ID")
            if identity in seen or item["status"] not in TASK_STATES:
                raise ValueError("duplicate task ID or invalid state")
            if any(not isinstance(item[key], str) for key in ("goal", "status", "detail")) or not item["goal"].strip():
                raise ValueError("invalid task text")
            if identity in tasks and tasks[identity]["parent_id"] != parent:
                raise ValueError("task parent identity changed")
            seen.add(identity)
            tasks[identity] = {key: item[key] for key in _TASK_KEYS}
            tasks[identity]["goal"] = item["goal"].strip()[:140]
            tasks[identity]["detail"] = item["detail"].strip()[:240]
    # Iterative traversal handles deep graphs without recursion or recursion limits.
    checked = set()
    for identity in tasks:
        path = set()
        current = identity
        while current is not None and current not in checked:
            if current not in tasks or current in path:
                raise ValueError("missing parent or cyclic task hierarchy")
            path.add(current)
            current = tasks[current]["parent_id"]
        checked.update(path)
    return list(tasks.values())
