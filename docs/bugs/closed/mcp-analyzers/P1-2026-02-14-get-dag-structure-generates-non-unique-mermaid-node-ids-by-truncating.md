## Summary

`get_dag_structure()` generates non-unique Mermaid node IDs by truncating `node_id` to 8 characters, which collapses multiple nodes into one visual node.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/mcp/analyzers/reports.py`
- Line(s): `214`, `222`
- Function/Method: `get_dag_structure`

## Evidence

`reports.py` builds Mermaid IDs with truncated prefixes:

```python
lines.append(f'    {n.node_id[:8]}["{label}"]')   # line 214
...
lines.append(f"    {e.from_node_id[:8]} {arrow} {e.to_node_id[:8]}")  # line 222
```

Node IDs are deterministic strings prefixed by node type/name (`builder.py`):

```python
generated = f"{prefix}_{name}_{config_hash}_{sequence}"  # line 134
```

For transform nodes, IDs begin with `"transform_"`, so the first 8 chars are always `"transfor"`. That makes Mermaid IDs collide for common multi-transform DAGs, producing incorrect graphs.

## Root Cause Hypothesis

A display-shortening optimization (`[:8]`) was applied to Mermaid identifiers, but Mermaid requires unique node identifiers. Prefix truncation destroys uniqueness.

## Suggested Fix

Use stable unique aliases (or full IDs) for Mermaid identifiers, and keep truncation only in labels if needed.

Example approach:

```python
alias = {n.node_id: f"n{i}" for i, n in enumerate(nodes)}
lines.append(f'    {alias[n.node_id]}["{label}"]')
lines.append(f"    {alias[e.from_node_id]} {arrow} {alias[e.to_node_id]}")
```

## Impact

DAG visualizations can be structurally wrong, causing investigators to see incorrect paths/edges and misdiagnose routing behavior.
