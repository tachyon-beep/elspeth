# Bug Report: BatchStats emits `mean` for empty batches even when `compute_mean=False`

## Summary

- `BatchStats.process()` always includes `mean` in the empty-batch path, ignoring the `compute_mean` setting. This produces inconsistent output/contract behavior relative to non-empty batches and documented intent.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory rows (empty list)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/transforms/batch_stats.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `BatchStats` with `compute_mean: False`.
2. Call `process([], ctx)` with an empty batch.

## Expected Behavior

- The output should not include the `mean` field, and the contract should omit `mean` when `compute_mean=False`.

## Actual Behavior

- The empty-batch branch always includes `mean` and reports it in `fields_added`, even when `compute_mean=False`.

## Evidence

- Empty-batch branch unconditionally sets `mean` and `fields_added` includes `mean`: `src/elspeth/plugins/transforms/batch_stats.py:116-139`.
- Intent that `compute_mean=False` should omit `mean` is tested for non-empty batches: `tests/plugins/transforms/test_batch_stats_integration.py:108-126`.

## Impact

- User-facing impact: Inconsistent output shape depending on whether the batch is empty; downstream consumers may see `mean` unexpectedly.
- Data integrity / security impact: Minor schema/contract inconsistency; could mislead consumers expecting `mean` to be absent when disabled.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The empty-batch fast path hardcodes `mean` in `result_data` and `fields_added` without checking `self._compute_mean`.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/transforms/batch_stats.py`: In the empty-batch branch, conditionally include `mean` and `fields_added` based on `self._compute_mean`, mirroring the non-empty logic.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test for empty batch with `compute_mean=False` to assert `mean` is absent and the contract omits `mean`.
- Risks or migration steps:
  - Low risk; output becomes consistent with non-empty behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: `compute_mean` setting is ignored for empty batches.
- Reason (if known): Unknown
- Alignment plan or decision needed: Ensure empty-batch path respects `compute_mean` and matches non-empty behavior.

## Acceptance Criteria

- With `compute_mean=False`, both empty and non-empty batches omit `mean` from output and contract.
- Tests cover empty-batch `compute_mean=False`.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/transforms/test_batch_stats_integration.py`
- New tests required: yes, empty-batch `compute_mean=False` case.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `tests/plugins/transforms/test_batch_stats_integration.py`
---
# Bug Report: BatchStats silently drops configured `group_by` field instead of failing fast

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
