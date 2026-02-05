# Bug Report: Gate Route Labels Are Lowercased During Config Normalization

## Summary

- `_lowercase_schema_keys()` lowercases `GateSettings.routes` keys, silently mutating user-defined route labels and causing case-sensitive label mismatches at runtime.

## Status

**FIXED** - 2026-02-06

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074e
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/config.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a settings file with a config gate condition that returns a mixed-case string (e.g., `condition: "row['priority']"`), and routes like `{ "High": "continue", "Low": "review_sink" }`.
2. Load settings via `load_settings()` (or run pipeline).
3. Execute a row with `priority == "High"`; gate evaluation returns `"High"` but `gate_config.routes` has been lowercased to `"high"` and raises `ValueError`.

## Expected Behavior

- Gate route labels should be preserved exactly as written so that string results match route keys.

## Actual Behavior

- Route labels are lowercased during config normalization, causing gate routing failures for mixed-case labels.

## Evidence

- `_lowercase_schema_keys()` lowercases all dict keys except `options` and sink names, with no special case for `routes`. See `src/elspeth/core/config.py:1483`, `src/elspeth/core/config.py:1495`, `src/elspeth/core/config.py:1502`.
- `GateExecutor` matches route labels exactly and raises when a label is missing. See `src/elspeth/engine/executors.py:833`, `src/elspeth/engine/executors.py:842`, `src/elspeth/engine/executors.py:855`.
- `GateSettings` does not enforce lowercase route labels, implying case-sensitive labels are valid. See `src/elspeth/core/config.py:340`.

## Impact

- User-facing impact: Config-driven gates can fail at runtime for valid mixed-case labels, producing `ValueError` and halting routing.
- Data integrity / security impact: Misrouting or failed routing undermines audit traceability for affected rows.
- Performance or cost impact: Additional failures/retries or aborted runs.

## Root Cause Hypothesis

- The config normalization step treats `routes` as schema keys and lowercases them, even though route labels are user-defined and should remain case-sensitive.

## Fix Applied

**File:** `src/elspeth/core/config.py`

**Changes:**

1. Updated `_lowercase_schema_keys()` docstring to document that both `options` and `routes` preserve case (lines 1462-1466).

2. Added special case for `routes` key (lines 1506-1508):
   ```python
   elif new_key == "routes":
       # Routes: preserve everything inside (user-defined route labels)
       child = _lowercase_schema_keys(v, _preserve_nested=True, _in_sinks=False)
   ```

**Test Added:** `tests/core/test_config.py::TestLoadSettingsWithGates::test_load_settings_preserves_mixed_case_route_labels`

This regression test verifies that mixed-case route labels like `{"High": "urgent", "Medium": "continue", "Low": "archive"}` are preserved exactly through `load_settings()`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/reference/configuration.md:321`.
- Observed divergence: Route labels are documented as evaluation results that must match the returned value; lowercasing labels breaks that contract.
- Reason (if known): Config normalization over-applies lowercasing to user data.
- Alignment plan or decision needed: Preserve route label keys during normalization.

## Acceptance Criteria

- A gate with mixed-case route labels loads without mutation and routes correctly when the condition returns that label.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_config.py -k gate`
- New tests required: yes, verify `routes` keys retain case through `load_settings()` and config-gate execution.

**Test Results:** All 26 gate-related tests pass including the new regression test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/reference/configuration.md:321`
