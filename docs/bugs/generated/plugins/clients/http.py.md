# Bug Report: AuditedHTTPClient records raw URLs containing secrets

## Summary

- AuditedHTTPClient writes the raw `full_url` into `request_data` without sanitization, so query-string tokens or Basic Auth credentials are stored in the audit trail in plain text.

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
- Data set or fixture: Any HTTP call where the URL contains a token or Basic Auth

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `/home/john/elspeth-rapid/src/elspeth/plugins/clients/http.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `AuditedHTTPClient` with a mock `LandscapeRecorder`.
2. Call `post()` with a URL that includes secrets, e.g. `https://api.example.com/hook?token=sk-secret` or `https://user:pass@api.example.com/hook`.
3. Inspect `record_call` arguments; observe `request_data["url"]` contains the raw secret.

## Expected Behavior

- URLs recorded in the audit trail are sanitized: sensitive query params and Basic Auth credentials are removed, and a fingerprint is recorded when available (consistent with secret handling policy).

## Actual Behavior

- `request_data["url"]` is stored as the raw URL string, including secrets, with no sanitization or fingerprinting.

## Evidence

- `src/elspeth/plugins/clients/http.py:204-209` stores `full_url` directly in `request_data` with no sanitization or fingerprint.
- `CLAUDE.md:678-684` mandates “Never store secrets - use HMAC fingerprints.”
- `src/elspeth/contracts/results.py:283-300` requires webhook URLs to be pre-sanitized to avoid storing tokens in the audit trail (pattern exists but is not used here).

## Impact

- User-facing impact: None directly, but audit trail contains leaked credentials.
- Data integrity / security impact: Secrets are written into the audit database (Tier 1 “full trust”), violating the secret-handling policy and creating a high-risk data leak.
- Performance or cost impact: Minimal.

## Root Cause Hypothesis

- `AuditedHTTPClient.post()` does not sanitize or fingerprint URLs before persisting them; it only filters headers.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/clients/http.py`: sanitize `full_url` before recording, using `SanitizedWebhookUrl.from_raw_url()` and store `sanitized_url` plus optional `url_fingerprint` in `request_data`.
- Config or schema changes: None.
- Tests to add/update:
  - Add unit test in `tests/plugins/clients/test_audited_http_client.py` to verify query param and Basic Auth secrets are removed from recorded URL and fingerprint is present when a key exists.
  - Add dev-mode test to ensure sanitization without fingerprint when `ELSPETH_ALLOW_RAW_SECRETS=true`.
- Risks or migration steps:
  - Request hashes will change because URL field changes; replay/verify may need to handle the new `url_fingerprint` field to preserve identity semantics.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:678-684` (Secret Handling), `src/elspeth/contracts/results.py:283-300` (sanitized webhook URLs).
- Observed divergence: Raw URLs (including secrets) are recorded in audit calls.
- Reason (if known): Missing URL sanitization step in `AuditedHTTPClient`.
- Alignment plan or decision needed: Standardize URL sanitization/fingerprinting for all audited HTTP calls.

## Acceptance Criteria

- Recorded `request_data["url"]` never contains tokens or Basic Auth credentials.
- If a fingerprint key exists, `request_data` includes a stable `url_fingerprint` tied to the secret values.
- Tests demonstrate sanitized URLs and fingerprint behavior in both normal and dev modes.

## Tests

- Suggested tests to run: `ELSPETH_ALLOW_RAW_SECRETS=true .venv/bin/python -m pytest tests/plugins/clients/test_audited_http_client.py`
- New tests required: yes, URL sanitization + fingerprint tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Secret Handling), `src/elspeth/contracts/url.py` (SanitizedWebhookUrl)
