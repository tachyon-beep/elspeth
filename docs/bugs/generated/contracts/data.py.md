# Bug Report: Schema compatibility allows int→float coercion even when consumer schema is strict

## Summary

- `check_compatibility()` treats `int` as compatible with `float` unconditionally, so pipelines with strict consumer schemas pass DAG validation but fail at runtime when strict validation rejects the `int`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/P2-aggregation-metadata-hardcoded @ 1f10763eed654bee9c12cd7f935428db1280e13c
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Minimal in-memory schema definitions (no dataset)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/data.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Define a producer schema with `x: int` and a consumer schema with `x: float` and `model_config = ConfigDict(strict=True)` (or use `create_schema_from_config(..., allow_coercion=False)` for the consumer).
2. Call `check_compatibility(Producer, Consumer)` and observe `compatible=True`.
3. Validate a producer row like `{"x": 1}` against the strict consumer schema (`Consumer.model_validate(...)`) and observe a `ValidationError`.

## Expected Behavior

- `check_compatibility()` should report incompatibility (type mismatch) when the consumer schema is strict and the producer provides `int` for a `float` field.

## Actual Behavior

- `check_compatibility()` returns compatible because `_types_compatible()` always allows `int -> float`, even when the consumer schema is strict, leading to runtime validation failures.

## Evidence

- `check_compatibility()` never inspects consumer strictness and relies on `_types_compatible()` for type compatibility. `src/elspeth/contracts/data.py:156-179`.
- `_types_compatible()` unconditionally accepts `int` as compatible with `float`. `src/elspeth/contracts/data.py:225-245`.
- Strictness is explicitly used to disable coercion for transforms/sinks via `allow_coercion=False` -> `strict=True`. `src/elspeth/plugins/schema_factory.py:6-8`, `src/elspeth/plugins/schema_factory.py:120-132`.

## Impact

- User-facing impact: Pipelines that should be rejected at config/DAG validation pass, then crash at runtime during strict input validation in transforms/sinks.
- Data integrity / security impact: None directly; failure is loud, but validation happens too late.
- Performance or cost impact: Wasted pipeline execution and retries before failure.

## Root Cause Hypothesis

- `_types_compatible()` hardcodes numeric coercion without checking consumer schema strictness, so `check_compatibility()` permits coercion even when the consumer schema explicitly disallows it.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/data.py`: Pass consumer strictness into `_types_compatible()` (or read `consumer_schema.model_config["strict"]` in `check_compatibility`) and only allow numeric coercion when strict is `False`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test in `tests/plugins/test_schemas.py` asserting `check_compatibility()` returns incompatible when consumer schema has `strict=True` and producer uses `int` for `float`.
  - Add a test using `create_schema_from_config(..., allow_coercion=False)` to ensure DAG validation aligns with strictness.
- Risks or migration steps:
  - Existing pipelines relying on implicit `int -> float` coercion with strict consumer schemas will now be rejected at validation time; update those schemas or producer types accordingly.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L187-L194` (Coercion Rules by Plugin Type: transforms/sinks must not coerce)
- Observed divergence: Compatibility checks allow coercion even when the consumer is strict, which contradicts “no coercion” for transforms/sinks.
- Reason (if known): `_types_compatible()` is type-only and doesn’t factor in consumer strictness.
- Alignment plan or decision needed: Update compatibility logic to respect strictness so DAG validation matches runtime validation semantics.

## Acceptance Criteria

- `check_compatibility()` reports incompatibility for producer `int` vs consumer `float` when consumer strictness is enabled.
- Added tests cover strict consumer coercion behavior and pass.
- No change in behavior for non-strict consumer schemas (int->float remains compatible).

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_schemas.py -k strict`
- New tests required: yes, add strict consumer coercion mismatch case

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Data Manifesto / Coercion Rules)
