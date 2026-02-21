## Summary

`TokenManager.coalesce_tokens()` does not validate parent token invariants (non-empty list, same `row_id`), allowing a merged token to be recorded with a `row_id` that conflicts with one or more linked parent tokens.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P1 — caller structurally prevents invalid state: _pending dict uses (coalesce_name, row_id) as key guaranteeing all parents share row_id; _execute_merge only called when len(arrived) > 0; defense-in-depth hardening only)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/tokens.py
- Line(s): 286-293
- Function/Method: `TokenManager.coalesce_tokens`

## Evidence

`coalesce_tokens()` takes `row_id` from only the first parent and never checks the rest:

```python
# /home/john/elspeth-rapid/src/elspeth/engine/tokens.py:286-293
row_id = parents[0].row_id
...
merged = self._recorder.coalesce_tokens(
    parent_token_ids=[p.token_id for p in parents],
    row_id=row_id,
    step_in_pipeline=step,
)
```

Recorder-side coalesce also trusts caller input and does not validate parent/row consistency:

```python
# /home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py:275-319
def coalesce_tokens(..., parent_token_ids: list[str], row_id: str, ...):
    ... insert merged token with row_id ...
    for parent_id in parent_token_ids:
        ... insert parent link ...
```

I reproduced this with an in-memory script: two parents from different rows were coalesced successfully; output showed:

- `parent row ids`: two different IDs
- `merged row id`: first parent's row ID
- parent links include both parents (including the mismatched row)

So the audit graph can persist contradictory lineage instead of failing fast.

Tests currently cover happy-path same-row coalesce only (e.g. `/home/john/elspeth-rapid/tests/unit/engine/test_tokens.py:203-211`) and do not cover mixed-row or empty-parent inputs.

## Root Cause Hypothesis

The method encodes an implicit assumption ("they should all be the same") but does not enforce it. Because `TokenManager` is the production caller of recorder coalesce, this unchecked assumption can convert upstream orchestration bugs into persisted audit inconsistency.

## Suggested Fix

Add explicit invariant checks in `TokenManager.coalesce_tokens()` before any recorder call:

```python
if not parents:
    raise ValueError("coalesce_tokens requires at least one parent token")

row_id = parents[0].row_id
mismatched = [p.token_id for p in parents if p.row_id != row_id]
if mismatched:
    raise ValueError(
        f"coalesce_tokens requires all parents to share row_id={row_id}; "
        f"mismatched token_ids={mismatched}"
    )
```

Optional follow-up defense-in-depth test additions:

- reject empty `parents`
- reject mixed-`row_id` parents

## Impact

- Violates audit-lineage integrity: merged token `row_id` can disagree with linked parent lineage.
- Breaks strict traceability guarantees ("every decision traceable to source row") by allowing contradictory row ancestry in persisted records.
- Masks upstream bugs instead of crashing at a trust/invariant boundary, contrary to Tier-1/Tier-2 fail-fast expectations.
