# Bug Report: Source Plugin Name Example Mismatch in `sources/__init__.py`

## Summary

- The usage example in `src/elspeth/plugins/sources/__init__.py` shows `get_source_by_name("csv_source")`, but the actual CSV source plugin name is `"csv"`, so the example triggers a lookup failure.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit for `src/elspeth/plugins/sources/__init__.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate a `PluginManager`, call `register_builtin_plugins()`, then call `get_source_by_name("csv_source")` as shown in the module docstring.
2. Observe the lookup failure because the CSV source plugin is named `"csv"`.

## Expected Behavior

- The example should reference the correct plugin name and successfully resolve the CSV source.

## Actual Behavior

- The example uses `"csv_source"`, which does not match the actual plugin name `"csv"`, so `get_source_by_name` raises a lookup error.

## Evidence

- Docstring example uses `"csv_source"` in `src/elspeth/plugins/sources/__init__.py:8`.
- CSV source plugin declares `name = "csv"` in `src/elspeth/plugins/sources/csv_source.py:61`.

## Impact

- User-facing impact: Developers following the example will hit a ValueError and may misconfigure source plugins.
- Data integrity / security impact: None.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The example string `"csv_source"` is stale and was not updated after plugin naming conventions standardized on `"csv"`.

## Proposed Fix

- Code changes (modules/files): Update the example in `src/elspeth/plugins/sources/__init__.py` to use `"csv"` or a generic placeholder matching actual plugin names.
- Config or schema changes: None.
- Tests to add/update: None.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Documentation example does not reflect actual plugin name.
- Reason (if known): Likely leftover from earlier naming conventions.
- Alignment plan or decision needed: Update the example to match current plugin naming.

## Acceptance Criteria

- The docstring example in `src/elspeth/plugins/sources/__init__.py` uses `"csv"` (or another valid source name) and matches the actual plugin name.

## Tests

- Suggested tests to run: None
- New tests required: no

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
