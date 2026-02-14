# MCP Server Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/mcp/` (4 findings from static analysis)
**Source code reviewed:** `server.py`, `analyzers/queries.py`

## Summary

| # | Bug | Original | Triaged | Verdict |
|---|-----|----------|---------|---------|
| 1 | call_tool returns success for errors | P1 | **P2 downgrade** | SDK validates first; error text in success envelope |
| 2 | get_errors accepts invalid error_type | P1 | **P2 downgrade** | SDK schema prevents reaching handler |
| 3 | eager import of optional mcp dep | P1 | **P1 confirmed** | Breaks imports for non-MCP users |
| 4 | list_runs missing "interrupted" status | P2 | **P2 confirmed** | Real schema drift from RunStatus enum |

## Cross-Cutting Observations

1. **MCP SDK schema validation layer**: The SDK validates tool inputs against jsonschema
   before handlers run (`.venv/.../mcp/server/lowlevel/server.py:530`). This makes
   handler-level validation gaps (bugs 1, 2) defense-in-depth issues rather than
   reachable bugs. Bug 4 is different — the schema itself is wrong.

2. **Schema drift pattern**: Bug 4 shows hardcoded enums drifting from canonical enum
   definitions. Fix: generate tool schema enums from `RunStatus` values to prevent
   future drift.
