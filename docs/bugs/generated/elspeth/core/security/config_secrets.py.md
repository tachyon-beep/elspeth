# Bug Report: Key Vault Secrets Load Without Fingerprint Key, Causing Late Failure and Missing Audit Records

## Summary

- `load_secrets_from_config` loads Key Vault secrets even when `ELSPETH_FINGERPRINT_KEY` is absent, which later causes audit recording to fail and leaves secret resolution events unrecorded.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: `SecretsConfig` with `source="keyvault"` and mapping that omits `ELSPETH_FINGERPRINT_KEY`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/core/security/config_secrets.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Ensure `ELSPETH_FINGERPRINT_KEY` is not set in the environment.
2. Configure secrets with `source: keyvault` and a mapping that does not include `ELSPETH_FINGERPRINT_KEY`.
3. Call `load_secrets_from_config()` and pass its `secret_resolutions` into an orchestrator run.

## Expected Behavior

- Secret loading should fail fast with a clear error if no fingerprint key is available, before any Key Vault secrets are fetched and before environment variables are injected.

## Actual Behavior

- Secrets are fetched and injected, but the run fails later when `record_secret_resolutions` calls `get_fingerprint_key`, causing missing audit records for the already-fetched secrets.

## Evidence

- `load_secrets_from_config` has no check for `ELSPETH_FINGERPRINT_KEY` availability before loading secrets. `src/elspeth/core/security/config_secrets.py:72` through `src/elspeth/core/security/config_secrets.py:158`
- Audit recording requires a fingerprint key and will raise if missing. `src/elspeth/engine/orchestrator/core.py:430` through `src/elspeth/engine/orchestrator/core.py:440`
- `get_fingerprint_key` raises when `ELSPETH_FINGERPRINT_KEY` is absent. `src/elspeth/core/security/fingerprint.py:34` through `src/elspeth/core/security/fingerprint.py:53`
- Audit standard requires fingerprints for secret resolution records. `CLAUDE.md:688` through `CLAUDE.md:727`

## Impact

- User-facing impact: Runs fail late (after run creation) with a fingerprint-key error that is disconnected from the earlier secret load.
- Data integrity / security impact: Secret resolutions are not recorded in the audit trail even though external Key Vault calls occurred.
- Performance or cost impact: Unnecessary Key Vault API calls and startup latency before the run fails.

## Root Cause Hypothesis

- `load_secrets_from_config` does not enforce the availability of `ELSPETH_FINGERPRINT_KEY` (env or mapping) before fetching Key Vault secrets, so audit recording fails later.

## Proposed Fix

- Code changes (modules/files): Add a preflight check in `src/elspeth/core/security/config_secrets.py` to require `ELSPETH_FINGERPRINT_KEY` to be set or present in `config.mapping` before any Key Vault calls; raise `SecretLoadError` with a clear remediation message if missing.
- Config or schema changes: None.
- Tests to add/update: Add a unit test in `tests/core/security/test_config_secrets.py` asserting that missing fingerprint key causes `SecretLoadError` before any secret fetch.
- Risks or migration steps: Minimal; behavior changes only for misconfigured Key Vault usage.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:688` through `CLAUDE.md:727`
- Observed divergence: Secrets can be loaded from Key Vault without guaranteeing a fingerprint key, so audit records cannot be produced.
- Reason (if known): Missing preflight validation in secret-loading path.
- Alignment plan or decision needed: Enforce fingerprint-key availability at the start of `load_secrets_from_config` or explicitly decide to allow opt-out (with a documented, auditable alternative).

## Acceptance Criteria

- When Key Vault secrets are configured and `ELSPETH_FINGERPRINT_KEY` is missing, `load_secrets_from_config` raises `SecretLoadError` before any secrets are fetched.
- When the fingerprint key is available (env or mapping), secrets load normally and audit recording proceeds without error.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/security/test_config_secrets.py`
- New tests required: yes, missing-fingerprint-key preflight error case.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:688` through `CLAUDE.md:727`
