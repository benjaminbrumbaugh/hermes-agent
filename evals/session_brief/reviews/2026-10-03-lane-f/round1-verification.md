# Lane F Round 1 — integrator verification

| Candidate finding | Verification | Disposition |
| --- | --- | --- |
| Completed outcomes disappear on a later delta | Reproduced by tracing `generate_brief()` at `agent/session_brief.py:319-339`: the only post-parse filter receives `delta_text`, while the previous brief is used only to build the prompt. The system prompt also says not to carry a previous item merely because it appeared there. | **Accepted — high** |
| Older auxiliary result can overwrite a newer result | Reproduced from `maybe_update_brief()` at `:399-421`: each turn captures a prior snapshot and starts an independent thread. `update_session_brief()` writes unconditionally at `:357`; `set_session_brief()` updates by id only at `hermes_state_brief.py:57-60`. | **Accepted — high** |
| v1 `decisions` leaks through current wire | `_wire_brief()` constructs a new four-field projection at `hermes_state_brief.py:37-45`; the gateway returns `get_session_brief()` and the generated contract has no `decisions`. | **Rejected — migration is safe** |
| Brief mutates the main model prompt/cache | The brief uses auxiliary `call_llm()` with its own static system prompt and never writes into the agent conversation or prompt builder. | **Rejected — cache boundary holds** |
| Compression count slices the wrong messages | The finalizer calls `maybe_update_brief()` before turn-end compaction (`agent/turn_finalizer.py:641-655`), and `_turns_since()` falls back to the full current list when the stored count exceeds its length. The concern was not reproducible from the inspected path. | **Rejected as unconfirmed; evidence gap recorded** |

The two accepted findings identify real product behavior defects, not change-detector failures. The eventual tests must prove the persistence/update contract at the layer they observe; they do not prove visual glanceability or the human ship gate.
