## Summary

Coalesce timeout/flush handling silently ignores invalid `CoalesceOutcome` states (neither merged nor failed), which can hide coalesce-state bugs and lose continuation work.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P1 — requires a bug in CoalesceExecutor to produce an outcome with both merged_token=None and failure_reason=None; defense-in-depth hardening only, not a reachable gap)

## Location

- File: `src/elspeth/engine/orchestrator/outcomes.py`
- Line(s): `155-176`, `206-233`
- Function/Method: `handle_coalesce_timeouts`, `flush_coalesce_pending`

## Evidence

Both functions only handle two branches:

```python
if outcome.merged_token is not None:
    ...
elif outcome.failure_reason:
    counters.rows_coalesce_failed += 1
```

No `else` invariant check exists. If a malformed outcome arrives (`merged_token is None` and `failure_reason is None`, or contradictory fields), it is silently ignored.

Related contract evidence: `CoalesceOutcome` in `src/elspeth/engine/coalesce_executor.py:31-53` has no `__post_init__` invariants enforcing valid state combinations, so the orchestrator layer should guard explicitly.

`flush_coalesce_pending` additionally uses `assert` for required `coalesce_name` (`outcomes.py:211`), which is weaker than explicit invariant errors.

## Root Cause Hypothesis

The code assumes executor outputs are always valid and omits fail-fast validation in the orchestrator boundary layer.

## Suggested Fix

Validate outcome state explicitly before branching, and replace `assert` with `OrchestrationInvariantError`.

Example pattern:

```python
has_merged = outcome.merged_token is not None
has_failure = outcome.failure_reason is not None
if has_merged == has_failure:
    raise OrchestrationInvariantError(
        f"Invalid CoalesceOutcome state: merged={has_merged}, failure={outcome.failure_reason!r}"
    )
```

Then process merged/failure branches explicitly using `is not None` checks.

## Impact

Malformed coalesce outcomes can be dropped without sink continuation or failure accounting in this layer, violating fail-fast expectations and creating audit/metrics blind spots.
