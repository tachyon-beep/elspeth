## Summary

`sanitize_for_canonical()` does not actually sanitize all non-finite float cases it claims to handle (e.g., NumPy float scalars, tuple nesting).

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/canonical.py
- Line(s): 258-274
- Function/Method: `sanitize_for_canonical`

## Evidence

Implementation only recurses `dict` and `list`, and only replaces non-finite values when `isinstance(obj, float)` (`src/elspeth/core/canonical.py:268-273`).

So `np.float32("nan")` and tuple-contained infinities are missed:

```python
sanitize_for_canonical({"x": np.float32("nan")})  # {"x": np.float32(nan)} (unchanged)
sanitize_for_canonical({"x": (1.0, float("inf"))})  # {"x": (1.0, inf)} (unchanged)
```

This conflicts with how orchestrator comments describe intended behavior before hash operations (`src/elspeth/engine/orchestrator/core.py:1393-1397`).

## Root Cause Hypothesis

The sanitizer was implemented for a narrow subset of Python container/value types and was not kept aligned with the broader numeric/container variants present elsewhere in canonical normalization.

## Suggested Fix

Expand sanitizer traversal and value checks to include:
- `float | np.floating`
- `tuple` (and optionally generic `Mapping` / sequence handling)
- optional `np.ndarray` recursive sanitization path

Then add focused tests for `np.float32/np.float64` non-finite values and tuple nesting.

## Impact

Rows expected to be sanitized still hit non-canonical paths, forcing `repr_hash` fallbacks instead of deterministic canonical hashing in quarantine-related flows, reducing consistency of hash-based observability/audit correlation.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/canonical.py.md`
- Finding index in source report: 2
- Beads: pending
