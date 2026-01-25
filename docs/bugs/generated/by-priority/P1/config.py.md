# Bug Report: Duplicate fork/coalesce branch names accepted, causing coalesce stalls and token overwrites

## Summary

- Gate `fork_to` and `coalesce.branches` accept duplicate names; downstream coalesce tracking keys by branch name and counts list length, so duplicates overwrite arrivals and can prevent merges.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/rc1-bug-burndown-session-4 @ 8635789
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Pipeline config with duplicate fork/coalesce branch names

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit for `src/elspeth/core/config.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: reviewed config validation, DAG wiring, and coalesce executor logic

## Steps To Reproduce

1. Define a gate with `routes` including `"fork"` and `fork_to: ["path_a", "path_a"]`.
2. Define a coalesce with `branches: ["path_a", "path_a"]` and `policy: require_all`.
3. Build/run the pipeline and observe coalesce behavior.

## Expected Behavior

- Config validation rejects duplicate branch names in `fork_to` and `coalesce.branches`.

## Actual Behavior

- Configuration is accepted; coalesce arrivals overwrite by branch name and the merge waits for `len(branches)`, so merges can stall or drop data.

## Evidence

- `src/elspeth/core/config.py:238` defines `validate_fork_to_labels` but only checks reserved labels.
- `src/elspeth/core/config.py:249` shows the loop checks reserved labels without uniqueness validation.
- `src/elspeth/core/config.py:327` defines `CoalesceSettings.branches` with no uniqueness validator.
- `src/elspeth/core/dag.py:509` maps `branch_to_coalesce` by branch name, overwriting duplicates.
- `src/elspeth/engine/coalesce_executor.py:173` stores arrivals in a dict keyed by branch name.
- `src/elspeth/engine/coalesce_executor.py:195` compares arrivals to `len(settings.branches)`.

## Impact

- User-facing impact: coalesce can hang or produce fewer outputs than expected.
- Data integrity / security impact: silent loss of branch results before merge.
- Performance or cost impact: stalled runs and wasted compute.

## Root Cause Hypothesis

- Missing uniqueness validation for `fork_to` and `coalesce.branches` (and no cross-coalesce uniqueness), while runtime logic assumes uniqueness.

## Proposed Fix

- Code changes (modules/files):
  - Add uniqueness checks in `GateSettings.validate_fork_to_labels` in `src/elspeth/core/config.py`.
  - Add a validator in `CoalesceSettings` to enforce unique `branches` in `src/elspeth/core/config.py`.
  - Optionally enforce global uniqueness across coalesce configurations in `ElspethSettings`.
- Config or schema changes: None.
- Tests to add/update:
  - Add `tests/core/test_config.py` cases rejecting duplicate `fork_to` and `coalesce.branches`.
- Risks or migration steps:
  - Existing configs with duplicates will fail fast (expected; prevents silent loss).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:342`
- Observed divergence: duplicate branch names can prevent tokens from reaching a terminal state or cause silent loss.
- Reason (if known): config validation gap.
- Alignment plan or decision needed: enforce uniqueness at config load time.

## Acceptance Criteria

- Duplicate `fork_to` or `coalesce.branches` values raise a clear validation error.
- Coalesce merges complete when all distinct branches arrive, with no overwrites.

## Tests

- Suggested tests to run: `pytest tests/core/test_config.py -k fork_to`
- New tests required: yes, duplicate branch validation

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/bugs/open/core-dag/P1-2026-01-22-duplicate-branch-names-break-coalesce.md`
---
# Bug Report: Audit config stores raw database sink DSNs (passwords not fingerprinted)

## Summary

- `resolve_config()` fingerprints secrets but does not sanitize database sink `url` values, so DSN passwords can be stored verbatim in the audit config.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/rc1-bug-burndown-session-4 @ 8635789
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Pipeline with `database` sink using a DSN containing credentials

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit for `src/elspeth/core/config.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: reviewed audit config fingerprinting and database sink config

## Steps To Reproduce

1. Configure a `database` sink with `options.url: "postgresql://user:secret@host/db"`.
2. Load settings and call `resolve_config()` (or run via CLI which stores the resolved config).
3. Inspect the resolved config stored in Landscape; the raw DSN with password remains.

## Expected Behavior

- DSN passwords are removed and fingerprinted before audit storage.

## Actual Behavior

- Only `landscape.url` is sanitized; sink DSNs pass through `_fingerprint_secrets` unchanged because the key is `url`, not a secret field name.

## Evidence

- `src/elspeth/core/config.py:1016` sanitizes only `landscape.url`.
- `src/elspeth/core/config.py:1039` fingerprints sink options using `_fingerprint_secrets`.
- `src/elspeth/core/config.py:772` defines secret field names that exclude `url`.
- `src/elspeth/core/config.py:781` uses field-name matching for secret detection.
- `src/elspeth/plugins/sinks/database_sink.py:42` defines the sink config field as `url`.

## Impact

- User-facing impact: credentials can appear in audit exports and run records.
- Data integrity / security impact: secret leakage violates audit safety requirements.
- Performance or cost impact: none.

## Root Cause Hypothesis

- Audit fingerprinting only handles `landscape.url` and name-based secret fields; it does not sanitize DSNs embedded in sink `options.url`.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/core/config.py`, detect database sink configs and sanitize `options["url"]` via `_sanitize_dsn` or `SanitizedDatabaseUrl`, storing a fingerprint field (e.g., `url_password_fingerprint`) or redaction flag.
  - Consider extending the same handling to datasource options if DSN-based sources are added.
- Config or schema changes: None.
- Tests to add/update:
  - Add `tests/core/test_config.py` to assert `resolve_config()` redacts passwords in `sinks.*.options.url`.
- Risks or migration steps:
  - Audit config output changes (password removed, fingerprint added).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:358`
- Observed divergence: audit config can contain raw secrets.
- Reason (if known): DSN sanitization only applied to `landscape.url`.
- Alignment plan or decision needed: extend audit fingerprinting to sink DSNs.

## Acceptance Criteria

- Resolved audit config never contains raw DSN passwords for database sinks.
- Fingerprint/redaction metadata is recorded for DSN passwords.

## Tests

- Suggested tests to run: `pytest tests/core/test_config.py -k fingerprint`
- New tests required: yes, database sink DSN redaction

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
