# Lane B content-contract variants — full-corpus review

Run: `ha-bj0`
Corpus: 41 fixtures in `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-corpus`
Variants: baseline + 9 candidates
Snapshots: up to 6 sampled completed-turn boundaries per fixture
Model: `stealth/space-bunny-alpha`
Descriptor fingerprint: `97965633e79600f5`

## Result

The full run generated 410 fixture×variant jobs with zero runner errors, then graded 2,630 snapshot
rows with zero grading errors. The report contains 10 variants. No variant ships under the frozen rubric:
no mean score reaches 4.0, no candidate clears the critical-failure threshold, and no candidate clears
every bucket threshold.

The scorecard below is copied from the `report.py --json` output. `critical_rate` is the report's sum of
`state.wrong`, `waiting.missing`, and `fact.invented`; `verbose_rate` is `density.verbose`.

| variant | snapshots | generation errors | mean_glance | state agreement | critical rate | verbose rate | ships |
|---|---:|---:|---:|---:|---:|---:|:---:|
| baseline | 261 | 1 | 2.30 | 0.670 | 0.916 | 0.517 | false |
| blocker_dominant | 261 | 1 | 2.56 | 0.690 | 0.797 | 0.126 | false |
| decision_pruned | 262 | 0 | 2.43 | 0.649 | 0.844 | 0.198 | false |
| delta_first | 260 | 2 | 2.36 | 0.704 | 0.835 | 0.081 | false |
| enum_state | 260 | 2 | 2.43 | 0.712 | 0.796 | 0.142 | false |
| evidence_first | 260 | 1 | 2.48 | 0.704 | 0.808 | 0.004 | false |
| instruction_only | 260 | 1 | 2.32 | 0.688 | 0.869 | 0.227 | false |
| minimalist | 260 | 1 | 2.58 | 0.688 | 0.765 | 0.027 | false |
| state_first | 257 | 3 | 2.57 | 0.716 | 0.774 | 0.082 | false |
| user_voice | 257 | 4 | 2.37 | 0.681 | 0.809 | 0.121 | false |

The complete machine scorecard is the uncommitted evidence artifact at
`temp/session-brief-eval/ha-bj0/scorecard.json`; `report.py --worst 20` was run against the same output.
The missing Lane A scorecard referenced by the bead was not present in the shared temp tree, so this lane
regenerated and compared its own baseline rather than asserting a value it could not inspect.

## Per-variant theses and findings

| variant | thesis | unique win | unique loss |
|---|---|---|---|
| `baseline` | Preserve the production five-field prompt and behavior. | Control: establishes the current contract and its 2.30 mean. | Highest critical rate (0.916) and verbose rate (0.517); it is not a viable content contract. |
| `state_first` | Make the first status token the explicit state answer. | Best state agreement (0.716); mean 2.57. | Still invents/stales goals and facts; 3 generation errors and critical rate 0.774. |
| `delta_first` | Lead with what materially changed since the prior brief. | Keeps verbosity at 0.081 and state agreement at 0.704. | Mean 2.36; freshness emphasis did not prevent wrong/stale goals. |
| `blocker_dominant` | Put an exact user action above all other content when blocked. | Strong blocker rates (`waiting.missing` 0.031, `waiting.vague` 0.015). | False blockers and state errors remain; critical rate 0.797 and verbosity 0.126. |
| `minimalist` | Remove low-signal decisions and keep a compact four-field contract. | Best mean (2.58), low verbosity (0.027), and lowest critical rate (0.765). | Empty-section noise is high (0.292) in the normalized evaluator view; pivots and running reviews still become waiting/done. |
| `enum_state` | Add explicit `state` and `waiting_on` fields. | Strong state agreement (0.712) and a machine-readable waiting action. | Schema did not solve transcript selection; mean 2.43, verbosity 0.142, critical rate 0.796. |
| `decision_pruned` | Reserve decisions for actual choices with reasons. | Zero generation errors and fewer decision false positives than baseline. | Mean 2.43; state agreement 0.649 and empty-section noise 0.202. |
| `user_voice` | Prefer plain user nouns over agent jargon. | Lower goal-jargon rate (0.066) than baseline. | Decision false positives are highest (0.416); 4 generation errors and mean 2.37. |
| `instruction_only` | Keep the shipped schema and improve instructions only. | Lowest integration risk and no schema delta. | Behaves close to baseline: mean 2.32, critical rate 0.869, verbosity 0.227. |
| `evidence_first` | Use conservative evidence rules and empty rather than guessed fields. | Best verbosity rate (0.004), with state agreement 0.704. | It still follows unrelated earlier work in long/pivot transcripts; mean 2.48 and critical rate 0.808. |

## Recommendation

Recommend `minimalist` as the single starting content contract for Lane E, subject to a new integrated
evaluation after the renderer and prompt are updated. It is the strongest measured candidate by mean
glance score (2.58), has the lowest critical-error rate (0.765), and reduces verbose output from the
baseline's 0.517 to 0.027. Its schema removes `decisions`; the eval adapter projects a missing decisions
field to an empty canonical list for comparison, so Lane E must decide whether the renderer omits that
section rather than displaying an empty placeholder.

This is a recommendation, not a ship decision: the candidate fails every frozen ship gate. The evidence
shows that reducing density alone does not solve stale goals or confusion between a running background
review and a user blocker. Before integration, Lane E should preserve the explicit state-first and
evidence-first rules as hypotheses to test against the integrated contract, without claiming that this
lane's results prove they work in production.

## Worst-row inspection and evidence boundary

`report.py --worst 20` identifies repeated failure clusters rather than isolated typos. Two representative
rows were inspected against their fixture transcripts:

- `20260814_110332_5e05e2`, message count 4/9: the transcript explicitly says an independent security
  review is running, while `minimalist` says `WAITING ON YOU` for the review verdict. The grader's
  `state.wrong`, `waiting.false`, and `running.unclear` findings are supported by the transcript.
- The same fixture, message count 123: the latest direct user request is “Find what is using OpenRouter,”
  but `evidence_first` reports an unrelated dashboard mail-cleanup task as running. The grader's
  `goal.stale`, `state.wrong`, `fact.invented`, and `fresh.stale_status` findings are supported by the
  visible user/assistant sequence. Runtime wrappers and tool results occur between the actual user turns.

The full-corpus run proves comparative behavior of these prompts under one remote model, corpus, snapshot
schedule, and grader. It does not prove pixel layout, human two-second glance performance, behavior on
unseen conversations, or that the grader catches every semantic error. The renderer and human glance lanes
remain required. The one unparseable response in most variants is retained as a generation error in the
scorecard rather than silently converted into a passing row.

## Schema and runner changes

- `delta_first.schema.json` adds `changed`.
- `minimalist.schema.json` removes `decisions`.
- `enum_state.schema.json` adds the constrained `state` enum and `waiting_on`.
- The runner loads prompt/schema descriptors, validates exact deltas, fingerprints descriptors, preserves
  native variant fields in generated records, and projects to the stable five-field grading view.
- Baseline remains byte/source-bound to `agent.session_brief._SYSTEM_PROMPT`,
  `agent.session_brief._RESPONSE_FORMAT`, and `agent.session_brief.normalize_brief`.

No production prompt, persistence schema, desktop contract, or renderer was changed in Lane B.
