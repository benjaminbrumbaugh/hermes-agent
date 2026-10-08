"""Display admission for durable model continuation and witnessed legacy replays."""

from agent.context_compressor import MODEL_ONLY_DISPLAY_METADATA_KEY, _INFLIGHT_TASK_REPLAY_HEADER
from hermes_state_common import _sql_json_extract, _sql_literal


def legacy_replay_content(content):
    """Recognize the exact generated prefix, never a substring quoted by a user."""
    if isinstance(content, list) and content and isinstance(content[0], dict):
        content = content[0].get("text") if content[0].get("type") == "text" else None
    return isinstance(content, str) and content.startswith(_INFLIGHT_TASK_REPLAY_HEADER + "\n")


def _legacy_replay_sql(alias):
    content = f"{alias}.content"
    # Multimodal content has a NUL-prefixed JSON sentinel. Slice bytes: SQLite
    # text substr stops at NUL and would lose the entire stored payload.
    parts = (f"CASE WHEN SUBSTR(CAST({content} AS BLOB), 1, 6) = X'006a736f6e3a' "
             f"THEN CAST(SUBSTR(CAST({content} AS BLOB), 7) AS TEXT) ELSE '{{}}' END")
    first_text = _sql_json_extract(parts, "$[0].text")
    first_type = _sql_json_extract(parts, "$[0].type")
    prefix = _sql_literal(_INFLIGHT_TASK_REPLAY_HEADER + "\n")
    return (f"COALESCE(({alias}.role = 'user' AND (INSTR({content}, {prefix}) = 1 OR "
            f"({first_type} = 'text' AND INSTR({first_text}, {prefix}) = 1))), 0)")


def display_visible_sql(alias="messages", *, has_uid=True):
    """Filter before grouping/paging; legacy replay requires an earlier source witness.

    Content alone never authorizes hiding a row. UID, accepted timestamp and
    session scope must all match an earlier visible non-replay user occurrence.
    This also works with already-materialized display indexes, without writes.
    """
    metadata = _sql_json_extract(f"{alias}.display_metadata", "$." + MODEL_ONLY_DISPLAY_METADATA_KEY)
    visible = f" AND COALESCE({metadata}, 0) = 0"
    if not has_uid:
        return visible
    return visible + f""" AND NOT (
        {_legacy_replay_sql(alias)} AND {alias}.message_uid IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM messages AS replay_source
            WHERE replay_source.session_id = {alias}.session_id
              AND replay_source.message_uid = {alias}.message_uid
              AND replay_source.timestamp = {alias}.timestamp
              AND replay_source.id < {alias}.id
              AND (replay_source.active = 1 OR replay_source.compacted = 1)
              AND replay_source.role = 'user'
              AND COALESCE({_sql_json_extract('replay_source.display_metadata', '$.' + MODEL_ONLY_DISPLAY_METADATA_KEY)}, 0) = 0
              AND NOT {_legacy_replay_sql('replay_source')}
        ))"""


def witnessed_legacy_replay(db, row, sources):
    """Streaming twin of display_visible_sql for resume and read-only legacy paging."""
    uid = row["message_uid"] if "message_uid" in row.keys() else None
    if row["role"] != "user" or not uid:
        return False
    session = row["session_id"] if "session_id" in row.keys() else None
    identity = (session, uid, row["timestamp"])
    if legacy_replay_content(db._decode_content(row["content"])):
        return identity in sources
    sources.add(identity)
    return False
