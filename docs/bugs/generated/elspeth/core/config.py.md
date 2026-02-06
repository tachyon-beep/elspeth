# Bug Report: Gate Route Labels Are Lowercased During Config Normalization

## Summary

- `_lowercase_schema_keys()` lowercases `GateSettings.routes` keys, silently mutating user-defined route labels and causing case-sensitive label mismatches at runtime.

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

## Proposed Fix

- Code changes (modules/files): Add a special-case in `_lowercase_schema_keys()` to preserve keys under `routes` (similar to `options`), in `src/elspeth/core/config.py`.
- Config or schema changes: None.
- Tests to add/update: Add a config-loading test that asserts route labels preserve case; add a config-gate integration test with mixed-case labels.
- Risks or migration steps: None, behavior becomes less destructive and more aligned with docs.

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

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/reference/configuration.md:321`
---
# Bug Report: Trigger Condition Validation Allows Unsupported Keys

## Summary

- `TriggerConfig` validation does not enforce the documented batch-only context, allowing conditions that reference non-existent keys and fail at runtime.

## Severity

- Severity: minor
- Priority: P2

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

1. Configure an aggregation trigger condition with a row field not present in batch context, e.g., `condition: "row['type'] == 'flush_signal'"`.
2. Load settings; validation succeeds because the expression is syntactically valid and boolean.
3. Run aggregation; `TriggerEvaluator` evaluates against a context containing only `batch_count` and `batch_age_seconds`, raising an evaluation error.

## Expected Behavior

- Trigger condition validation should reject references to keys outside the batch-only context.

## Actual Behavior

- Invalid trigger conditions pass validation and crash later at runtime due to missing keys.

## Evidence

- Trigger conditions are documented as batch-only with `batch_count` and `batch_age_seconds`. See `src/elspeth/core/config.py:146`, `src/elspeth/core/config.py:148`.
- Validation only checks syntax/security/boolean-ness; it does not restrict field access. See `src/elspeth/core/config.py:178`, `src/elspeth/core/config.py:204`.
- Runtime evaluation context includes only `batch_count` and `batch_age_seconds`. See `src/elspeth/engine/triggers.py:119`, `src/elspeth/engine/triggers.py:121`.

## Impact

- User-facing impact: Configurations that look valid at load time fail during execution with trigger evaluation errors.
- Data integrity / security impact: Aggregation may fail mid-run, interrupting audit trail completion for affected batches.
- Performance or cost impact: Failed runs and retries increase wasted compute.

## Root Cause Hypothesis

- `TriggerConfig` validation lacks a whitelist for allowable row keys in trigger conditions, despite the batch-only contract.

## Proposed Fix

- Code changes (modules/files): Extend `TriggerConfig.validate_condition_expression()` to parse and reject any row key usage outside `batch_count` and `batch_age_seconds`; update the docstring/examples to show `row['batch_count']`/`row['batch_age_seconds']` usage explicitly.
- Config or schema changes: None.
- Tests to add/update: Add config validation tests that accept `row['batch_count']` and reject `row['type']`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/config.py:146`.
- Observed divergence: Validation permits row-key references outside the documented batch-only context.
- Reason (if known): Validation logic checks syntax/boolean but not allowed identifiers.
- Alignment plan or decision needed: Enforce the batch-only key whitelist at config time.

## Acceptance Criteria

- Trigger conditions referencing non-batch keys are rejected at config validation with a clear error, and valid batch-only conditions pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_config_aggregation.py -k trigger`
- New tests required: yes, add invalid-key and valid-key cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/core/config.py:146`
