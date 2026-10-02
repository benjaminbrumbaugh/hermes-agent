# Pulse candidate

Branch: `brief-design/pulse`  
Primary hierarchy: vertical state pulse → goal → blocker/task/outcome sections.

The pulse uses one quiet vertical guide and an anchored status marker to give the brief a directional “what is happening now?” reading. The marker changes only from the existing blocker presence, while the actual status text remains authoritative and visible. Supporting sections share one flat rhythm and hairline treatment.

Intended rubric coverage: `state.buried`, `running.unclear`, `waiting.missing`, `order.wrong`, and `density.empty_section_noise`. The trade-off is decorative geometry consuming a small amount of horizontal space, especially in RTL or at 280 px. It adds no i18n strings, so Arabic follows the established English fallback rather than introducing a partial translation.

Evidence boundary: the pulse line is a visual hypothesis, not semantic state proof; only the rendered dark/light screenshots can show whether it helps or distracts.
