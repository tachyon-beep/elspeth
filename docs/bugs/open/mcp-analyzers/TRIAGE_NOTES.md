# MCP Analyzers Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/mcp-analyzers/` (9 findings from static analysis)
**Source code reviewed:** `contracts.py`, `reports.py`, `diagnostics.py`, `queries.py`

## Summary

| # | Bug | Original | Triaged | Verdict |
|---|-----|----------|---------|---------|
| 1 | explain_field wrong field on name collision | P1 | **P3 downgrade** | Extremely niche collision scenario |
| 2 | Mermaid non-unique IDs via truncation | P1 | **P1 confirmed** | Produces structurally wrong DAG diagrams |
| 3 | is_terminal as int not bool | P1 | **P2 downgrade** | Contract drift; calculations correct |
| 4 | performance report truncates node_id | P1 | **P3 downgrade** | Intentional display pattern |
| 5 | avg duration 0.0 as missing | P2 | **P2 confirmed** | Known truthiness pattern |
| 6 | LIMIT without ORDER BY | P2 | **P2 confirmed** | Nondeterministic validation error samples |
| 7 | plugin can be null | P2 | **P2 confirmed** | Contract type mismatch from outer join |
| 8 | get_node_states missing attempt ordering | P2 | **P2 confirmed** | Core recorder already fixed; MCP didn't pick up fix |
| 9 | list_contract_violations masks corruption | P2 | **P3 downgrade** | datetime always truthy; read-only path |

## Cross-Cutting Observations

1. **Node ID truncation has two outcomes**: Bug 2 (Mermaid [:8]) is genuinely broken because
   Mermaid requires unique identifiers and all transform nodes collide on "transfor". Bug 4
   (performance [:12]) is an intentional display pattern with plugin name disambiguation.

2. **Truthiness vs `is not None`**: Bug 5 is a real problem (0.0 is falsy). Bug 9 is a
   false alarm (datetime objects are always truthy in Python).

3. **Core recorder fixes not propagated to MCP**: Bug 8 shows that the retry-ordering fix
   already applied to `_query_methods.py` was not mirrored in the MCP analyzer's
   `queries.py`. Future fixes should audit both query paths.

4. **Outer join null handling**: Bug 7 shows a pattern where `outerjoin` to the nodes table
   produces NULL plugin_name. The fix already exists as `row.plugin_name or "unknown"` in
   `reports.py` but wasn't applied in `diagnostics.py`.
