# Bug Report: BatchStats silently drops configured `group_by` field instead of failing fast

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Resolved**
- Resolution summary:
  - Updated `BatchStats` to require configured `group_by` in every batch row using direct field access.
  - Missing configured `group_by` now fails fast with `KeyError` instead of silent omission.
  - Added unit coverage for missing `group_by` in both first row and later rows.


## Summary

- When `group_by` is configured but missing from the batch rows, `BatchStats` silently omits the field instead of failing fast. This hides upstream schema/config errors and violates the “no defensive programming” policy.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory rows missing `group_by`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/transforms/batch_stats.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `BatchStats` with `group_by: "category"`.
2. Call `process(rows, ctx)` where the first row lacks `"category"`.

## Expected Behavior

- The transform should fail fast (KeyError) because a configured field is missing from Tier 2 pipeline data, indicating an upstream bug or invalid configuration.

## Actual Behavior

- The transform silently skips the `group_by` field, returning a “successful” aggregate without the configured context field.

## Evidence

- Defensive membership checks suppress missing `group_by` without raising: `src/elspeth/plugins/transforms/batch_stats.py:175-184`.
- Policy prohibits defensive patterns that hide missing fields in system-owned code: `CLAUDE.md:918-974`.

## Impact

- User-facing impact: Aggregates lack configured grouping context without any failure signal.
- Data integrity / security impact: Silent data loss in audit-relevant output (missing group context), undermining traceability.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `group_by` presence is guarded by `if self._group_by in rows[0]` rather than direct access, masking upstream schema issues.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/transforms/batch_stats.py`: Replace membership checks with direct access to `rows[0][self._group_by]` when `group_by` is configured; include it unconditionally in `fields_added` for non-empty batches.
- Config or schema changes: Optional follow-up to validate `group_by` against input schema at config-validation time.
- Tests to add/update:
  - Add a test asserting `KeyError` (or a hard failure) when `group_by` is configured but missing from input rows.
- Risks or migration steps:
  - Low risk; failure is intentional to surface upstream bugs.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:918-974`
- Observed divergence: Defensive presence checks hide missing configured fields rather than failing fast.
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce direct field access for configured `group_by`.

## Acceptance Criteria

- With `group_by` configured, missing fields cause a hard failure (no silent omission).
- Tests cover the missing `group_by` case.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/transforms/test_batch_stats.py`
- New tests required: yes, missing `group_by` should fail.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`

---

## Verification (2026-02-11)

- Reproduced before fix: configured `group_by` was silently omitted when absent from rows.
- Post-fix behavior:
  - Missing configured `group_by` raises `KeyError`.
  - Heterogeneous `group_by` values continue to raise `ValueError`.
  - Homogeneous `group_by` continues to be emitted in output.
- Tests executed:
  - `PYTHONPATH=src .venv/bin/python -m pytest -q tests/unit/plugins/transforms/test_batch_stats.py tests/unit/plugins/transforms/test_batch_stats_integration.py`
  - `ruff check src/elspeth/plugins/transforms/batch_stats.py tests/unit/plugins/transforms/test_batch_stats.py`
