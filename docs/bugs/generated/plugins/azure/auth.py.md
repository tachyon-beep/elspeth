# Bug Report: Auth method selection ignores validator’s trimmed checks, can pick wrong method

## Summary

- `AzureAuthConfig.create_blob_service_client()` and `auth_method` choose the auth path based on raw field truthiness, which can disagree with the validator’s “trimmed” checks and select the wrong method when a non-active field is whitespace-only.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Config with `connection_string="   "` and valid `sas_token` + `account_url`

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/plugins/azure/auth.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Construct `AzureAuthConfig(connection_string="   ", sas_token="token", account_url="https://acct.blob.core.windows.net")`.
2. Call `create_blob_service_client()` or read `auth_method`.

## Expected Behavior

- The active method should be SAS token (per validator’s trimmed checks), and `create_blob_service_client()` should build a client using `sas_token` + `account_url`.

## Actual Behavior

- The code treats the whitespace `connection_string` as truthy and selects the connection-string branch, ignoring the validated SAS config and leading to auth failures with an invalid connection string. `auth_method` also reports `connection_string` incorrectly.

## Evidence

- Validator uses trimmed checks to decide active method: `has_conn_string = ... self.connection_string.strip()` and `has_sas_token = ... self.sas_token.strip()` in `/home/john/elspeth-rapid/src/elspeth/plugins/azure/auth.py:85-99`.
- Branch selection ignores those trimmed checks and uses raw truthiness: `if self.connection_string: ... elif self.sas_token: ...` in `/home/john/elspeth-rapid/src/elspeth/plugins/azure/auth.py:157-167`.
- `auth_method` mirrors the same raw-truthiness logic in `/home/john/elspeth-rapid/src/elspeth/plugins/azure/auth.py:210-217`.

## Impact

- User-facing impact: Valid SAS/managed-identity/service-principal configs can fail if any other auth field is set to whitespace (common with env var interpolation), causing incorrect auth method selection and connection failure.
- Data integrity / security impact: None directly, but it prevents data access and may prompt unsafe manual workarounds.
- Performance or cost impact: Wasted retries or failed runs.

## Root Cause Hypothesis

- The validator determines the active method using trimmed strings, but runtime selection uses raw field truthiness; whitespace-only values are treated as “set” at runtime even though validation excludes them.

## Proposed Fix

- Code changes (modules/files):
  - Normalize auth fields in `validate_auth_method` (e.g., coerce whitespace-only strings to `None`) and/or store the computed active method in a private attribute used by `create_blob_service_client()` and `auth_method`.
  - Update `create_blob_service_client()` and `auth_method` to use the same trimmed checks as the validator.
- Config or schema changes: None.
- Tests to add/update:
  - Unit test: whitespace `connection_string` + valid `sas_token` chooses SAS path (no attempt to use connection string).
  - Unit test: whitespace `sas_token` + valid managed identity chooses managed identity.
- Risks or migration steps:
  - Low risk; behavior becomes consistent with existing validation rules.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- `create_blob_service_client()` uses the same “active method” logic as validation (whitespace-only values do not select a method).
- `auth_method` reports the validated active method.
- Added tests cover whitespace edge cases and pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, unit tests for auth-method selection with whitespace fields.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
