## Summary

`list_runs` tool schema excludes valid run status `interrupted`, so valid filters are rejected before reaching analyzer logic.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/mcp/server.py
- Line(s): 205-210
- Function/Method: `list_tools` (tool definition for `list_runs`)

## Evidence

`list_runs` input schema enum is:

```python
"enum": ["running", "completed", "failed"]
```

But valid statuses include `interrupted`:

- `src/elspeth/contracts/enums.py:17-20` (`RunStatus.INTERRUPTED = "interrupted"`)

Analyzer supports full enum validation:

- `src/elspeth/mcp/analyzers/queries.py:55-62` validates via `RunStatus(status)`.

MCP SDK enforces `inputSchema` first:

- `.venv/lib/python3.13/site-packages/mcp/server/lowlevel/server.py:528-532` (`jsonschema.validate`).

So `"interrupted"` is blocked at protocol layer despite being a valid backend value.

## Root Cause Hypothesis

Tool schema enum in `server.py` drifted from canonical `RunStatus` enum and was hardcoded incompletely.

## Suggested Fix

Update `list_runs` `status` enum to include `"interrupted"`, ideally generated from `RunStatus` values in `server.py` to avoid future drift.

## Impact

Operators cannot directly filter interrupted runs through MCP, weakening diagnostics workflows and creating contract mismatch between advertised API behavior and backend capabilities.

## Triage

- Status: open
- Source report: `docs/bugs/generated/mcp/server.py.md`
- Finding index in source report: 2
- Beads: pending
