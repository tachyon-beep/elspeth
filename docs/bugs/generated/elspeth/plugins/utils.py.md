# Bug Report: get_nested_field Hides Type Mismatches as “Missing” in Pipeline Data

## Summary

- `get_nested_field` returns the default sentinel when an intermediate value is not a `dict`, which silently masks type violations in Tier 2 pipeline data and violates the no-defensive-programming rule.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row / 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Row where a dotted mapping expects a dict but the intermediate value is a non-dict (e.g., `{"user": "string_not_dict"}`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/utils.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `field_mapper` with mapping `{"user.name": "origin"}`.
2. Process a row where `user` is a string: `{"user": "string_not_dict"}`.
3. Observe that `get_nested_field` returns `MISSING`, causing the mapping to be skipped (or a “missing_field” error in strict mode) instead of surfacing a type violation.

## Expected Behavior

- A non-dict intermediate value on a dotted path should raise a clear error (TypeError/ValueError) because pipeline data types are expected to be correct; this should not be treated as “missing.”

## Actual Behavior

- `get_nested_field` returns the default/MISSING sentinel when the intermediate value is not a `dict`, masking the type error and allowing processing to continue.

## Evidence

- `src/elspeth/plugins/utils.py:48` shows the `isinstance(current, dict)` guard that returns the default on non-dict intermediates.
- `src/elspeth/plugins/utils.py:49` returns the default/MISSING sentinel, conflating type mismatch with missing path.
- `tests/plugins/test_utils.py:74` and `tests/plugins/test_utils.py:81` codify the current behavior by asserting non-dict intermediates return `MISSING`.
- `src/elspeth/plugins/transforms/field_mapper.py:114` uses `get_nested_field`, so this defensive behavior affects actual mapping output.
- `CLAUDE.md:81` and `CLAUDE.md:86` state that transforms must “expect types” and “bug if types are wrong.”

## Impact

- User-facing impact: Mapped fields can silently disappear when the input type is wrong, producing incomplete output without a clear failure.
- Data integrity / security impact: Violates the Tier 2 trust model by masking upstream bugs; audit outputs can be misleading because a type error is treated as “missing.”
- Performance or cost impact: Low.

## Root Cause Hypothesis

- `get_nested_field` conflates “missing path” with “wrong intermediate type” by returning the default when `current` is not a `dict`, which is a prohibited defensive pattern for pipeline data.

## Proposed Fix

- Code changes (modules/files): Update `get_nested_field` in `src/elspeth/plugins/utils.py` to raise a `TypeError` (or `ValueError`) when an intermediate value is not a `dict`, and only return the default when the key is genuinely missing.
- Config or schema changes: None.
- Tests to add/update: Update `tests/plugins/test_utils.py` to expect an exception for non-dict intermediates; add a `field_mapper` test to assert type mismatches crash rather than being treated as missing.
- Risks or migration steps: Pipelines currently relying on the defensive behavior will now surface upstream type bugs; this is consistent with policy.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:81` and `CLAUDE.md:86`; `CLAUDE.md:918` and `CLAUDE.md:920`.
- Observed divergence: The utility uses defensive type checking to suppress errors from incorrect types, contrary to the “expect types / bug if types are wrong” rule and the prohibition on defensive programming.
- Reason (if known): Legacy utility behavior and tests that treat non-dict intermediates as “missing.”
- Alignment plan or decision needed: Change the utility to raise on wrong types and update tests to enforce the contract.

## Acceptance Criteria

- Accessing a dotted path with a non-dict intermediate raises a clear exception.
- `tests/plugins/test_utils.py` reflects the new behavior.
- A `field_mapper` regression test confirms type mismatches are not silently skipped.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_utils.py -v`
- New tests required: yes, add a `field_mapper` test for non-dict intermediates on dotted mappings.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:81`, `CLAUDE.md:86`, `CLAUDE.md:918`, `CLAUDE.md:920`
