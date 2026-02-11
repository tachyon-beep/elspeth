# Bug Report: Canonicalization Crashes on Zero‑Dimensional NumPy Arrays

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - `canonical_json(np.array(5))` still raises `TypeError: 'int' object is not iterable`.
  - The ndarray path still iterates over `obj.tolist()` unconditionally, which breaks for 0-D arrays.
- Current evidence:
  - `src/elspeth/core/canonical.py:76`
  - `src/elspeth/core/canonical.py:90`

## Summary

- Canonical JSON normalization assumes `np.ndarray.tolist()` is iterable and crashes on 0‑D arrays (scalar arrays), raising `TypeError` instead of normalizing to a JSON‑safe primitive.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 1c70074e
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: synthetic `np.array(5)` scalar array in row/config

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/canonical.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `canonical_json(np.array(5))` or `stable_hash({"x": np.array(5)})`.
2. `_normalize_value` hits the `np.ndarray` branch and executes `[_normalize_value(x) for x in obj.tolist()]`.

## Expected Behavior

- Zero‑dimensional arrays are normalized to a JSON‑safe primitive (e.g., `5`), consistent with the stated “numpy types to primitives” policy.

## Actual Behavior

- `np.array(5).tolist()` returns a scalar, so the list comprehension raises `TypeError: 'int' object is not iterable`, aborting canonicalization and hashing.

## Evidence

- `src/elspeth/core/canonical.py:75-89`
  The `np.ndarray` branch assumes `obj.tolist()` is iterable and immediately list‑comprehends over it, which fails for 0‑D arrays.

## Impact

- User-facing impact: Pipeline runs can crash during hashing when a plugin emits a scalar `np.ndarray` (common in NumPy‑heavy code paths).
- Data integrity / security impact: Audit trail hash generation fails, preventing payload persistence and breaking determinism guarantees.
- Performance or cost impact: Run failures require manual intervention/retries; wasted compute.

## Root Cause Hypothesis

- `_normalize_value` treats all `np.ndarray` values as iterable collections, but NumPy scalar arrays (`shape == ()`) return a scalar from `tolist()`, causing a `TypeError`.

## Proposed Fix

- Code changes (modules/files):
  - Detect zero‑dimensional arrays in `src/elspeth/core/canonical.py` and normalize via `obj.item()` (or `obj.tolist()` without iteration) before recursion.
- Config or schema changes: None.
- Tests to add/update:
  - Add unit tests in `tests/core/test_canonical.py` verifying `canonical_json(np.array(5))` and `canonical_json(np.array(3.14))` succeed and produce canonical primitives.
- Risks or migration steps:
  - Low risk; only affects normalization of 0‑D arrays.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` “Canonical JSON - Two‑Phase with RFC 8785” (normalize numpy types to primitives).
- Observed divergence: Zero‑dimensional NumPy arrays are not normalized to primitives and instead crash.
- Reason (if known): Missing special case for `np.ndarray` with `ndim == 0`.
- Alignment plan or decision needed: Add scalar array handling to align with stated normalization policy.

## Acceptance Criteria

- `canonical_json(np.array(5))` returns `"5"` (or equivalent canonical numeric JSON) without error.
- `stable_hash({"x": np.array(5)})` completes deterministically.
- New tests for 0‑D arrays pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_canonical.py -k "numpy_array"`
- New tests required: yes, add 0‑D NumPy array normalization tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Canonical JSON section)

## Verification Status

- [x] Bug confirmed via reproduction
- [x] Root cause verified
- [x] Fix implemented
- [x] Tests added
- [x] Fix verified

## Resolution (2026-02-12)

**Fixed by:** Codex (GPT-5)

**Changes:**
- `src/elspeth/core/canonical.py`: Added explicit `np.ndarray` `ndim == 0` handling so scalar arrays normalize as scalar primitives via `obj.item()`.
- `tests/unit/core/test_canonical.py`: Added regression coverage for `_normalize_value(np.array(...))`, `canonical_json({"value": np.array(5)})`, and `stable_hash` parity against scalar values.

**Verification:**
- Repro before fix: `canonical_json(np.array(5))` raised `TypeError: 'int' object is not iterable`.
- Post-fix tests:
  - `uv run pytest -q tests/unit/core/test_canonical.py`
  - `uv run pytest -q tests/property/canonical/test_nan_rejection.py tests/property/canonical/test_hash_determinism.py`
  - `uv run ruff check src/elspeth/core/canonical.py tests/unit/core/test_canonical.py`
  - `UV_CACHE_DIR=.uv-cache uv run --with mypy mypy src/elspeth/core/canonical.py`
