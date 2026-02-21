## Summary

`get_failure_context()` can return `validation_errors[].plugin = null`, violating the declared `FailureContextReport` contract (`plugin: str`) and leaking nullable internals to MCP clients.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/mcp/analyzers/diagnostics.py`
- Line(s): 283-296, 320-326
- Function/Method: `get_failure_context`

## Evidence

`get_failure_context()` does an outer join to `nodes` and directly forwards `plugin_name`:

```python
# diagnostics.py
.outerjoin(
    nodes_table,
    (validation_errors_table.c.node_id == nodes_table.c.node_id) & (validation_errors_table.c.run_id == nodes_table.c.run_id),
)
...
"plugin": e.plugin_name,
```

But the return type requires a string:

- `src/elspeth/mcp/types.py:475-480` (`FailureValidationError.plugin: str`)

And `validation_errors.node_id` is nullable by schema:

- `src/elspeth/core/landscape/schema.py:407` (`Column("node_id", String(64)),  # nullable`)
- `src/elspeth/core/landscape/_error_recording.py:46-50` accepts `node_id: str | None`

Repro (executed in repo): inserting a validation error with `node_id=None` and calling `get_failure_context()` returned:

- `{'plugin': None, ...}`

So actual output can violate declared schema.

## Root Cause Hypothesis

The function assumes `plugin_name` is always present, but the upstream table design explicitly allows validation errors without a `node_id`, so `outerjoin` can produce `NULL` plugin names.

## Suggested Fix

Normalize plugin names for the nullable-node case while still failing loudly on true corruption:

- If `validation_errors.node_id is None` and `plugin_name is None`, emit `"unknown"` (or similar explicit sentinel string).
- If `validation_errors.node_id is not None` but `plugin_name is None`, raise (Tier 1 corruption signal).

## Impact

Contract/schema mismatch at MCP boundary can break consumers that expect `plugin` to always be a string and weakens failure-attribution quality in diagnostics output.

## Triage

- Status: open
- Source report: `docs/bugs/generated/mcp/analyzers/diagnostics.py.md`
- Finding index in source report: 1
- Beads: pending
