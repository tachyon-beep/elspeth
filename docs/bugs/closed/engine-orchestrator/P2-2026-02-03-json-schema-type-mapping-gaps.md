# Bug Report: JSON schema type mapping gaps in reconstruct_schema_from_json

## Summary

- The `_json_schema_to_python_type` function in `export.py` has incomplete support for Pydantic JSON schema patterns, causing crashes or type degradation when resuming pipelines.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Claude Opus 4.5
- Date: 2026-02-03
- Related run/issue ID: elspeth-rapid-hg2g (beads)

## Environment

- Commit/branch: RC2.1
- OS: Linux
- Python version: 3.12
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline with nullable fields, nested models, or date/time types

## Steps To Reproduce

1. Create a source schema with nullable fields: `name: str | None`
2. Run a pipeline until checkpoint
3. Attempt to resume the pipeline
4. Observe crash in `reconstruct_schema_from_json`

## Expected Behavior

- All Pydantic JSON schema patterns should reconstruct correctly
- Resume should work for any valid source schema

## Actual Behavior

- Nullable types crash: `{"anyOf": [{"type": "string"}, {"type": "null"}]}` → ValueError
- Union types crash: `{"anyOf": [{"type": "integer"}, {"type": "string"}]}` → ValueError
- $ref references crash: `{"$ref": "#/$defs/SomeModel"}` → ValueError
- date, time, UUID types degrade to `str` (lossy but doesn't crash)

## Evidence

- File: `src/elspeth/engine/orchestrator/export.py:227-306`
- The function only handles `anyOf` pattern for Decimal (number+string subset)
- No handling for `$ref` patterns used by nested Pydantic models
- Only `date-time` format recognized, not `date`, `time`, `duration`, `uuid`

Test script confirming behavior:
```python
from elspeth.engine.orchestrator.export import _json_schema_to_python_type

# These crash
_json_schema_to_python_type('x', {'anyOf': [{'type': 'string'}, {'type': 'null'}]})
_json_schema_to_python_type('x', {'$ref': '#/$defs/Model'})

# These degrade to str
_json_schema_to_python_type('x', {'type': 'string', 'format': 'date'})  # Returns str, not date
_json_schema_to_python_type('x', {'type': 'string', 'format': 'uuid'})  # Returns str, not UUID
```

## Impact

- User-facing impact: Cannot resume pipelines with common schema patterns (nullable fields are extremely common)
- Data integrity / security impact: Type fidelity loss for date/time/UUID fields (audit trail shows `str` instead of actual type)
- Performance or cost impact: Resume failures require pipeline restart from beginning

## Root Cause Hypothesis

- Pre-existing gaps in original orchestrator code (confirmed in commit 48c5913a extraction)
- The function was written to handle a subset of Pydantic patterns, not the full JSON Schema spec
- No tests exist for this functionality, so gaps went unnoticed

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/orchestrator/export.py`: Extend `_json_schema_to_python_type` to handle:
    1. `anyOf` with `null` type → `Optional[T]`
    2. `$ref` patterns → recursive lookup in `$defs`
    3. Additional format handlers: date, time, duration, uuid, binary
- Config or schema changes: None
- Tests to add/update:
  - `tests/unit/engine/test_export.py` (new file)
  - Cover all Pydantic type emission patterns
- Risks or migration steps:
  - Low risk: purely additive changes to support more patterns
  - No migration needed: existing supported patterns unchanged

## Acceptance Criteria

- Nullable fields (`str | None`, `Optional[int]`) reconstruct correctly
- Nested Pydantic models with `$ref` reconstruct correctly
- date, time, timedelta, UUID, bytes fields reconstruct with correct types
- Comprehensive test coverage for all Pydantic JSON schema patterns

## Tests

- Suggested tests to run: `pytest tests/unit/engine/test_export.py -v` (after creating)
- New tests required: yes (no tests currently exist for schema reconstruction)

## Notes / Links

- Related issues/PRs: elspeth-rapid-hg2g (beads issue)
- Related docs: Pydantic JSON Schema documentation
- Pre-existing bug discovered during orchestrator refactoring (extracted in commit 48c5913a)
