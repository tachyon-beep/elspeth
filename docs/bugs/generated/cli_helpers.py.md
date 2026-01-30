# Bug Report: Explicit --settings path silently ignored when missing, causing wrong database resolution

## Summary

- `resolve_database_url` ignores a user-supplied `settings_path` if the file does not exist and silently falls back to `./settings.yaml`, which can point to a different database than the user intended.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: settings.yaml present in CWD, user provides missing --settings path

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/cli_helpers.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Ensure `./settings.yaml` exists and points `landscape.url` to DB_A.
2. Run `elspeth explain --run latest --settings /tmp/does-not-exist.yaml` (no `--database`).
3. Observe it proceeds using `./settings.yaml` instead of erroring on the missing explicit settings path.

## Expected Behavior

- The CLI should fail fast with a clear error when a user explicitly provides a non-existent `--settings` path.

## Actual Behavior

- The missing `settings_path` is ignored, and the function falls back to `./settings.yaml`, potentially resolving a different database without warning.

## Evidence

- `resolve_database_url` only loads the user-provided path if it exists; otherwise it skips directly to default settings, with no error for the explicitly provided path:
  - `/home/john/elspeth-rapid/src/elspeth/cli_helpers.py:108-126`

## Impact

- User-facing impact: A user can unknowingly query or operate on the wrong audit database when they mistype `--settings`.
- Data integrity / security impact: Audit lineage may be reported from the wrong run database, undermining traceability and correctness.
- Performance or cost impact: Minimal, but can lead to wasted investigation time.

## Root Cause Hypothesis

- The function treats a non-existent explicit `settings_path` the same as "not provided," violating configuration precedence and leading to silent fallback.

## Proposed Fix

- Code changes (modules/files):
  - Add an explicit check: if `settings_path` is provided and does not exist, raise `ValueError` immediately. (`/home/john/elspeth-rapid/src/elspeth/cli_helpers.py`)
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test for `resolve_database_url` that passes a non-existent `settings_path` and asserts a `ValueError`.
- Risks or migration steps:
  - Slight behavior change: previously silent fallback will now be a hard error for mistyped settings paths.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): CLAUDE.md “Configuration Precedence (High to Low)”
- Observed divergence: Explicit settings input should be honored or error; current behavior silently falls back to defaults.
- Reason (if known): Missing explicit guard on `settings_path` existence.
- Alignment plan or decision needed: Enforce failure on invalid explicit settings path.

## Acceptance Criteria

- Providing `--settings` with a non-existent file results in a clear `ValueError` and no fallback to default settings.
- Existing behavior when `--settings` is valid or omitted remains unchanged.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add a unit test for `resolve_database_url` with missing `settings_path`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: CLAUDE.md (Configuration Precedence section)
