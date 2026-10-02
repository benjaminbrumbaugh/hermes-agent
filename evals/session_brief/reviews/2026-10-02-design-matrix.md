# Matrix candidate

Branch: `brief-design/matrix`  
Primary hierarchy: compact status cell + goal cell → blockers → tasks/outcomes/decisions.

The matrix puts state and topic beside each other in a two-cell, flat information grid. This tests whether a returning user can answer “where is it?” and “what is it about?” without spending vertical space before the supporting lists. Section icons make the lower rows scannable while empty sections remain omitted.

Intended rubric coverage: `state.buried`, `goal.redundant`, `order.wrong`, `density.padding`, and `running.unclear`. The trade-off is narrow-width wrapping: two columns can make either value taller at 280 px, so the render set must decide whether the compact top edge survives that constraint. No contract or locale keys change; Arabic uses the existing fallback.

Evidence boundary: passing static checks confirms the grid is valid React/CSS; the screenshots are required to judge wrapping and first-glance state legibility.
