## Summary

`ExecutionGraph.get_effective_producer_schema()` suppresses `GraphValidationError` for select-merge branch tracing and silently downgrades to `None`, which disables downstream type validation.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/dag/graph.py`
- Line(s): `1088-1092`, `1023-1028`
- Function/Method: `ExecutionGraph.get_effective_producer_schema` (impact materializes in `_validate_single_edge`)

## Evidence

`get_effective_producer_schema()` catches and suppresses branch-trace failures:

```python
try:
    _first, last = self._trace_branch_endpoints(NodeID(node_id), select_branch)
    return self.get_effective_producer_schema(last)
except GraphValidationError:
    pass  # Fall through to None if trace fails
```

Source: `/home/john/elspeth-rapid/src/elspeth/core/dag/graph.py:1088`

`_validate_single_edge()` treats `None` producer schema as dynamic and exits early:

```python
producer_schema = self.get_effective_producer_schema(from_node_id)
...
if producer_schema is None or consumer_schema is None:
    return
```

Source: `/home/john/elspeth-rapid/src/elspeth/core/dag/graph.py:1023`

So a coalesce select branch-trace failure is converted into "compatible with anything," hiding a graph-construction bug instead of failing fast. The tier-model allowlist also explicitly notes this fallback "skips type validation": `/home/john/elspeth-rapid/config/cicd/enforce_tier_model/core.yaml:347`.

## Root Cause Hypothesis

A defensive fallback was added for select-merge traceability edge cases, but it violates Tier-1 fail-fast expectations by converting internal invariants into dynamic-schema bypass behavior.

## Suggested Fix

Fail closed instead of degrading to `None`:

- Require `select_branch` directly from config (validated upstream).
- If `_trace_branch_endpoints()` fails, raise `GraphValidationError` with node/branch context.
- Remove the silent `except ...: pass` path.

## Impact

Graph/schema contract defects at coalesce-select boundaries can pass validation and surface later as runtime misrouting/type failures, weakening pre-run contract enforcement and audit confidence.
