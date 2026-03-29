## Summary

`LandscapeAnalyzer.explain_token()` promises a structured `ErrorResult`, but it forwards invalid/ambiguous requests to `lineage.explain()` without handling its `ValueError` paths, so callers can get an uncaught exception instead of MCP-safe error output.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/mcp/analyzer.py`
- Line(s): 96-106
- Function/Method: `LandscapeAnalyzer.explain_token`

## Evidence

`LandscapeAnalyzer.explain_token()` only converts the `None` return into an error dict:

```python
# /home/john/elspeth/src/elspeth/mcp/analyzer.py:96-106
def explain_token(...) -> ExplainTokenResult | ErrorResult:
    result = queries.explain_token(self._db, self._recorder, run_id, token_id=token_id, row_id=row_id, sink=sink)
    if result is None:
        return {"error": "Token or row not found, or no terminal tokens exist yet"}
    return result
```

But the delegated implementation calls the core lineage API, which raises on invalid request shapes instead of returning `None`:

```python
# /home/john/elspeth/src/elspeth/mcp/analyzers/queries.py:341-343
result = explain(recorder, run_id, token_id=token_id, row_id=row_id, sink=sink)
if result is None:
    return None
```

```python
# /home/john/elspeth/src/elspeth/core/landscape/lineage.py:98-99
if token_id is None and row_id is None:
    raise ValueError("Must provide either token_id or row_id")
```

That invalid combination is reachable through the public MCP boundary today. The server validator accepts `explain_token` calls with only `run_id`:

```python
# verified in repo
_validate_tool_args('explain_token', {'run_id': 'r1'})
# => {'run_id': 'r1', 'token_id': None, 'row_id': None, 'sink': None}
```

Supporting code:
- [`/home/john/elspeth/src/elspeth/mcp/server.py:191-208`] defines `token_id`, `row_id`, and `sink` as optional.
- [`/home/john/elspeth/tests/unit/mcp/test_arg_validation.py:165-188`] checks the tool is registered, but there is no regression test for the invalid `run_id`-only case.
- [`/home/john/elspeth/tests/unit/mcp/test_analyzer_queries.py:276-308`] covers only success/`None` cases for the MCP wrapper, not the exception path.

What the code does:
- Accepts a request shape the public surface allows.
- Lets `ValueError` escape from the lower-level lineage layer.

What it should do:
- Normalize user-facing request errors into `{"error": ...}` at the facade boundary, consistent with the method’s declared return type and the other analyzer methods’ error behavior.

## Root Cause Hypothesis

The facade was written as a thin pass-through and only accounted for the delegated function’s `None` result, not its documented exception cases. Because `server.py` does not enforce the cross-field invariant “at least one of `token_id` or `row_id` must be present,” `analyzer.py` becomes the last practical boundary for turning invalid caller input into a structured MCP error, but it currently lacks that guard.

## Suggested Fix

Validate `token_id`/`row_id` in `LandscapeAnalyzer.explain_token()` before delegating, and catch user-input `ValueError` from the lower layer to return `ErrorResult` instead of crashing the tool call.

Example shape:

```python
def explain_token(...) -> ExplainTokenResult | ErrorResult:
    if token_id is None and row_id is None:
        return {"error": "Must provide either token_id or row_id"}

    try:
        result = queries.explain_token(
            self._db, self._recorder, run_id, token_id=token_id, row_id=row_id, sink=sink
        )
    except ValueError as exc:
        return {"error": str(exc)}

    if result is None:
        return {"error": "Token or row not found, or no terminal tokens exist yet"}
    return result
```

Also add a regression test that exercises the facade or MCP path with:
- `run_id` only
- ambiguous `row_id` without `sink`

## Impact

A malformed but schema-valid `explain_token` request can currently fail as an unhandled exception instead of a structured analyzer error. That breaks the MCP tool contract for one of the primary incident-debugging entry points, makes client behavior inconsistent, and can terminate or surface protocol-level failures during analysis sessions instead of returning actionable error text.
