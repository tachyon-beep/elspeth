## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/plugins/sources/null_source.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sources/null_source.py
- Line(s): 18-88
- Function/Method: Unknown

## Evidence

`NullSource` is intentionally a zero-row source for resume flows, and the surrounding code uses it in a way that avoids the obvious failure modes.

In [/home/john/elspeth/src/elspeth/plugins/sources/null_source.py:18](file:///home/john/elspeth/src/elspeth/plugins/sources/null_source.py#L18), `NullSourceSchema` sets `extra="allow"` with zero fields:

```python
class NullSourceSchema(PluginSchema):
    model_config = ConfigDict(extra="allow")
```

That matches the DAG validator’s observed-schema check in [/home/john/elspeth/src/elspeth/core/dag/graph.py:1233](file:///home/john/elspeth/src/elspeth/core/dag/graph.py#L1233), which treats `len(model_fields) == 0 and model_config["extra"] == "allow"` as observed. This prevents resume graph validation from incorrectly failing against explicit downstream schemas.

In [/home/john/elspeth/src/elspeth/cli.py:1562](file:///home/john/elspeth/src/elspeth/cli.py#L1562) and [/home/john/elspeth/src/elspeth/cli.py:1879](file:///home/john/elspeth/src/elspeth/cli.py#L1879), resume explicitly constructs `NullSource({})` and injects `on_success` from the original source before building/executing the resume graph:

```python
null_source = NullSource({})
null_source.on_success = null_source_on_success
```

That satisfies the source routing contract even though `NullSource` itself has no config model.

The resume path restores row types from the original run’s recorded schema, not from `NullSourceSchema`. [/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:2610](file:///home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L2610) reads the original `source_schema_json` from the recorder, and [/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py:275](file:///home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L275) has a guard that would fail fast if an empty schema like `NullSourceSchema` were mistakenly used to restore non-empty row payloads.

Coverage exists for the key edge case in [/home/john/elspeth/tests/unit/plugins/sources/test_null_source.py:79](file:///home/john/elspeth/tests/unit/plugins/sources/test_null_source.py#L79), which asserts the schema is structurally observed, and [/home/john/elspeth/tests/unit/plugins/sources/test_null_source.py:96](file:///home/john/elspeth/tests/unit/plugins/sources/test_null_source.py#L96), which verifies a resume-like graph with explicit downstream schema validates successfully.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No fix recommended.

## Impact

No confirmed breakage attributable to `/home/john/elspeth/src/elspeth/plugins/sources/null_source.py` was verified. The file appears to satisfy its narrow resume-only role without violating the source contract, schema contract, or audit-trail requirements.
