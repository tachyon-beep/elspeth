# Bug Report: RowDataResult allows invalid state values and non-dict payloads without crashing

## Summary

- RowDataResult only enforces None/non-None invariants and does not validate that `state` is a RowDataState or that `data` is a dict in AVAILABLE state, allowing invalid internal audit data to pass silently.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A (direct RowDataResult construction)

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/landscape/row_data.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In a Python shell, run:
   `RowDataResult(state="available", data={"k": "v"})`
2. Observe that no exception is raised and `state` is a plain string.
3. In a Python shell, run:
   `RowDataResult(state=RowDataState.AVAILABLE, data=["not", "a", "dict"])`
4. Observe that no exception is raised even though `data` is not a dict.

## Expected Behavior

- RowDataResult should crash if `state` is not a RowDataState enum member or if `data` is not a dict when state is AVAILABLE, per Tier-1 trust rules (invalid enum value or wrong type should be fatal).

## Actual Behavior

- RowDataResult accepts non-enum `state` values (e.g., raw strings) and non-dict payloads for AVAILABLE state without raising, allowing invalid internal audit data to propagate.

## Evidence

- `row_data.py:21-31` defines RowDataState as `str, Enum`, so equality with raw strings is True.
- `row_data.py:56-60` only checks None vs non-None; it does not validate `state` type or `data` type.
- `CLAUDE.md:34-41` requires Tier 1 data to crash on wrong types or invalid enum values.

## Impact

- User-facing impact: Potentially misleading state handling (e.g., match/case may treat invalid string states as valid).
- Data integrity / security impact: Violates Tier-1 “crash on anomalies” rule; corrupted or malformed audit payloads can be treated as valid.
- Performance or cost impact: Low direct impact; indirect costs from undetected data corruption.

## Root Cause Hypothesis

- RowDataResult lacks strict runtime validation for `state` and `data` types; `RowDataState` inherits from `str`, so invalid raw strings can pass state checks and be treated as valid.

## Proposed Fix

- Code changes (modules/files):
  - `/home/john/elspeth-rapid/src/elspeth/core/landscape/row_data.py`: In `RowDataResult.__post_init__`, enforce `state` is a RowDataState and (when AVAILABLE) `data` is a dict; raise TypeError/ValueError otherwise.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests rejecting non-enum `state` values (e.g., "available") and non-dict `data` in AVAILABLE state in `tests/core/landscape/test_row_data.py`.
- Risks or migration steps:
  - Existing callers constructing RowDataResult with raw strings will now crash; update those call sites to use RowDataState constants.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:34-41`
- Observed divergence: Invalid enum values and wrong payload types do not crash.
- Reason (if known): Missing runtime validation in RowDataResult.
- Alignment plan or decision needed: Enforce strict enum/type validation at RowDataResult construction.

## Acceptance Criteria

- RowDataResult raises an exception when `state` is not a RowDataState.
- RowDataResult raises an exception when `state` is AVAILABLE and `data` is not a dict.
- Tests cover both invalid state and invalid data type cases.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_row_data.py`
- New tests required: yes, add validation tests for invalid state and invalid data type.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier-1 trust rules)
