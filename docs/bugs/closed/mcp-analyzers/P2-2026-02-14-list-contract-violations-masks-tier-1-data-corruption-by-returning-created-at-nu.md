## Summary

`list_contract_violations()` masks Tier-1 data corruption by returning `created_at: null` instead of crashing when `created_at` is unexpectedly missing.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 — Python datetime objects are always truthy so the truthiness check never triggers for non-None values; this is a read-only diagnostic path where crashing would prevent investigating actual corruption)

## Location

- File: `src/elspeth/mcp/analyzers/contracts.py`
- Line(s): 189
- Function/Method: `list_contract_violations`

## Evidence

The function uses a defensive null fallback on audit DB data:

```python
"created_at": row.created_at.isoformat() if row.created_at else None,
```

But `validation_errors.created_at` is declared non-null:

- `src/elspeth/core/landscape/schema.py:413`

Per Tier-1 policy in `CLAUDE.md`, anomalies in our audit data should crash immediately, not be silently coerced to a plausible output.

## Root Cause Hypothesis

A generic optional-datetime serialization pattern was applied in an audit-tier query path where strict invariants should be enforced.

## Suggested Fix

Remove the fallback and require strict presence:

```python
"created_at": row.created_at.isoformat(),
```

If `created_at` is `None`, let it fail loudly so corruption/contract drift is detected immediately.

## Impact

Potential audit DB corruption is hidden from operators and auditors, weakening integrity guarantees and delaying root-cause detection.

## Triage

- Status: open
- Source report: `docs/bugs/generated/mcp/analyzers/contracts.py.md`
- Finding index in source report: 2
- Beads: pending
