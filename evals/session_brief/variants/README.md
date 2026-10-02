# Variants

One file per competing system prompt: `<name>.md` is the whole prompt. `baseline` is virtual (the shipped prompt).

Variants that change the response shape also carry `<name>.schema.json` with:

- `schema`: the complete strict JSON Schema sent to the model;
- `schema_delta.added`: field names and their exact schemas added to the production shape;
- `schema_delta.removed`: production field names removed from the variant;
- `normalization`: optional canonical-field mappings used only by the eval runner.

The runner stores native fields for review, then projects every variant into the renderer-facing
`goal/status/completed/blockers/decisions` view before grading. These sidecars are eval inputs, not
production API contracts.
