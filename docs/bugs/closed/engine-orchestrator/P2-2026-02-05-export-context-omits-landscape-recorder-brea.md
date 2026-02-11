# Bug Report: Export Context Omits Landscape Recorder, Breaking `restore_source_headers`

**Status: FIXED**

## Status Update (2026-02-11)

- Classification: **Fixed**
- Verification summary:
  - `export_landscape()` now instantiates `LandscapeRecorder(db)` and passes it into `PluginContext`.
  - Export sink context now includes `landscape`, matching sink expectations for `restore_source_headers=True`.
- Current evidence:
  - `src/elspeth/engine/orchestrator/export.py:87`
  - `src/elspeth/engine/orchestrator/export.py:89`
  - `src/elspeth/engine/orchestrator/export.py:90`

## Summary

- `export_landscape` builds a `PluginContext` with `landscape=None`. CSV/JSON sinks configured with `restore_source_headers=True` require `ctx.landscape` and will raise a `ValueError`, causing export to fail even though a `LandscapeDB` is available.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any run with `landscape.export.enabled: true` and export sink configured with `restore_source_headers: true`

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/export.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `landscape.export.enabled: true` and set export sink to `csv` or `json` with `restore_source_headers: true`.
2. Run a pipeline to completion and trigger export.
3. Observe export failure with a `ValueError` about missing Landscape in context.

## Expected Behavior

- Export should provide a `PluginContext` with `landscape` set so sinks can resolve headers.

## Actual Behavior

- Export constructs `PluginContext` with `landscape=None`, and sinks raise `ValueError`, failing the export.

## Evidence

- `src/elspeth/engine/orchestrator/export.py:83-85` sets `landscape=None` in `PluginContext`.
- `src/elspeth/plugins/sinks/json_sink.py:489-494` raises if `ctx.landscape` is `None` when `restore_source_headers=True`.
- `src/elspeth/plugins/sinks/csv_sink.py:556-561` has the same requirement.

## Impact

- User-facing impact: Export fails for common sink configurations that rely on header restoration.
- Data integrity / security impact: Audit trail export becomes unavailable for compliance workflows.
- Performance or cost impact: Operational overhead to re-run export with altered sink settings.

## Root Cause Hypothesis

- Export path does not supply a LandscapeRecorder to the sink context despite having access to `LandscapeDB`.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/orchestrator/export.py`: Instantiate `LandscapeRecorder(db)` and pass it as `ctx.landscape` for export sink writes.
- Config or schema changes: None
- Tests to add/update:
  - Add a unit/integration test that exports with `restore_source_headers=True` and verifies no exception.
- Risks or migration steps:
  - Low risk; context only enriched for export.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Sinks expect `ctx.landscape` for header restoration, but export context omits it.
- Reason (if known): Export context set with minimal fields only.
- Alignment plan or decision needed: Ensure export contexts satisfy sink expectations.

## Acceptance Criteria

1. Export succeeds with `restore_source_headers=True` for CSV/JSON sinks.
2. No `ValueError` is raised due to missing `ctx.landscape`.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/engine/test_export.py -v`
- New tests required: yes, export with header restoration.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
