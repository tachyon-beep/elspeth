# Bug Report: Optional Float Fields Downgrade to `any` in Output Contracts

## Summary

- Optional float fields created via schema config are mapped to `object` in output contracts, so type validation is skipped for those fields.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 3aa2fa93
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: SchemaConfig with optional float field (e.g., `score: float?`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/transform_contract.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a schema with an optional float field via config, e.g., `SchemaConfig(mode="fixed", fields=["score: float?"])` and build it with `create_schema_from_config`.
2. Call `create_output_contract_from_schema` on the resulting schema class.
3. Validate output `{"score": "not-a-float"}` against the contract.

## Expected Behavior

- The contract should record `score` as `float`, and non-float values should produce a type mismatch violation (unless `None`).

## Actual Behavior

- The contract records `score` as `object`, so type validation is skipped and invalid types pass.

## Evidence

- `src/elspeth/contracts/transform_contract.py:45-60` shows `_get_python_type` only recognizes primitives and falls back to `object` for unknown types, including `Annotated` inside `Optional`.
- `src/elspeth/plugins/schema_factory.py:28-36` defines `FiniteFloat` as `Annotated[float, ...]`, and `src/elspeth/plugins/schema_factory.py:145-151` wraps optional fields as `base_type | None`, producing `Optional[Annotated[float, ...]]`.
- `src/elspeth/contracts/schema_contract.py:235-238` skips type validation when `python_type is object`.

## Impact

- User-facing impact: Transform outputs with optional float fields can silently emit non-float values without violations.
- Data integrity / security impact: Violates Tier 2 expectations; incorrect types can propagate into the audit trail and downstream sinks.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `_get_python_type` does not unwrap `typing.Annotated` when it appears inside `Union`/`Optional`, so optional floats become `object` and lose type enforcement.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/contracts/transform_contract.py` `_get_python_type` to unwrap `Annotated` types (including inside unions) before `_TYPE_MAP` checks.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/contracts/test_transform_contract.py` to ensure optional float fields derived from config produce `python_type=float` and reject non-float values.
- Risks or migration steps: Low risk; tighter validation may surface existing invalid data that previously passed.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` Data Manifesto (Tier 2: transforms must not accept wrong types).
- Observed divergence: Optional float fields are treated as `any`, disabling type enforcement.
- Reason (if known): Missing `Annotated` unwrapping logic in `_get_python_type`.
- Alignment plan or decision needed: Implement `Annotated` unwrapping and add regression tests.

## Acceptance Criteria

- Optional float fields in output contracts are recorded as `float`.
- Non-float values for optional float fields yield type mismatch violations.
- Added regression test passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_transform_contract.py`
- New tests required: yes, test optional float contract typing from config-generated schemas.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-02-02-phase3-transform-sink-integration.md`
