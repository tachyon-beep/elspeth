# Bug Report: Observed Schema Silently Accepts Non-List `fields` Values

## Summary

- In `mode: observed`, `SchemaConfig.from_dict()` ignores any `fields` value that is not a non-empty list, allowing invalid configs (e.g., `fields: "id: int"` or a dict) to pass without error and dropping the user’s explicit schema intent.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 3aa2fa93d8ebd2650c7f3de23b318b60498cd81c (branch: RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Minimal schema config dict

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit for `/home/john/elspeth-rapid/src/elspeth/contracts/schema.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `SchemaConfig.from_dict({"mode": "observed", "fields": "id: int"})`.
2. Observe that no exception is raised and the returned config is treated as observed (no explicit fields).

## Expected Behavior

- `SchemaConfig.from_dict()` should reject any `fields` value for `mode: observed` that is not `None` or an empty list, raising a `ValueError` for non-list values.

## Actual Behavior

- Non-list `fields` values are silently ignored in observed mode, resulting in an observed schema with `fields=None` and no error.

## Evidence

- `src/elspeth/contracts/schema.py:324-334` only raises when `fields_value` is a non-empty list; non-list values bypass validation and return an observed schema with `fields=None`.

## Impact

- User-facing impact: Misconfigured pipelines can silently bypass intended schema enforcement.
- Data integrity / security impact: Invalid or malformed rows can flow without validation, weakening audit guarantees.
- Performance or cost impact: None direct.

## Root Cause Hypothesis

- The observed-mode branch only checks `isinstance(fields_value, list)` and `len > 0`, leaving non-list types unvalidated.

## Proposed Fix

- Code changes (modules/files): Tighten observed-mode validation in `src/elspeth/contracts/schema.py` to reject any non-`None` `fields` value that is not an empty list.
- Config or schema changes: None.
- Tests to add/update: Add tests in `tests/contracts/test_schema_config.py` for observed mode with `fields` as a string and as a dict, asserting `ValueError`.
- Risks or migration steps: Low; this only rejects invalid configs that were previously (incorrectly) accepted.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/schema.py:252-265` (observed schemas accept anything but do not define explicit field types).
- Observed divergence: Non-list `fields` values are accepted and effectively ignored, despite being explicit field definitions.
- Reason (if known): Missing type validation for `fields` in observed mode.
- Alignment plan or decision needed: Enforce `fields is None or []` for observed mode; reject all other types.

## Acceptance Criteria

- `SchemaConfig.from_dict()` raises `ValueError` when `mode: observed` and `fields` is a non-list (e.g., string or dict).
- Existing schema tests pass, with new tests covering the invalid observed-mode `fields` types.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_schema_config.py`
- New tests required: yes, observed-mode `fields` non-list validation cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
