# Bug Report: PipelineRow `__contains__` Misreports Extras Allowed by `__getitem__`

## Summary

- `PipelineRow.__getitem__` explicitly allows access to extra fields in `FLEXIBLE`/`OBSERVED` modes, but `PipelineRow.__contains__` returns `False` for those same fields, breaking membership checks and dict-like consistency.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `1c70074ef3b71e4fe85d4f926e52afeca50197ab` on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/contracts/schema_contract.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `SchemaContract` in `FLEXIBLE` mode with at least one declared field.
2. Create a `PipelineRow` containing an extra key not present in the contract.
3. Observe `row["extra"]` succeeds but `"extra" in row` evaluates to `False`.

## Expected Behavior

- Membership checks should align with access semantics: if `row["extra"]` is allowed in `FLEXIBLE`/`OBSERVED`, then `"extra" in row` should return `True`.

## Actual Behavior

- `__contains__` returns `False` for extra fields even though `__getitem__` returns their values in `FLEXIBLE`/`OBSERVED` modes.

## Evidence

- `PipelineRow.__getitem__` explicitly allows extra fields in `FLEXIBLE`/`OBSERVED` modes. `src/elspeth/contracts/schema_contract.py:530-538`
- `PipelineRow.__contains__` rejects any field not in the contract, even when extras are allowed. `src/elspeth/contracts/schema_contract.py:560-588`
- `SchemaContract.validate` only rejects extras in `FIXED` mode, so extras are valid for `FLEXIBLE`/`OBSERVED`. `src/elspeth/contracts/schema_contract.py:262-273`

## Impact

- User-facing impact: guard patterns like `if "field" in row` silently skip available data, causing incorrect routing/transform logic.
- Data integrity / security impact: incorrect decisions can propagate into the audit trail (wrong branch, missing outputs).
- Performance or cost impact: unnecessary reprocessing or retries if logic depends on membership checks.

## Root Cause Hypothesis

- `__contains__` uses contract-only resolution and never considers the “extras allowed” behavior implemented in `__getitem__`, leading to inconsistent semantics for flexible/observed rows.

## Proposed Fix

- Code changes (modules/files):
  - Update `PipelineRow.__contains__` in `src/elspeth/contracts/schema_contract.py` to mirror `__getitem__` behavior for `FLEXIBLE`/`OBSERVED` modes (return `True` if `key in _data` when contract resolution fails).
  - Update the `__contains__` docstring to match the actual access rules.
- Config or schema changes: N/A
- Tests to add/update:
  - Add a unit test asserting `"extra" in row` is `True` when `row["extra"]` succeeds in `FLEXIBLE`/`OBSERVED`.
  - Add a unit test asserting `"extra" in row` is `False` in `FIXED` mode.
- Risks or migration steps:
  - Low risk; changes only affect membership semantics and align with existing access behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: `__contains__` behavior contradicts `__getitem__` behavior in flexible/observed modes.
- Reason (if known): Unknown
- Alignment plan or decision needed: Decide and document whether extras are accessible via `PipelineRow` in `FLEXIBLE`/`OBSERVED` and enforce consistent behavior.

## Acceptance Criteria

- In `FLEXIBLE`/`OBSERVED` mode, `__contains__` returns `True` for extra fields present in `_data`.
- In `FIXED` mode, `__contains__` returns `False` for any extra field.
- Added tests pass and clearly encode the intended semantics.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_pipeline_row_contains.py -v`
- New tests required: yes, membership semantics for extra fields

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
