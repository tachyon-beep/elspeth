# Bug Report: SourceRow.valid Allows Missing Contract Despite Engine Requirement

## Summary

- `SourceRow.valid()` accepts `contract=None` and documentation/examples show it as optional, but the engine requires a contract for all valid source rows, causing a runtime crash when a source follows the documented usage.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 3aa2fa93 on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit for `src/elspeth/contracts/results.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a source plugin using the BaseSource or SourceProtocol example that yields `SourceRow.valid(row)` without a contract.
2. Run a pipeline with that source so `TokenManager.create_initial_token()` is invoked.

## Expected Behavior

- Valid source rows must carry a `SchemaContract`; `SourceRow.valid()` should require it (or fail fast at construction with a clear error), and documentation/examples should reflect that.

## Actual Behavior

- `SourceRow.valid()` allows `contract=None`, so a source following the documented example crashes later when the engine tries to create the initial token.

## Evidence

- `src/elspeth/contracts/results.py:463-515` shows `SourceRow.valid()` accepting `contract: SchemaContract | None = None` and examples that omit a contract.
- `src/elspeth/engine/tokens.py:87-89` enforces `source_row.contract is not None` and raises `ValueError` otherwise.
- `src/elspeth/plugins/base.py:388-398` example yields `SourceRow.valid(row)` without a contract.

## Impact

- User-facing impact: New or updated source plugins can crash immediately at run start if they follow the documented usage.
- Data integrity / security impact: None directly, but crashes block ingestion.
- Performance or cost impact: Pipeline aborts, wasted run time.

## Root Cause Hypothesis

- Contract mismatch: `SourceRow.valid()` and docs treat the contract as optional, but engine logic requires a contract for all non-quarantined rows.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/results.py`: make `contract` required in `SourceRow.valid()` and add validation for non-quarantined rows.
  - `src/elspeth/contracts/results.py`: update docstring examples to pass a contract.
  - `src/elspeth/plugins/base.py`: update example to pass a contract.
  - `src/elspeth/plugins/protocols.py`: update example to pass a contract.
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test that `SourceRow.valid()` without a contract raises a clear error.
- Risks or migration steps:
  - Any existing source implementations omitting the contract will fail fast; update them to pass `get_schema_contract()`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Documentation implies a contract is optional, while engine requires it for valid rows.
- Reason (if known): Likely drift between contract API and engine enforcement.
- Alignment plan or decision needed: Make contract mandatory for valid source rows and update examples.

## Acceptance Criteria

- `SourceRow.valid()` requires a contract for non-quarantined rows.
- Documentation/examples consistently pass a contract.
- A source that omits the contract fails immediately with a clear error.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k "SourceRow"`
- New tests required: yes, add a contract-required test for `SourceRow.valid()`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
---
# Bug Report: TransformResult Missing Invariant Checks for Error Status and Reason

## Summary

- `TransformResult.__post_init__()` only validates success results; it does not enforce valid `status` values or require `reason` for error results, enabling invalid results to be routed instead of crashing and potentially recording missing error details.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 3aa2fa93 on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit for `src/elspeth/contracts/results.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In a transform plugin, return `TransformResult(status="error", row=None, reason=None, success_reason=None)` or `TransformResult(status="bogus", ...)`.
2. Run a pipeline with `on_error` configured for that transform.

## Expected Behavior

- Invalid `status` values or error results without a `reason` should raise immediately (plugin bug) so the pipeline crashes instead of routing/recording an invalid result.

## Actual Behavior

- `TransformResult` permits invalid `status` values and missing error reasons; executor logic treats any non-`"success"` status as error and relies on an `assert` to enforce reason presence.

## Evidence

- `src/elspeth/contracts/results.py:126-133` only checks `success_reason` for success; no validation of `status` or error `reason`.
- `src/elspeth/engine/executors.py:449-454` uses an `assert` to enforce error reason; asserts can be stripped with `-O`, allowing missing error details to pass through.

## Impact

- User-facing impact: Invalid transform results may be routed instead of crashing, hiding plugin bugs.
- Data integrity / security impact: Error records can lack required details, violating auditability expectations.
- Performance or cost impact: Potentially wasted processing on invalid results routed downstream.

## Root Cause Hypothesis

- Contract invariants for `TransformResult` are under-enforced in `__post_init__`, relying on downstream assertions instead of fail-fast validation.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/results.py`: add `__post_init__` checks that `status` is exactly `"success"` or `"error"`.
  - `src/elspeth/contracts/results.py`: require `reason` for error results and reject `success_reason` on error results.
- Config or schema changes: None.
- Tests to add/update:
  - Add unit tests that invalid `status` and missing `reason` raise `ValueError`.
- Risks or migration steps:
  - Any transforms constructing invalid `TransformResult` instances will fail fast; update those plugins to use factory methods.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): CLAUDE.md (Plugin bugs must crash, no bug-hiding patterns)
- Observed divergence: Invalid result states can be routed rather than crashing immediately.
- Reason (if known): Validation deferred to executor and guarded by `assert`.
- Alignment plan or decision needed: Enforce invariants in `TransformResult` itself.

## Acceptance Criteria

- `TransformResult` construction fails fast for invalid `status` values.
- Error results always require a non-`None` `reason`.
- Unit tests cover invalid cases and pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k "TransformResult"`
- New tests required: yes, add invariant enforcement tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: CLAUDE.md (Plugin ownership and auditability principles)
