# Ledger candidate

Branch: `brief-design/ledger`  
Primary hierarchy: status/goal header → numbered blockers/tasks/outcomes/decisions.

Ledger gives repeated list items a stable visual index and pairs each index with the existing semantic icon. The result is a compact record-like scan path: state first, then actionable blockers, then work and outcomes. Completed items use a quieter text token so fresh user-relevant information wins attention.

Intended rubric coverage: `density.padding`, `density.low_signal_completed`, `order.wrong`, `fresh.no_delta`, and `decision.not_a_decision`. The trade-off is that numbering can imply chronology or priority even though the backend arrays do not promise either; this is intentionally a candidate to reject if screenshots make that interpretation harmful. No schema or locale changes are made.

Evidence boundary: static checks prove the list rendering is safe; the render receipts must determine whether numbering clarifies or adds noise.
