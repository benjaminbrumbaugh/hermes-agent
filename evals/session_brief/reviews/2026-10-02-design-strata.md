# Strata candidate

Branch: `brief-design/strata`  
Primary hierarchy: concise status lead → inline goal sentence → blocker rail → active work/history.

Strata removes a repeated “status” heading/value pair and lets the status lead carry the first line. The goal follows as a labeled sentence, then user blockers receive a tokenized left rail so an exact action is visually distinguishable from ordinary history. The remaining sections are kept flat and sparse.

Intended rubric coverage: `state.buried`, `waiting.vague`, `waiting.false`, `order.wrong`, and `density.padding`. The trade-off is that the status label is not repeated beside the value, so extremely terse or ambiguous model status text may be harder to classify than in a badge treatment. It preserves all existing i18n keys and relies on normal locale fallback.

Evidence boundary: the layout can make a blocker prominent but cannot correct inaccurate backend text; screenshots evaluate hierarchy only, not content truth.
