# Bug Report: CLI crashes on non-mapping settings YAML before validation

## Summary

- `_load_raw_yaml()` and `_extract_secrets_config()` assume the YAML root is a mapping, so a non-mapping settings file triggers an uncaught `AttributeError` instead of a clear validation error.

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
- Data set or fixture: `settings.yaml` with a top-level list or scalar

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/cli.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `settings.yaml` whose top level is a list or scalar (e.g., `- foo: bar`).
2. Run `elspeth validate -s settings.yaml` or `elspeth run -s settings.yaml --dry-run`.
3. Observe an `AttributeError: 'list' object has no attribute 'get'` instead of a config error.

## Expected Behavior

- CLI should emit a clear configuration validation error indicating the YAML root must be a mapping.

## Actual Behavior

- CLI raises an uncaught `AttributeError` during secrets extraction.

## Evidence

- `src/elspeth/cli.py:246` `_load_raw_yaml()` returns `yaml.safe_load(f) or {}` without ensuring a mapping.
- `src/elspeth/cli.py:292` `_load_settings_with_secrets()` calls `raw_config.get(...)` unguarded.
- `src/elspeth/cli.py:316` `_extract_secrets_config()` repeats `raw_config.get(...)` unguarded.

## Impact

- User-facing impact: confusing stack trace instead of actionable config error.
- Data integrity / security impact: none direct, but config boundary is not validated as required.
- Performance or cost impact: none.

## Root Cause Hypothesis

- Missing type validation for the YAML root object before accessing `.get()` in `_load_settings_with_secrets()` and `_extract_secrets_config()`.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/cli.py` validate that `raw_config` is a `dict` in `_load_raw_yaml()` (or in `_extract_secrets_config()`), and raise a user-facing `ValueError` with a clear message when it isn’t.
- Config or schema changes: None.
- Tests to add/update: Add CLI validation test for non-mapping YAML to ensure a clean error message is emitted.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:59-69` (Tier 3 boundary requires validation at the boundary).
- Observed divergence: External config input isn’t validated before being accessed as a mapping.
- Reason (if known): Missing type check on raw YAML parse result.
- Alignment plan or decision needed: Add explicit root-type validation and surface a clean error.

## Acceptance Criteria

- Non-mapping YAML produces a readable validation error (no stack trace).
- `run`, `validate`, and any other path that uses `_load_raw_yaml()` handle this error consistently.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/test_cli_validation.py -k non_mapping_yaml`
- New tests required: yes, cover non-mapping YAML in CLI validation path.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 3 validation guidance)
---
# Bug Report: `purge` can silently create an empty SQLite DB and skip real payloads

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
