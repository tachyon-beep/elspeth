# Bug Report: Aggregation validation hides missing `is_batch_aware` attribute with `getattr`

**Status: CLOSED (Fixed)**

## Status Update (2026-02-11)

- Classification: **Fixed**
- Verification summary:
  - Aggregation validation now uses direct attribute access (`transform.is_batch_aware`) instead of `getattr(..., False)`.
  - Missing `is_batch_aware` now surfaces as an `AttributeError` (interface violation) rather than being masked as `False`.
  - Existing regression coverage validates aggregation gating behavior in `tests/unit/cli/test_cli_helpers.py`.
- Current evidence:
  - `src/elspeth/cli_helpers.py:65` (direct `transform.is_batch_aware` access)
  - `tests/unit/cli/test_cli_helpers.py:105`
  - `tests/unit/cli/test_cli_helpers.py:213`

## Summary

- Aggregation validation uses `getattr(..., False)` on a system-owned transform, masking a missing `is_batch_aware` attribute (interface violation) as a configuration error.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ e0060836
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit for `src/elspeth/cli_helpers.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Register or configure a transform that does not define `is_batch_aware` (e.g., forgets to subclass `BaseTransform`).
2. Reference that transform in `aggregations` and run a CLI path that calls `instantiate_plugins_from_config`.

## Expected Behavior

- The missing `is_batch_aware` attribute should surface as an interface violation (AttributeError or explicit protocol error), signaling a system bug.

## Actual Behavior

- The code treats the missing attribute as `False` and raises a ValueError about `is_batch_aware=False`, masking the real contract violation.

## Evidence

- `src/elspeth/cli_helpers.py:54` uses `getattr(transform, "is_batch_aware", False)` in aggregation validation.
- `src/elspeth/plugins/protocols.py:192` defines `is_batch_aware` as a required TransformProtocol attribute.
- `CLAUDE.md:918` prohibits defensive patterns like `getattr` that hide system-owned bugs.

## Impact

- User-facing impact: Misleading error message that points to configuration instead of a plugin interface bug.
- Data integrity / security impact: None directly; pipeline fails fast but with incorrect diagnosis.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Defensive programming pattern (`getattr` with a default) is used on system-owned plugin objects, which violates the no-bug-hiding rule and masks interface violations.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/cli_helpers.py`, access `transform.is_batch_aware` directly and let AttributeError surface; keep the ValueError only for the explicit `False` case.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that injects a transform missing `is_batch_aware` and asserts that plugin instantiation fails with an interface violation rather than a config error.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:918`
- Observed divergence: `getattr(..., False)` hides missing attributes on system-owned plugins.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Remove defensive attribute access and rely on explicit attributes per protocol.

## Acceptance Criteria

- Aggregation validation raises a clear interface violation when `is_batch_aware` is missing.
- Aggregation validation still raises a ValueError when `is_batch_aware` is present and `False`.
- No defensive attribute access remains in the aggregation validation path.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/cli/test_cli_helpers.py -k instantiate_plugins_from_config`
- New tests required: yes, add a test covering missing `is_batch_aware`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:918`
