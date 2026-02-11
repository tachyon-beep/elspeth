# Bug Report: Truncate Silently Skips Non-String Values

**Status: FIXED**

## Resolution (2026-02-11)

- Classification: **Fixed**
- Summary of fix:
  - `Truncate.process()` now returns `TransformResult.error` with `reason=type_mismatch` for configured fields that are not strings, regardless of `strict`.
  - Truncation tracking now records `fields_modified` inline during mutation, removing defensive `isinstance`-based post filtering.
  - Contract tests now assert that non-string configured fields return an explicit error instead of silently passing through.
- Verification:
  - `uv run pytest -q tests/unit/contracts/transform_contracts/test_truncate_contract.py` (76 passed)
  - `UV_CACHE_DIR=.uv-cache uv run ruff check src/elspeth/plugins/transforms/truncate.py tests/unit/contracts/transform_contracts/test_truncate_contract.py` (passed)
  - `UV_CACHE_DIR=.uv-cache uv run --with mypy mypy src/elspeth/plugins/transforms/truncate.py tests/unit/contracts/transform_contracts/test_truncate_contract.py` (passed)


## Summary

- Truncate uses `isinstance(..., str)` to skip non-string values, which contradicts its own contract ("wrong types crash immediately") and the Tier 2 trust model; upstream type violations are silently passed through.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ `0282d1b441fe23c5aaee0de696917187e1ceeb9b`
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Row with a configured truncate field containing a non-string value (e.g., `{"title": 123}`) under a schema that declares `title` as `str`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/plugins/transforms/truncate.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `truncate` with `fields: {title: 5}` and a schema that declares `title` as `str` (non-observed mode).
2. Run the transform on a row where `title` is non-string (e.g., `123`).

## Expected Behavior

- The transform should not silently accept a wrong type; it should crash (or otherwise surface a hard failure) because upstream produced a type violation.

## Actual Behavior

- The transform silently skips non-string values and returns success, letting type violations pass through unchanged.

## Evidence

- `src/elspeth/plugins/transforms/truncate.py:5` and `src/elspeth/plugins/transforms/truncate.py:6` state that wrong types should crash immediately.
- `src/elspeth/plugins/transforms/truncate.py:125` through `src/elspeth/plugins/transforms/truncate.py:129` skip non-string values via `isinstance(..., str)` and `continue`.
- `src/elspeth/plugins/transforms/truncate.py:140` through `src/elspeth/plugins/transforms/truncate.py:145` repeat `isinstance` checks, reinforcing the skip.
- `tests/unit/plugins/transforms/test_truncate.py:164` through `tests/unit/plugins/transforms/test_truncate.py:177` encode the current "non-string unchanged" behavior.

## Impact

- User-facing impact: Rows with invalid types appear to be successfully transformed, masking upstream bugs.
- Data integrity / security impact: Output schema expectations are violated without a crash; audit trail records a "success" while carrying invalid types.
- Performance or cost impact: Minor; primary impact is correctness and audit integrity.

## Root Cause Hypothesis

- Defensive `isinstance` checks in `Truncate.process()` intentionally bypass type errors, contradicting the stated contract and Tier 2 trust model.

## Proposed Fix

- Code changes (modules/files): Enforce string-only behavior for configured fields in `src/elspeth/plugins/transforms/truncate.py` by removing the skip and raising a hard failure on non-string values; remove `isinstance` checks from `fields_modified` or replace with contract-aware checks that do not suppress errors.
- Config or schema changes: None.
- Tests to add/update: Update `tests/unit/plugins/transforms/test_truncate.py` to expect a hard failure on non-string values; add a test case for explicit type mismatch under a fixed schema.
- Risks or migration steps: This will break the current "non-string unchanged" test; aligns behavior with documented contract and trust model.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` "Three-Tier Trust Model" and "PROHIBITION ON DEFENSIVE PROGRAMMING PATTERNS" sections.
- Observed divergence: Transform uses `isinstance` and silently skips incorrect types, contradicting "Transforms expect conformance" and "no defensive programming" guidance.
- Reason (if known): Legacy tolerance encoded as behavior and tests.
- Alignment plan or decision needed: Align Truncate to crash on wrong types to maintain Tier 2 contract and audit integrity.

## Acceptance Criteria

- When a configured truncate field is non-string under a schema expecting `str`, the transform hard-fails (exception or equivalent crash) instead of returning success.
- Unit tests reflect the new failure behavior for non-string inputs.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_truncate.py`
- New tests required: yes, add/adjust tests for type mismatch behavior.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Three-Tier Trust Model; Prohibition on Defensive Programming)
