# Bug Report: Azure plugin docstring references non-existent plugin names

## Summary

- The azure plugin pack docstring shows `azure_blob_source`/`azure_blob_sink`, but the actual registered plugin names are `azure_blob`, so the documented example fails at runtime.

## Severity

- Severity: trivial
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 290716a2563735271d162f1fac7d40a7690e6ed6
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/plugins/azure/__init__.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `PluginManager`, call `register_builtin_plugins()`.
2. Call `manager.get_source_by_name("azure_blob_source")` (or `get_sink_by_name("azure_blob_sink")`).

## Expected Behavior

- The example in the azure plugin pack docstring should use valid plugin names and succeed.

## Actual Behavior

- `ValueError: Unknown source plugin: azure_blob_source` (and similarly for `azure_blob_sink`).

## Evidence

- Docstring shows `azure_blob_source` and `azure_blob_sink` in `src/elspeth/plugins/azure/__init__.py:9-13`.
- Actual source plugin name is `azure_blob` in `src/elspeth/plugins/azure/blob_source.py:252`.
- Actual sink plugin name is `azure_blob` in `src/elspeth/plugins/azure/blob_sink.py:234`.

## Impact

- User-facing impact: Anyone following the example gets a plugin lookup error.
- Data integrity / security impact: None.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Docstring example is stale or copied from an earlier naming convention.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/plugins/azure/__init__.py` docstring example to use `"azure_blob"` for both source and sink.
- Config or schema changes: None.
- Tests to add/update:
  - None.
- Risks or migration steps:
  - None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- The docstring example uses `"azure_blob"` and matches the actual plugin names.

## Tests

- Suggested tests to run: None.
- New tests required: no.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
