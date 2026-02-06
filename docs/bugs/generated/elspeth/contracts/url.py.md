# Bug Report: SanitizedWebhookUrl Leaves Fragment Tokens Unredacted

## Summary

- `SanitizedWebhookUrl.from_raw_url()` ignores secrets embedded in URL fragments (e.g., `#access_token=...`), returning the raw URL unchanged and storing the token in the audit trail.

## Severity

- Severity: critical
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Example webhook URL containing fragment token (e.g., `https://example.com/callback#access_token=sk-abc`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/contracts/url.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `SanitizedWebhookUrl.from_raw_url("https://example.com/callback#access_token=sk-abc", fail_if_no_key=False)`.
2. Inspect `result.sanitized_url`.

## Expected Behavior

- Fragment tokens (e.g., `access_token`) should be removed or redacted, and a fingerprint should be computed when a key is available.

## Actual Behavior

- The URL is returned unchanged with the fragment intact, and no fingerprint is generated.

## Evidence

- Early return bypasses sanitization when no sensitive query params or basic auth are detected; fragment is not checked: `src/elspeth/contracts/url.py:177-179`.
- Fragment is preserved verbatim in reconstruction, so any secrets in `#...` are stored: `src/elspeth/contracts/url.py:232-235`.
- Audit artifacts store `sanitized_url` directly, so fragment secrets enter the audit trail: `src/elspeth/contracts/results.py:447-473`.
- The module claims URLs stored in the audit trail cannot contain credentials: `src/elspeth/contracts/url.py:2-6`.
- Secret handling policy forbids storing secrets directly and mandates fingerprints: `CLAUDE.md:688-726`.

## Impact

- User-facing impact: None directly, but audit trail records can include live tokens in fragment URLs.
- Data integrity / security impact: Secret leakage into the audit trail violates audit safety and secret-handling policy; credentials become recoverable from stored artifacts.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `SanitizedWebhookUrl.from_raw_url()` only inspects query params and basic auth for secrets, and performs an early return when those are absent, leaving fragment tokens untouched.

## Proposed Fix

- Code changes (modules/files): Extend `SanitizedWebhookUrl.from_raw_url()` in `src/elspeth/contracts/url.py` to parse fragment data (treat `#a=b&c=d` like query params), detect sensitive keys, strip them, and compute fingerprints; gate the early return on “no sensitive query params, no sensitive fragment params, and no basic auth”.
- Config or schema changes: None.
- Tests to add/update: Add tests in `tests/core/security/test_url.py` for fragment token sanitization (e.g., `#access_token=...`) including fingerprint behavior and no-key error paths.
- Risks or migration steps: Minimal; behavior changes only affect sanitized audit URLs, not runtime webhook calls.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/url.py:2-6`; `CLAUDE.md:688-726`.
- Observed divergence: URLs containing fragment tokens are returned unchanged and stored in audit artifacts.
- Reason (if known): Fragment parsing and sanitization are not implemented.
- Alignment plan or decision needed: Implement fragment sanitization and update tests to enforce the “no secrets in audit trail” guarantee.

## Acceptance Criteria

- A fragment token (e.g., `#access_token=sk-abc`) is removed from `sanitized_url`.
- A fingerprint is computed for fragment secret values when `ELSPETH_FINGERPRINT_KEY` is available.
- `SecretFingerprintError` is raised in production mode when fragment secrets exist and no key is set.
- Tests covering fragment sanitization pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/security/test_url.py -k "fragment"`
- New tests required: yes, fragment token sanitization cases in `tests/core/security/test_url.py`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:688-726`
