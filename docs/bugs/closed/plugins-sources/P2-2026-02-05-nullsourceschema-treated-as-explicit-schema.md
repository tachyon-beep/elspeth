# Bug Report: NullSourceSchema Treated as Explicit Schema, Breaking Resume Graph Validation

## Summary

- `NullSourceSchema` inherits `PluginSchema` defaults (`extra="ignore"`) so it is NOT recognized as an observed/dynamic schema, causing resume execution graph validation to fail when downstream input schemas are explicit.

## Status

**CLOSED** - Fixed 2026-02-06

## Severity

- Severity: moderate
- Priority: P2
- Downgrade rationale: Resume validation failure is clear and explicit; no silent data corruption or audit integrity issue

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b4 (branch RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Resume pipeline where first downstream transform has explicit input schema (non-observed)

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/sources/null_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline where the first transform uses an explicit input schema (e.g., `schema` fields set to fixed/flexible or required fields without observed mode).
2. Attempt `elspeth resume ... --execute`, which builds the execution graph with `NullSource` and calls graph validation.

## Expected Behavior

- Resume execution graph validates successfully, even though the source is `NullSource`, because schema compatibility should not block resuming previously valid pipelines.

## Actual Behavior

- Graph validation can fail with a schema compatibility error because `NullSourceSchema` is treated as an explicit schema with zero fields instead of an observed/dynamic schema.

## Evidence

- `NullSourceSchema` is an empty subclass of `PluginSchema` and does not override `model_config`, so it inherits `extra="ignore"` (not observed). `src/elspeth/plugins/sources/null_source.py:17`, `src/elspeth/plugins/sources/null_source.py:43`
- Observed schemas are defined as `len(model_fields) == 0` **and** `model_config["extra"] == "allow"`, which `NullSourceSchema` does not satisfy. `src/elspeth/core/dag.py:983`, `src/elspeth/core/dag.py:987`
- `PluginSchema` defaults set `extra="ignore"`, confirming `NullSourceSchema` is not observed unless overridden. `src/elspeth/contracts/data.py:43`
- The schema factory explicitly defines observed schemas with `extra="allow"`. `src/elspeth/plugins/schema_factory.py:58`, `src/elspeth/plugins/schema_factory.py:83`

## Impact

- User-facing impact: Resume can be blocked for pipelines with explicit input schemas, even though original runs were valid.
- Data integrity / security impact: None directly, but resume becomes unusable for valid pipelines, preventing recovery.
- Performance or cost impact: Increased operational time due to failed resumes and manual intervention.

## Root Cause Hypothesis

- `NullSourceSchema` is meant to be a dynamic/observed schema but inherits `PluginSchema` defaults (`extra="ignore"`), so the DAG validator treats it as an explicit schema and enforces field compatibility against downstream input schemas.

## Fix Applied

**Files changed:**
- `src/elspeth/plugins/sources/null_source.py`: Added `model_config = ConfigDict(extra="allow")` to `NullSourceSchema`

**Code change:**
```python
class NullSourceSchema(PluginSchema):
    """Dynamic/observed schema for NullSource - accepts any row structure.

    CRITICAL: Must set extra="allow" to be recognized as an observed schema.
    The DAG validator checks `len(model_fields) == 0 AND model_config["extra"] == "allow"`
    to identify observed schemas (see dag.py:_is_observed_schema). Without this,
    NullSourceSchema would be treated as an explicit schema with zero fields,
    causing resume graph validation to fail when downstream transforms have
    explicit input schemas.
    """

    model_config = ConfigDict(extra="allow")
```

**Tests added:**
- `tests/plugins/sources/test_null_source.py::test_null_source_schema_is_observed` - Verifies `NullSourceSchema` has `extra="allow"` and no fields (observed schema signature)
- `tests/plugins/sources/test_null_source.py::test_null_source_schema_with_explicit_downstream_schema` - Integration test verifying resume graph validation passes when NullSource precedes a transform with explicit input schema

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/schema_factory.py:58` (observed schemas must use `extra="allow"`).
- Observed divergence: `NullSourceSchema` does not declare `extra="allow"` despite being described as dynamic/observed.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Align `NullSourceSchema` with observed schema semantics by setting `extra="allow"`.

## Acceptance Criteria

- [x] Resume execution graph validation succeeds when downstream transforms use explicit schemas.
- [x] `NullSourceSchema` is recognized as observed/dynamic by DAG validation.
- [x] No regressions in normal (non-resume) execution.

## Tests

- Tests run: `.venv/bin/python -m pytest tests/plugins/sources/test_null_source.py -v` (8 passed)
- New tests added:
  - `test_null_source_schema_is_observed`: Structural check that schema has observed semantics
  - `test_null_source_schema_with_explicit_downstream_schema`: Integration test with resume-like graph

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`
