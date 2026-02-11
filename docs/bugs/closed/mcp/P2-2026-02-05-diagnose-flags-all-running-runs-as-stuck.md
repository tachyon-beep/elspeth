# Bug Report: `diagnose()` Flags All Running Runs as “Stuck”

**Status: RESOLVED ✅**

## Status Update (2026-02-11)

- Classification: **Resolved**
- Verification summary:
  - `diagnose()` now applies a one-hour UTC cutoff for `stuck_runs`.
  - Recent runs in `running` status are no longer falsely flagged as stuck.
- Current evidence:
  - `src/elspeth/mcp/analyzers/diagnostics.py`
  - `tests/unit/mcp/test_diagnostics.py`

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

- `src/elspeth/mcp/analyzers/diagnostics.py` now enforces `started_at < now(UTC) - 1 hour` for `stuck_runs`.
- New MCP unit tests cover recent/old/mixed running-run scenarios.

## Impact

- User-facing impact: False-positive “stuck run” alerts, reducing trust in diagnostics.
- Data integrity / security impact: None.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The stuck-run query omits a `started_at < now - timedelta(hours=1)` filter.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/mcp/analyzers/diagnostics.py`: add UTC one-hour cutoff for `stuck_runs`.
  - `src/elspeth/mcp/analyzers/diagnostics.py`: reuse the same cutoff for stuck operations.
- Config or schema changes: None.
- Tests added/updated:
  - `tests/unit/mcp/test_diagnostics.py`:
    - recent running run is not flagged as stuck
    - old running run is flagged as stuck
    - mixed recent+old running runs only include old run
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

- Validation run:
  - `uv run pytest -q tests/unit/mcp/test_diagnostics.py`
  - `uv run pytest -q tests/unit/mcp`
  - `uv run ruff check src/elspeth/mcp/analyzers/diagnostics.py tests/unit/mcp/test_diagnostics.py`
- New tests required: no (covered by new unit tests).

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
