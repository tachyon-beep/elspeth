# Bug Report: SanitizedWebhookUrl leaves secrets in URL fragments

## Summary

- `SanitizedWebhookUrl.from_raw_url()` does not sanitize or fingerprint sensitive tokens embedded in the URL fragment (e.g., `#access_token=...`), violating the “URL cannot contain credentials” guarantee and allowing secrets to be stored in the audit trail.

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
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/url.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `SanitizedWebhookUrl.from_raw_url("https://api.example.com/callback#access_token=secret")`.
2. Inspect `sanitized_url` and `fingerprint`.

## Expected Behavior

- The fragment token (`access_token=secret`) is stripped from `sanitized_url`, and the secret value is fingerprinted (or a `SecretFingerprintError` is raised if the key is unavailable and `fail_if_no_key=True`).

## Actual Behavior

- The URL fragment is passed through unchanged; `sanitized_url` still contains `#access_token=secret`, and `fingerprint` remains `None`.

## Evidence

- `src/elspeth/contracts/url.py:153-179` only inspects `parsed.query` and basic auth, then returns the original URL unchanged if no query/basic auth secrets are present; fragments are not checked.
- `src/elspeth/contracts/url.py:228-236` reconstructs the URL with `parsed.fragment` unchanged, so any fragment secrets remain in the sanitized output.

## Impact

- User-facing impact: Secrets embedded in fragments are stored verbatim in audit artifacts and logs that use `sanitized_url`, violating the “no credentials in audit trail” guarantee.
- Data integrity / security impact: Credential leakage into the audit trail (legal record) and potential exposure of OAuth tokens or access tokens.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `SanitizedWebhookUrl.from_raw_url()` only parses and sanitizes query parameters and basic auth; it never inspects or sanitizes the fragment component, even though fragments often carry tokens (e.g., OAuth implicit flow).

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/contracts/url.py` to parse and sanitize fragment parameters when the fragment matches a query-string pattern (e.g., contains `=`), remove sensitive keys, and include any secret values in the fingerprint calculation.
  - Ensure `has_sensitive_keys` accounts for sensitive keys found in fragments.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests for fragment secrets: `#access_token=secret`, `#token=`, mixed fragment + query tokens, and case-insensitive fragment keys.
  - Add a test that fragment secrets trigger `SecretFingerprintError` when `fail_if_no_key=True` and a non-empty secret is present.
- Risks or migration steps:
  - Minimal; ensure fragment parsing preserves non-sensitive fragment content if present.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/url.py:3-7` (“GUARANTEE URLs cannot contain credentials when stored in the audit trail”).
- Observed divergence: Fragment tokens are left intact and can be stored in audit artifacts.
- Reason (if known): Fragment not considered in sanitization logic.
- Alignment plan or decision needed: Extend sanitization to fragment parameters using the same sensitive key list and fingerprint logic.

## Acceptance Criteria

- Sanitized webhook URLs never include sensitive tokens in fragments.
- Fingerprints are computed (or errors raised) for non-empty fragment secrets.
- New tests for fragment handling pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/security/test_url.py`
- New tests required: yes, fragment token handling coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/url.py` module docstring contract
