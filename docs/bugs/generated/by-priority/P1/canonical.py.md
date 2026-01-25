# Bug Report: NaN/Infinity Rejection Bypassed in Multi-Dimensional NumPy Arrays

## Summary

- `np.ndarray` normalization only applies `_normalize_value` to top-level elements, so nested lists from multi-dimensional arrays bypass explicit NaN/Infinity checks and type normalization.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 86357898ee109a1dbb8d60f3dc687983fa22c1f0 / fix/rc1-bug-burndown-session-4
- OS: unknown
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: Synthetic 2D NumPy array containing NaN

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `/home/john/elspeth-rapid/src/elspeth/core/canonical.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In Python, create `arr = np.array([[1.0, float("nan")]], dtype=float)`.
2. Call `canonical_json({"array": arr})` (or `stable_hash({"array": arr})`).

## Expected Behavior

- NaN/Infinity in any position within a NumPy array should raise `ValueError` from the explicit non-finite check, regardless of array dimensionality.

## Actual Behavior

- `_normalize_value` converts the array to a list-of-lists and only normalizes the top-level elements, so nested NaN/Infinity values bypass the explicit check and fall through to the RFC8785 serializer, producing a non-policy error or invalid canonicalization.

## Evidence

- `src/elspeth/core/canonical.py:74` uses `return [_normalize_value(x) for x in obj.tolist()]`, which does not recurse into nested lists from multi-dimensional arrays.
- `src/elspeth/core/canonical.py:57` shows the NaN/Infinity check only runs inside `_normalize_value`, so nested elements are skipped.

## Impact

- User-facing impact: pipelines can crash unexpectedly when hashing row data containing multi-dimensional arrays with non-finite values or nested unsupported types.
- Data integrity / security impact: non-finite floats can bypass the explicit rejection policy, risking invalid audit hashes or inconsistent error handling.
- Performance or cost impact: Unknown.

## Root Cause Hypothesis

- ndarray normalization applies `_normalize_value` one level deep instead of using `_normalize_for_canonical` recursively on the list produced by `tolist()`.

## Proposed Fix

- Code changes (modules/files):
  - Update the `np.ndarray` branch in `src/elspeth/core/canonical.py` to call `_normalize_for_canonical(obj.tolist())` (or otherwise recursively normalize nested structures).
- Config or schema changes: None.
- Tests to add/update:
  - Add tests for multi-dimensional NumPy arrays with NaN/Infinity.
  - Add tests for object-dtype arrays containing `pd.Timestamp` or `Decimal` to confirm recursive normalization.
- Risks or migration steps:
  - Low; change is localized to normalization and should be covered by new tests.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:322`
- Observed divergence: Phase 1 normalization should reject NaN/Infinity across numpy types, but multi-dimensional arrays bypass the explicit rejection.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Make ndarray normalization recursive and add coverage for multi-dimensional arrays.

## Acceptance Criteria

- `canonical_json` raises `ValueError` with a non-finite message for NaN/Infinity anywhere inside NumPy arrays of any dimensionality.
- Multi-dimensional arrays containing supported types normalize without `TypeError`.
- New tests pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_canonical.py tests/property/canonical/test_nan_rejection.py`
- New tests required: yes, multi-dimensional array cases for NaN/Infinity and object arrays.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:322`
