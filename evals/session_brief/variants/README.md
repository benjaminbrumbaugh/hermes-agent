# Variants

**Archived legacy experiments:** These prompts and schema descriptors predate v3. They are not
current-contract acceptance fixtures. Rebase schema deltas and task normalization before comparing
them with the current baseline; alternatively run against an explicitly frozen legacy contract.
Current model shape is `goal/status/tasks/blockers`; current wire also retains legacy `completed`.

One file per competing system prompt: `<name>.md` is the whole prompt. `baseline` is virtual (the shipped prompt).

Variants that change the response shape also carry `<name>.schema.json` with:

- `schema`: the complete strict JSON Schema sent to the model;
- `schema_delta.added`: field names and their exact schemas added to the production shape;
- `schema_delta.removed`: production field names removed from the variant;
- `normalization`: optional canonical-field mappings used only by the eval runner.

The runner stores native fields for review, then projects every variant into the renderer-facing
legacy `goal/status/completed/blockers/decisions` view before grading. V3 grading must instead retain
`tasks` and previous task identity/parent context. These sidecars are eval inputs, not
production API contracts.
