## Summary

Evaluate whether aggregations should be allowed at arbitrary positions in the DAG (e.g., source -> transform_a -> aggregation -> transform_b -> sink) rather than constrained to post-transform position.

## Severity

- Severity: minimal
- Priority: P4
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-ipwc

## Considerations

- Aggregations are state barriers (collect N rows, flush as 1 or N)
- Mid-chain placement creates fork-like semantics (buffered vs unbuffered tokens)
- Would require: selective buffering, bypass logic, schema branching at coalesce
- Existing gate/fork/coalesce infrastructure may already cover the use cases
- No current user request or example YAML exercises this pattern

## When to Revisit

- When a real use case emerges that cannot be solved with the current post-transform constraint
- After Phase 3 is stable and declarative wiring is proven in production

## Blocked By

- `w2q7` — ELSPETH-NEXT (deferred to post-RC3)

## Affected Subsystems

- `engine/orchestrator/`
- `engine/processor.py`
- `core/dag/`
