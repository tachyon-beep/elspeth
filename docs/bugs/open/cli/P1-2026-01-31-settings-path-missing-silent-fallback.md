# Bug Report: Explicit --settings path silently ignored when missing

## Summary

- `resolve_database_url` ignores a user-supplied `settings_path` if the file does not exist and silently falls back to `./settings.yaml`, which can point to a different database than the user intended.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31
- Related run/issue ID: N/A

## Evidence

- `src/elspeth/cli_helpers.py:108-126` - function only loads user-provided path if it exists; otherwise skips to default settings with no error

## Impact

- User-facing impact: User can unknowingly query or operate on the wrong audit database when they mistype `--settings`
- Data integrity / security impact: Audit lineage may be reported from the wrong run database, undermining traceability
- Performance or cost impact: Wasted investigation time

## Root Cause Hypothesis

- The function treats a non-existent explicit `settings_path` the same as "not provided," violating configuration precedence.

## Proposed Fix

- Code changes:
  - Add explicit check: if `settings_path` is provided and does not exist, raise `ValueError` immediately
- Tests to add/update:
  - Add unit test for `resolve_database_url` that passes non-existent `settings_path` and asserts `ValueError`

## Acceptance Criteria

- Providing `--settings` with a non-existent file results in a clear `ValueError` and no fallback to default settings
- Existing behavior when `--settings` is valid or omitted remains unchanged
