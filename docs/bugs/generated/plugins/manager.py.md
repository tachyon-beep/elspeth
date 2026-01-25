# Bug Report: PluginSpec schema hashes are `None` for config-driven schemas

## Summary

- PluginSpec hashes class-level schemas, but built-in plugins set schemas on instances during `__init__`, so schema hashes end up `None` for config-driven plugins.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/rc1-bug-burndown-session-4 @ 86357898ee109a1dbb8d60f3dc687983fa22c1f0
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `src/elspeth/plugins/manager.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate a config-driven plugin like `FieldMapper` with a valid `schema` config.
2. Observe `FieldMapper.input_schema`/`output_schema` are set on the instance (not the class).
3. Call `PluginSpec.from_plugin(FieldMapper, NodeType.TRANSFORM)` and observe schema hashes are `None`.

## Expected Behavior

- Schema hashes should reflect the actual schemas used by plugin instances for a run/configuration.

## Actual Behavior

- Schema hashes are computed from class-level attributes and can be `None` for config-driven plugins.

## Evidence

- `PluginSpec.from_plugin` reads schemas from the class via `getattr(...)`: `src/elspeth/plugins/manager.py:92`
- `PluginSpec.from_plugin` hashes those class-level schemas: `src/elspeth/plugins/manager.py:102`
- Built-in transforms set schemas on the instance in `__init__`: `src/elspeth/plugins/transforms/field_mapper.py:67`
- Built-in sources set `output_schema` on the instance: `src/elspeth/plugins/sources/csv_source.py:77`
- Built-in sinks set `input_schema` on the instance: `src/elspeth/plugins/sinks/csv_sink.py:89`

## Impact

- User-facing impact: Low today (PluginSpec is not used in runtime paths), but will surface once schema hashes are recorded in node metadata.
- Data integrity / security impact: Missing schema hashes weaken auditability and compatibility/change detection guarantees.
- Performance or cost impact: Low (future debugging/repro effort increases).

## Root Cause Hypothesis

- PluginSpec assumes static class-level schemas, but the system uses config-driven, instance-level schema generation.

## Proposed Fix

- Code changes (modules/files):
  - Update `PluginSpec` to accept plugin instances (or schemas directly) so hashes reflect actual instance schemas: `src/elspeth/plugins/manager.py`
  - Alternatively, hash `schema_config` deterministically and store that as the schema fingerprint.
- Config or schema changes: none
- Tests to add/update:
  - Add a test that `PluginSpec` returns non-None schema hashes for config-driven plugins like `FieldMapper`, `CSVSource`, and `CSVSink`.
- Risks or migration steps:
  - If changing method signatures, introduce a new `from_instance(...)` and update call sites to avoid breaking API.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `USER_MANUAL.md:771`
- Observed divergence: Node records are expected to include schema hashes, but `PluginSpec.from_plugin` can yield `None` for built-in, config-driven plugins.
- Reason (if known): Schema generation moved to instance construction; PluginSpec stayed class-based.
- Alignment plan or decision needed: Decide the canonical schema identity source (instance Pydantic model vs `schema_config` hash) and update PluginSpec accordingly.

## Acceptance Criteria

- `PluginSpec` returns non-None, stable schema hashes for config-driven plugins (e.g., `FieldMapper`, `CSVSource`, `CSVSink`) when instantiated with valid configs.
- Tests cover config-driven schema hashing and fail if hashes regress to `None`.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_manager.py`
- New tests required: yes, add config-driven plugin cases for schema hash coverage

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `USER_MANUAL.md:771`
