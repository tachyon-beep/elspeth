## Summary

Optional MCP arguments that the server itself treats as nullable are published with non-null JSON Schema types, so the MCP framework rejects valid `null` inputs before ELSPETH’s own validator can handle them.

## Severity

- Severity: major
- Priority: P2

## Location

- File: [src/elspeth/mcp/server.py](/home/john/elspeth/src/elspeth/mcp/server.py)
- Line(s): 87-94, 149-152, 203-207, 275-277, 397-448, 466-503
- Function/Method: `_TOOLS`, `_validate_tool_args`, `create_server.call_tool`

## Evidence

In the tool registry, optional fields are declared as plain `"string"` or `"object"` in the MCP `inputSchema`, for example `list_runs.status` at [src/elspeth/mcp/server.py#L87](/home/john/elspeth/src/elspeth/mcp/server.py#L87), `explain_token.token_id/row_id/sink` at [src/elspeth/mcp/server.py#L203](/home/john/elspeth/src/elspeth/mcp/server.py#L203), and `query.params` at [src/elspeth/mcp/server.py#L275](/home/john/elspeth/src/elspeth/mcp/server.py#L275).

But ELSPETH’s own argument validator explicitly accepts `None` for those same fields:
```python
for fname in spec.optional_str:
    val = arguments.get(fname)
    if val is not None and not isinstance(val, str):
        raise TypeError(...)
```
from [src/elspeth/mcp/server.py#L423](/home/john/elspeth/src/elspeth/mcp/server.py#L423), and similarly for optional dicts at [src/elspeth/mcp/server.py#L444](/home/john/elspeth/src/elspeth/mcp/server.py#L444).

The MCP framework validates against `inputSchema` before calling this validator:
- [site-packages/mcp/server/lowlevel/server.py#L524](/home/john/elspeth/.venv/lib/python3.13/site-packages/mcp/server/lowlevel/server.py#L524)
- [site-packages/mcp/server/lowlevel/server.py#L530](/home/john/elspeth/.venv/lib/python3.13/site-packages/mcp/server/lowlevel/server.py#L530)

So a request like `{"status": null}` fails in the MCP layer even though `_validate_tool_args()` would accept it. The intended behavior is also codified in tests:
- [tests/unit/mcp/test_arg_validation.py#L44](/home/john/elspeth/tests/unit/mcp/test_arg_validation.py#L44) expects `list_runs.status=None` to be valid
- [tests/unit/mcp/test_arg_validation.py#L117](/home/john/elspeth/tests/unit/mcp/test_arg_validation.py#L117) expects `query.params=None` to be valid

What the code does: publishes schemas that forbid `null`.
What it should do: publish schemas that match the validator and accept `null` for nullable optionals.

## Root Cause Hypothesis

The module has two separate contracts for the same arguments: the hand-written MCP JSON Schema in `_TOOLS.schema_properties`, and the runtime validator in `_validate_tool_args()`. They drifted apart, and only the runtime validator was updated to treat optional fields as nullable.

## Suggested Fix

Make nullable optionals explicitly nullable in `schema_properties`, e.g.:
```python
"status": {
    "type": ["string", "null"],
    "description": "Filter by status",
    "enum": [s.value for s in RunStatus] + [None],
}
```
and
```python
"params": {"type": ["object", "null"], "description": "Optional query parameters"}
```
Apply the same fix to every `optional_str` and `optional_dict` field so the advertised schema and `_validate_tool_args()` stay aligned.

## Impact

MCP clients that serialize omitted optionals as `null` cannot call these tools successfully. This is a protocol/contract violation in the target file: the server advertises one input contract while implementing another, causing legitimate requests to fail before analysis even begins.
---
## Summary

Pagination arguments accept negative integers, and those values are forwarded straight into SQL `LIMIT`/`OFFSET`, which lets callers bypass the server’s stated result caps and can turn bounded inspection tools into unbounded table scans.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: [src/elspeth/mcp/server.py](/home/john/elspeth/src/elspeth/mcp/server.py)
- Line(s): 80, 124, 133-134, 142, 160, 215, 238, 336, 383, 435-442
- Function/Method: `_validate_tool_args`

## Evidence

Integer validation only checks type:
```python
for fname, int_default in spec.optional_int:
    val = arguments.get(fname, int_default)
    if isinstance(val, float) and val == int(val):
        val = int(val)
    if not isinstance(val, int) or isinstance(val, bool):
        raise TypeError(...)
    validated[fname] = val
```
from [src/elspeth/mcp/server.py#L435](/home/john/elspeth/src/elspeth/mcp/server.py#L435).

There is no lower-bound check for `limit`, `offset`, or `minutes`, even though these fields are described as bounded pagination/report controls in the registry, e.g. `list_rows.limit/offset` at [src/elspeth/mcp/server.py#L131](/home/john/elspeth/src/elspeth/mcp/server.py#L131).

Those values are passed straight through to SQL queries, for example:
- [src/elspeth/mcp/server.py#L126](/home/john/elspeth/src/elspeth/mcp/server.py#L126) forwards `limit` and `offset`
- [src/elspeth/mcp/analyzers/queries.py#L113](/home/john/elspeth/src/elspeth/mcp/analyzers/queries.py#L113) uses `.limit(limit).offset(offset)`
- [src/elspeth/mcp/analyzers/queries.py#L52](/home/john/elspeth/src/elspeth/mcp/analyzers/queries.py#L52), [src/elspeth/mcp/analyzers/queries.py#L173](/home/john/elspeth/src/elspeth/mcp/analyzers/queries.py#L173), and [src/elspeth/mcp/analyzers/queries.py#L473](/home/john/elspeth/src/elspeth/mcp/analyzers/queries.py#L473) do the same for other tools

I verified locally that SQLite treats negative bounds permissively: `LIMIT -1` returned all rows, and `OFFSET -1` behaved like `OFFSET 0`. The existing tests only cover type errors and bool rejection, not negative values:
- [tests/unit/mcp/test_arg_validation.py#L77](/home/john/elspeth/tests/unit/mcp/test_arg_validation.py#L77)

What the code does: accepts any integer, including negative pagination values.
What it should do: reject negative `limit`/`offset` values at the MCP boundary.

## Root Cause Hypothesis

The validator was written as a type gate, not a semantic validator. Because the tool registry centralizes defaults but not numeric constraints, no tool-specific minimums are enforced before the values reach SQLAlchemy.

## Suggested Fix

Add per-argument bounds to `_ArgSpec` or a dedicated numeric constraint field, then reject invalid values in `_validate_tool_args()`. At minimum:
- `limit >= 0` or preferably `limit > 0`
- `offset >= 0`
- `minutes > 0`

Example:
```python
if fname in {"limit", "offset"} and val < 0:
    raise ValueError(f"'{name}': '{fname}' must be >= 0")
```

## Impact

A caller can bypass intended pagination and force large result sets from audit tables such as runs, rows, tokens, operations, errors, and node states. On large audit databases that increases latency and memory pressure, and it weakens the server’s resource-safety guarantees for interactive debugging.
