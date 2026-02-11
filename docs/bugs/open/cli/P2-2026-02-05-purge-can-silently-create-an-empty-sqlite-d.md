# Bug Report: `purge` can silently create an empty SQLite DB and skip real payloads

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - `purge` still accepts `config.landscape.url` from `settings.yaml` without an existence check for file-backed SQLite databases.
  - `LandscapeDB` initialization still creates tables, so a missing file with an existing parent directory can produce a brand-new empty DB.
  - Reproduced behavior: running `purge --dry-run` with a missing configured SQLite file created the DB and reported no expired payloads.
- Current evidence:
  - `src/elspeth/cli.py:1249`
  - `src/elspeth/core/landscape/database.py:102`
  - `src/elspeth/core/landscape/database.py:252`

## Summary

- When `elspeth purge` relies on `settings.yaml` for the database URL, it doesn’t verify SQLite file existence, so `LandscapeDB.from_url()` can create a new empty DB and the purge reports “no payloads” while real payloads remain.

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
- Data set or fixture: `settings.yaml` with `landscape.url` pointing at a missing SQLite file

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/cli.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Set `settings.yaml` to use a file-backed SQLite URL (e.g., `sqlite:///./state/audit.db`) where the file does not exist.
2. Run `elspeth purge --dry-run` without `--database`.
3. Observe “Using database from settings.yaml: …” and “No payloads older than … days found.”

## Expected Behavior

- CLI should fail fast if the SQLite file in `settings.yaml` does not exist, matching the explicit `--database` path behavior.

## Actual Behavior

- A new empty database is created and purge reports nothing to delete, leaving real payloads untouched.

## Evidence

- `src/elspeth/cli.py:1624` uses `config.landscape.url` without validating SQLite file existence.
- `src/elspeth/cli.py:1665` calls `LandscapeDB.from_url(db_url)` which can create the DB file.
- `src/elspeth/core/landscape/database.py:241` `from_url()` builds an engine and calls `metadata.create_all(...)`, which creates SQLite files if missing.

## Impact

- User-facing impact: purge appears to succeed while doing nothing.
- Data integrity / security impact: retention policies are not enforced; payloads may persist unexpectedly.
- Performance or cost impact: storage growth and potential disk exhaustion.

## Root Cause Hypothesis

- Missing SQLite file existence check when `db_url` originates from `settings.yaml`.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/cli.py` detect SQLite file-backed URLs from `config.landscape.url`, verify the file exists (and is not `:memory:`), and error if missing.
- Config or schema changes: None.
- Tests to add/update: Add purge CLI test to assert missing SQLite file results in a failure and does not create a new DB.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:11-19` (audit trail is source of truth; no silent ambiguity).
- Observed divergence: purge silently targets a new empty DB instead of the intended audit trail.
- Reason (if known): missing file existence guard when using config-provided DB URL.
- Alignment plan or decision needed: enforce existence checks for file-backed SQLite URLs in purge.

## Acceptance Criteria

- `elspeth purge` fails with a clear error when `settings.yaml` points to a missing SQLite file.
- `elspeth purge` continues to work for valid SQLite files and non-SQLite URLs.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/integration/test_purge_cli.py -k missing_sqlite_db`
- New tests required: yes, cover missing SQLite file when using config-based DB URL.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (auditability standard)
