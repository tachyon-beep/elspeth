# Bug Report: SanitizedWebhookUrl Leaves Fragment Secrets Unsanitized

## Summary

- `SanitizedWebhookUrl.from_raw_url()` strips query params and basic auth, but preserves URL fragments verbatim, allowing fragment-based tokens (e.g., `#access_token=...`) to leak into the audit trail.

## Severity

- Severity: critical
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 7a155997ad574d2a10fa3838dd0079b0d67574ff (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/url.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `SanitizedWebhookUrl.from_raw_url("https://api.example.com/callback#access_token=secret", fail_if_no_key=False)`.
2. Inspect `sanitized_url`.

## Expected Behavior

- Fragment-based secrets are removed or sanitized so that stored URLs cannot contain credentials.

## Actual Behavior

- The fragment is preserved verbatim, so `sanitized_url` still contains `#access_token=secret`.

## Evidence

- `src/elspeth/contracts/url.py:228-236` reconstructs the sanitized URL using `parsed.fragment` unchanged, so any secrets in the fragment are preserved.
- `src/elspeth/contracts/url.py:2-6` claims sanitized URLs cannot contain credentials, which is violated when fragments carry secrets.

## Impact

- User-facing impact: URLs with fragment-based tokens (OAuth implicit flow, SPA callbacks) can leak secrets into audit artifacts.
- Data integrity / security impact: Audit trail may store credentials directly, violating secret handling requirements.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Fragment tokens were not considered a secret-bearing location during sanitization; only query params and userinfo are handled.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/contracts/url.py` sanitize or strip secrets in `parsed.fragment` (e.g., parse fragment as query string when it contains `=` and remove sensitive keys; preserve benign anchors).
- Config or schema changes: None.
- Tests to add/update: Add fragment-focused tests in `tests/core/security/test_url.py` for `#access_token=...` removal and benign fragment preservation.
- Risks or migration steps: Minimal; behavior change only for URLs with fragment secrets.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:688-726` (Secret Handling: never store secrets directly; use HMAC fingerprints).
- Observed divergence: Fragment-based secrets can be stored in the audit trail without fingerprinting or removal.
- Reason (if known): Fragment not included in sanitization path.
- Alignment plan or decision needed: Extend sanitization to handle fragments consistently with query params.

## Acceptance Criteria

- URLs with fragment tokens (e.g., `#access_token=secret`) are sanitized to remove the secret.
- Benign fragments (e.g., `#section1`) are preserved.
- Tests cover fragment secret removal and benign fragment retention.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/security/test_url.py`
- New tests required: yes, fragment sanitization cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Secret Handling section)
