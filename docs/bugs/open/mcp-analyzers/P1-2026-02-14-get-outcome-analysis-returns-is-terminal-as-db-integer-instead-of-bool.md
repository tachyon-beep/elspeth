## Summary

`get_outcome_analysis()` returns `is_terminal` as DB integer (`0/1`) instead of `bool`, violating the declared report contract and skipping Tier-1 invariant validation.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — aggregate calculations using truthiness on 0/1 are correct; only JSON serialization shows 1/0 instead of true/false; contract type drift, not wrong answers)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/mcp/analyzers/reports.py`
- Line(s): `640-642`, `681-683`
- Function/Method: `get_outcome_analysis`

## Evidence

Report payload uses raw DB value:

```python
"is_terminal": row.is_terminal,
```

But contract expects `bool` (`mcp/types.py`, `OutcomeDistributionEntry.is_terminal: bool`, line `331`).

Schema stores `is_terminal` as `Integer` (`schema.py`, line `155`), and repository code explicitly converts/validates it (`repositories.py`, lines `470-488`), which this report bypasses.

## Root Cause Hypothesis

Direct SQL aggregation reused raw storage representation without normalizing to API contract type or applying existing integrity checks.

## Suggested Fix

Normalize and validate before emitting:

- Validate `row.is_terminal in (0, 1)`; raise on anomaly.
- Convert to `bool` (`row.is_terminal == 1`).
- Optionally validate consistency with `RowOutcome(outcome).is_terminal` like `TokenOutcomeRepository`.

## Impact

Clients receive contract-inconsistent data (`0/1` instead of `true/false`), and corrupted terminal flags can pass through analysis instead of failing fast.
