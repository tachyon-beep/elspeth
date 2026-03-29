## Summary

`FailureValidationError.plugin` is typed as always-present `str`, but `get_failure_context()` can legitimately return `None` for that field, so `src/elspeth/mcp/types.py` publishes a false MCP contract for failure-context responses.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/mcp/types.py`
- Line(s): 429-434
- Function/Method: `FailureValidationError`

## Evidence

`FailureValidationError` currently requires `plugin: str`:

```python
class FailureValidationError(TypedDict):
    """A validation error in failure context."""

    plugin: str
    row_hash: str | None
    sample_data: dict[str, Any] | None
```

Source: `/home/john/elspeth/src/elspeth/mcp/types.py:429-434`

But the producer explicitly preserves `None` instead of fabricating a plugin name:

```python
if e.node_id is not None and e.plugin_name is None:
    ...
    raise RuntimeError(msg)
plugin = e.plugin_name  # None means no associated plugin node — don't fabricate "unknown"
validation_error_list.append(
    {
        "plugin": plugin,
        "row_hash": e.row_hash[:12] + "..." if e.row_hash else None,
        "sample_data": json.loads(e.row_data_json) if e.row_data_json else None,
    }
)
```

Source: `/home/john/elspeth/src/elspeth/mcp/analyzers/diagnostics.py:331-344`

That `None` case is reachable because the schema allows validation errors with no `node_id`:

```python
Column("node_id", String(64)),  # Source node where validation failed (nullable)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/schema.py:414`

And the recorder API also accepts `node_id: str | None`:

```python
def record_validation_error(
    self,
    run_id: str,
    node_id: str | None,
    ...
) -> str:
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/recorder.py:969-985`

So the actual behavior is “`plugin` may be `None` when the validation error is not associated with a node,” while the public type says “always a string.”

## Root Cause Hypothesis

`types.py` modeled the happy-path shape of failure-context data and drifted away from the analyzer’s real semantics. The analyzer intentionally avoids fabricating provenance, but the TypedDict was not updated to reflect that nullable contract.

## Suggested Fix

Change the field type to match the producer:

```python
class FailureValidationError(TypedDict):
    """A validation error in failure context."""

    plugin: str | None
    row_hash: str | None
    sample_data: dict[str, Any] | None
```

A follow-up unit test should cover a validation error recorded with `node_id=None` and assert that `get_failure_context()` returns `"plugin": None`.

## Impact

Any MCP consumer that trusts this type and does string-only operations on `validation_errors[*]["plugin"]` can crash or mishandle failure reports when a validation error lacks node provenance. It also weakens protocol checking in this subsystem: the false type contract hides a real response shape from static analysis, which is exactly the kind of analyzer drift this file is supposed to prevent.
