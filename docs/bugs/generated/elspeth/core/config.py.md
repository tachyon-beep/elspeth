# Bug Report: Gate Route Labels Are Lowercased During Config Load

## Summary

- `load_settings()` lowercases gate `routes` labels via `_lowercase_schema_keys`, but gate execution treats route labels as case-sensitive, causing runtime routing failures for mixed-case labels.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Settings YAML with a gate condition returning a mixed-case string route label

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/config.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a settings file with a config-driven gate whose condition returns a string value, e.g. `row['status']`, and configure routes with mixed-case labels like `"Approved"` and `"Rejected"`.
2. Call `load_settings()` on the file and run a pipeline where `row['status']` returns `"Approved"`.

## Expected Behavior

- Gate route labels should be preserved exactly as configured, allowing case-sensitive matching to the evaluated result.

## Actual Behavior

- Route labels are lowercased during config load, so the evaluated route label (`"Approved"`) is not found, raising a `ValueError` and failing the node/run.

## Evidence

- `_lowercase_schema_keys` lowercases all dict keys except `options` and sink names, so `routes` labels are mutated. `src/elspeth/core/config.py:1458`
- Gate route labels are used as case-sensitive keys in runtime routing; the evaluated result must match exactly. `src/elspeth/engine/executors.py:817`
- Gate routes are defined as a mapping of user-provided labels to destinations (not schema keys), so changing their case alters semantics. `src/elspeth/core/config.py:314`

## Impact

- User-facing impact: Config-driven gates fail at runtime when route labels use mixed case or must exactly match row values.
- Data integrity / security impact: Run can fail mid-execution; audit trail records a failed node state rather than the intended routing.
- Performance or cost impact: Failed runs and retries increase compute and operational cost.

## Root Cause Hypothesis

- `_lowercase_schema_keys` treats gate `routes` labels as schema keys and lowercases them, but these labels are user-defined data that must be preserved for exact matching.

## Proposed Fix

- Code changes (modules/files):
  - Update `_lowercase_schema_keys` to preserve keys within the `routes` mapping (similar to how `options` is preserved). `src/elspeth/core/config.py:1458`
- Config or schema changes: None
- Tests to add/update:
  - Add a `load_settings` regression test ensuring mixed-case `routes` labels are preserved exactly. `tests/core/test_config.py`
  - Add a gate execution test verifying routing succeeds when condition returns mixed-case strings matching configured labels. `tests/engine/test_gate_executor.py`
- Risks or migration steps:
  - Low risk; only affects normalization of route labels and should not impact schema key normalization.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25` (Tier 1 data: “No coercion, no defaults”)
- Observed divergence: Route labels (our config data) are silently coerced to lowercase.
- Reason (if known): Key-normalization function treats all dict keys as schema keys.
- Alignment plan or decision needed: Preserve `routes` labels as user data while continuing to lowercase schema keys.

## Acceptance Criteria

- Loading settings preserves `routes` label case exactly.
- Gate execution successfully routes when condition returns a mixed-case string matching configured labels.
- Existing schema key normalization for non-user-data keys remains unchanged.

## Tests

- Suggested tests to run: `python -m pytest tests/core/test_config.py tests/engine/test_gate_executor.py`
- New tests required: yes, add coverage for case-preserving routes.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 1 no-coercion guidance)
