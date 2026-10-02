# Compass candidate

Branch: `brief-design/compass`  
Primary hierarchy: labeled state → status value → explicitly labeled goal → non-empty supporting sections.

Compass is the most literal information instrument of the set. It gives the status a readable lead, then treats the goal as its own named destination instead of relying on proximity. Every later section is omitted when empty, so the pane does not spend first-glance space on absent data.

Intended rubric coverage: `state.buried`, `goal.redundant`, `goal.jargon`, `order.wrong`, and `density.empty_section_noise`. The trade-off is a more spacious header that may reduce how much history is visible before scrolling. It keeps the current i18n surface unchanged; Arabic uses the existing English fallback.

Evidence boundary: the explicit labels improve discoverability only if their copy remains short; screenshot review at all three widths is required to catch wrapping that static checks cannot see.
