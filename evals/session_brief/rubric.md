# Session brief rubric

The brief is a glanceable status instrument, not a summary. A returning user — switching between
conversations rapid-fire — must answer four questions in about two seconds **without reading**:

1. **Is it done?**
2. **Is it waiting on me?** If so, on *what exactly*?
3. **Is it still running?**
4. **What was this about?**

Everything else is secondary. A brief that reads well but makes the user misjudge any of the four is a
failure. Graders cite the brief text and the transcript for every failure they record.

## Failure modes

### State fidelity (the four answers)

- `state.wrong` — the state a user would infer from the brief (done / waiting on me / running / abandoned) differs from what the transcript shows.
- `state.buried` — the state is correct but not inferable from the first two lines (goal + status opening); the user must read further to learn it.
- `state.hedged` — the status hedges ("may be", "appears", "should now") where the transcript is definite.
- `waiting.missing` — the transcript ends with the agent asking the user for something (a decision, a click, a confirmation) and the brief does not surface it as a blocker.
- `waiting.vague` — a blocker is listed but does not name the exact action ("needs your input" vs "choose A or B").
- `waiting.stale` — a blocker is listed that the user already resolved later in the transcript.
- `waiting.false` — a blocker is listed that the transcript never shows the agent asking for.
- `running.unclear` — work is in flight (background job, pending result, agent mid-task) and the brief does not say what is running or what will happen when it finishes.

### Goal fidelity

- `goal.stale` — the user pivoted to a materially different request and the goal still states the old one.
- `goal.inflated` — the goal states a scope wider than the user asked for (the agent's framing, not the user's).
- `goal.jargon` — the goal uses the agent's internal nouns (file names, function names, tool names) where the user used plain terms.
- `goal.redundant` — the goal is a restatement of the conversation title and adds nothing.

### Truthfulness

- `fact.invented` — the brief states progress, a result, or a decision the transcript does not contain.
- `fact.overclaimed` — something attempted or partially done is listed as completed.
- `fact.unverified_as_verified` — the agent's unverified claim is presented as an established outcome.
- `decision.not_a_decision` — an item under decisions is a plan, an observation, or a task — not a choice between alternatives.
- `decision.no_why` — a decision is listed without the reason, when the transcript gives one.

### Density and scan-ability

- `density.verbose` — any string over ~120 characters, or a status over two sentences, where a shorter form carries the same answer.
- `density.padding` — items that restate each other, or completed items that are sub-steps of another listed item.
- `density.low_signal_completed` — completed items a returning user would not care about (ran tests, read a file, searched) crowding out outcomes.
- `density.empty_section_noise` — a section rendered with filler ("none yet", "n/a") rather than omitted.
- `order.wrong` — the most decision-relevant information (blocker, failure, final result) is below less relevant information.

### Freshness

- `fresh.stale_status` — the status describes an earlier turn, not the latest completed turn.
- `fresh.no_delta` — a returning user cannot tell what changed since they last looked (when the transcript shows material change).

### Voice

- `voice.agent_pov` — written from the agent's point of view ("I fixed", "the assistant") rather than as a status instrument.
- `voice.user_addressed` — second person instructions in sections other than blockers.
- `voice.inconsistent_tense` — mixed past/present within status.

## Scoring

`glance_score` 0–5 per snapshot:

- **5** — all four answers correct and obvious in the first two lines; nothing false; nothing padded.
- **4** — all four answers correct; a density or voice nit.
- **3** — four answers correct but at least one requires reading beyond the first two lines.
- **2** — one of the four answers wrong or missing, the rest fine.
- **1** — two or more wrong, or an invented fact.
- **0** — actively misleading about done / waiting / running.

Aggregate thresholds a variant must clear to ship (asserted by `report.py`, never typed):

- mean `glance_score` ≥ 4.0 on every bucket; no bucket < 3.5
- `state.wrong` + `waiting.missing` + `fact.invented` rate ≤ 3 % of snapshots
- `density.verbose` rate ≤ 10 % of snapshots
