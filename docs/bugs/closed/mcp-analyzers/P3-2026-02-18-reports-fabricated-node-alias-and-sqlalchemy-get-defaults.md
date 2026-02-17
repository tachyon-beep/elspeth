## Summary

`generate_mermaid_dag()` in `reports.py` uses `.get()` with fabricated fallbacks on Tier 1 data in two patterns: (1) node alias lookup falls back to truncated node ID for orphan edges, hiding Landscape data inconsistency; (2) SQLAlchemy inspector output uses `.get("nullable", True)` and `.get("constrained_columns", [])` despite these keys being guaranteed by the API.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/mcp/analyzers/reports.py`
- Lines: 221-222, 591, 597
- Functions: `generate_mermaid_dag()`, `get_database_schema()`

## Evidence

**Node alias (lines 221-222):**
- `node_alias` is built from `{n.node_id: f"N{i}" for ...}` for all nodes in the run
- Every edge's `from_node_id` and `to_node_id` should reference nodes in the same run
- Fallback `e.from_node_id[:8]` fabricates a display alias and hides the data inconsistency
- Line 217 uses direct access `node_alias[n.node_id]` — edges should be consistent

**SQLAlchemy inspector (lines 591, 597):**
- `inspector.get_columns()` always returns dicts with `nullable` key
- `inspector.get_pk_constraint()` always returns dict with `constrained_columns` key when not None
- Defaulting `nullable` to `True` is dangerous — fabricates permissiveness

## Fix Applied

1. Lines 221-222: Changed to direct `node_alias[e.from_node_id]` / `node_alias[e.to_node_id]`
2. Line 591: Changed `col.get("nullable", True)` to `col["nullable"]`
3. Line 597: Changed `pk.get("constrained_columns", [])` to `pk["constrained_columns"]`

## Impact

Orphan edges in Landscape data now crash with KeyError instead of producing silently wrong Mermaid diagrams. Missing SQLAlchemy column metadata now crashes instead of fabricating nullable=True.
