## Summary

`get_performance_report()` truncates `node_id` into a non-canonical display string, making node identity ambiguous and sometimes non-unique.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P1 — intentional display shortening pattern used consistently across MCP analyzers; plugin name alongside provides disambiguation; full node_id available via list_nodes)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/mcp/analyzers/reports.py`
- Line(s): `300`
- Function/Method: `get_performance_report`

## Evidence

`node_id` is emitted as:

```python
"node_id": row.node_id[:12] + "...",
```

But node IDs are canonical identifiers (from DAG builder) and are used for attribution/debug correlation. Truncating them can create collisions across nodes with similar prefixes and prevents exact cross-referencing.

## Root Cause Hypothesis

Human-readable shortening was applied directly to the canonical `node_id` field instead of a separate display field.

## Suggested Fix

Return full `row.node_id` in `node_id`. If short display is desired, add a separate field (e.g., `node_id_short`) and keep canonical identity intact.

## Impact

Performance bottlenecks and failures may be attributed to an ambiguous identifier, weakening audit traceability and making drill-down workflows error-prone.
