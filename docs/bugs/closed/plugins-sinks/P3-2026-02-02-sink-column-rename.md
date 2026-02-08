# Bug Report: Sinks need configurable column renaming

## Summary

- Sinks lack a generic way to rename output columns (e.g., input field `X` should be written as `Y`).
- This prevents simple header/field renames without transforms.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: user
- Date: 2026-02-02
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2-post-implementation-cleanup
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: any sink writing rows with desired renames

## Steps To Reproduce

1. Configure a sink that writes CSV/JSON output.
2. Provide rows with a field `X`.
3. Attempt to configure the sink to emit `Y` instead of `X`.
4. Observe there is no supported sink-level config for renaming.

## Expected Behavior

- Sinks should allow a simple rename mapping (e.g., `rename_columns: {X: Y}`) that renames output fields/headers.

## Actual Behavior

- No sink-level rename mapping exists; renaming requires a transform or manual post-processing.

## Impact

- Extra transforms for simple output renames
- Inconsistent output naming vs consumer requirements
- More complex pipelines for basic formatting tasks

## Root Cause Hypothesis

- Sink config lacks a standardized rename mapping across sink implementations.

## Proposed Fix

- Add sink-level `rename_columns` (or reuse display_headers semantics) with consistent behavior across CSV/JSON sinks.
- Ensure rename applies to both header names and row keys in output.
- Validate mapping keys against actual output fields.

## Acceptance Criteria

- Sink config supports renaming `X` -> `Y` without adding a transform.
- Output headers/keys reflect the rename mapping.
- Clear validation errors for unknown fields.

## Tests

- Suggested tests to run: `pytest tests/plugins/sinks/ -k rename -v`
- New tests required: yes (rename mapping behavior + validation)

## Notes / Links

- Related issues/PRs: N/A
