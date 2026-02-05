# Bug Report: `query()` Read-Only Guard Allows Non-SELECT Operations

## Summary

- The `query()` tool claims to be SELECT-only but only checks the prefix and a short forbidden-keyword list, so non-read-only statements can pass validation (including multi-statement payloads and unblocked commands like `COPY`, `PRAGMA`, `ATTACH`, `VACUUM`, `SET`), violating the “read-only” contract for the MCP analysis server.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074e (branch: RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Audit DB with MCP server enabled

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/mcp/server.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Run the MCP server against a Postgres audit DB.
2. Call the `query` tool with SQL like `SELECT 1; COPY (SELECT * FROM runs) TO '/tmp/runs.csv'` or `SELECT 1; SET ROLE some_role`.
3. The server accepts the query and passes it to the database because it starts with `SELECT` and doesn’t contain the blocked keywords.

## Expected Behavior

- The `query` tool rejects any multi-statement SQL and any non-SELECT/CTE statements, guaranteeing read-only behavior.

## Actual Behavior

- The guard only checks for `SELECT` prefix and a short keyword list, so other stateful statements and multi-statement payloads can pass validation and reach the database.

## Evidence

- `src/elspeth/mcp/server.py:605` shows `query()` implements the SELECT-only tool.
- `src/elspeth/mcp/server.py:618` only checks `startswith("SELECT")`.
- `src/elspeth/mcp/server.py:624` restricts only a small set of keywords, missing common stateful commands.
- `CLAUDE.md:518` states the MCP server provides read-only access, which this implementation can violate.

## Impact

- User-facing impact: The “read-only” analysis server can execute unintended commands.
- Data integrity / security impact: Potential audit DB mutation or unauthorized data exfiltration, depending on backend support for multi-statement execution.
- Performance or cost impact: Possible heavy or destructive operations run through the analysis tool.

## Root Cause Hypothesis

- The SQL guard is implemented as a simple string prefix and keyword blacklist, which does not reliably enforce a single read-only SELECT statement.

## Proposed Fix

- Code changes (modules/files): Strengthen validation in `src/elspeth/mcp/server.py` to parse SQL and allow only a single `SELECT`/`WITH` statement; reject semicolons and unsupported statement types; expand forbidden list if parsing is unavailable.
- Config or schema changes: None.
- Tests to add/update: Add unit tests for `query()` validation covering multi-statement input and non-SELECT statements (`COPY`, `PRAGMA`, `ATTACH`, `VACUUM`, `SET`).
- Risks or migration steps: Ensure any new SQL parser dependency (e.g., `sqlparse`/`sqlglot`) is approved or implement a minimal single-statement validator.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:518`
- Observed divergence: The server can execute non-read-only SQL even though it is documented as read-only.
- Reason (if known): Guard uses a simplistic string check rather than a statement-level validator.
- Alignment plan or decision needed: Enforce read-only semantics in the `query()` tool or use a read-only DB connection/role.

## Acceptance Criteria

- `query()` rejects any SQL with multiple statements or non-SELECT/CTE types.
- Attempted non-read-only queries return a validation error before DB execution.

## Tests

- Suggested tests to run: `python -m pytest tests/mcp/test_server_query_validation.py -k query_read_only`
- New tests required: yes, add validation tests for forbidden statements and multi-statement input.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Landscape MCP Analysis Server section)
---
# Bug Report: `diagnose()` Flags All Running Runs as “Stuck”

## Summary

- The `diagnose()` tool claims to detect runs “running for > 1 hour” but its query lacks a time threshold, so any run with status `running` is marked as stuck.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074e (branch: RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Audit DB with at least one active run

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/mcp/server.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Start a run and keep it in `running` status for a few minutes (well under one hour).
2. Call `diagnose()`.
3. Observe the run is reported under `stuck_runs`.

## Expected Behavior

- Only runs older than the stuck threshold (e.g., >1 hour) should be flagged as stuck.

## Actual Behavior

- Any run with status `running` and `completed_at` null is reported as stuck, regardless of age.

## Evidence

- `src/elspeth/mcp/server.py:1193` comments “running for > 1 hour” but no time filter is applied.
- `src/elspeth/mcp/server.py:1195`–`src/elspeth/mcp/server.py:1199` show the query only checks status and `completed_at`.

## Impact

- User-facing impact: False-positive “stuck run” alerts, reducing trust in diagnostics.
- Data integrity / security impact: None.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The stuck-run query omits a `started_at < now - timedelta(hours=1)` filter.

## Proposed Fix

- Code changes (modules/files): Add a timestamp cutoff condition in `src/elspeth/mcp/server.py` when selecting stuck runs.
- Config or schema changes: None.
- Tests to add/update: Add a test where a recent running run is not flagged, and an old running run is flagged.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/mcp/server.py:1193` (inline behavior description)
- Observed divergence: Implementation does not match stated “>1 hour” behavior.
- Reason (if known): Missing time filter in the query.
- Alignment plan or decision needed: None.

## Acceptance Criteria

- `diagnose()` only includes running runs that exceed the configured time threshold.
- Recent running runs are not listed under `stuck_runs`.

## Tests

- Suggested tests to run: `python -m pytest tests/mcp/test_server_diagnose.py -k stuck_runs`
- New tests required: yes, add `diagnose()` stuck-run threshold tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
