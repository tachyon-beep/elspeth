# Bug Report: Key Vault fingerprint key retrieved on every call (no cache)

## Summary

- `get_fingerprint_key()` fetches from Azure Key Vault on every invocation when `ELSPETH_KEYVAULT_URL` is set, causing redundant external calls and per-request latency/rate‑limit risk.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: `ELSPETH_KEYVAULT_URL` set, `ELSPETH_FINGERPRINT_KEY` unset
- Data set or fixture: Any pipeline using Key Vault for fingerprint key (e.g., audited HTTP client with auth headers)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/security/fingerprint.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Set `ELSPETH_KEYVAULT_URL` and ensure `ELSPETH_FINGERPRINT_KEY` is not set.
2. Patch `_get_keyvault_client()` to a mock `SecretClient` that counts `get_secret` calls.
3. Call `secret_fingerprint("s1")` twice without passing `key`.
4. Observe `get_secret` called twice.

## Expected Behavior

- The fingerprint key is fetched once per process (or cached for the process lifetime) and reused across subsequent `secret_fingerprint()` calls.

## Actual Behavior

- Every `secret_fingerprint()` call triggers a full Key Vault retrieval via `get_fingerprint_key()` when the env key is missing.

## Evidence

- `src/elspeth/core/security/fingerprint.py:58`–`95` fetches from Key Vault every call; no cache or memoization.
- `src/elspeth/core/security/fingerprint.py:126`–`133` calls `get_fingerprint_key()` whenever `key` is not passed.
- `src/elspeth/plugins/clients/http.py:109`–`127` shows per-request header fingerprinting that calls `secret_fingerprint()` without supplying a key, amplifying the repeated Key Vault fetches.

## Impact

- User-facing impact: Increased latency for any operation that fingerprints secrets (e.g., every HTTP request with auth headers).
- Data integrity / security impact: Higher chance of Key Vault throttling/failures leading to missing auth headers or errors in fingerprinting paths.
- Performance or cost impact: Redundant external calls to Key Vault; potential rate‑limit penalties and higher cloud cost.

## Root Cause Hypothesis

- `get_fingerprint_key()` lacks any module-level caching and always performs a Key Vault request when `ELSPETH_FINGERPRINT_KEY` is absent.

## Proposed Fix

- Code changes (modules/files):
  - Add a module‑level cache (e.g., `_CACHED_FINGERPRINT_KEY: bytes | None`) in `src/elspeth/core/security/fingerprint.py`.
  - Update `get_fingerprint_key()` to return the cached key if present; populate cache after successful env/Key Vault retrieval.
  - Optionally add a small helper to clear cache for tests.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test ensuring repeated `secret_fingerprint()` calls only trigger a single Key Vault `get_secret()` call when `ELSPETH_KEYVAULT_URL` is set.
- Risks or migration steps:
  - Key rotation during a long-lived process would require restart or explicit cache clear; document this as expected behavior (key should be stable per docs).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Repeated `secret_fingerprint()` calls with Key Vault configured perform at most one Key Vault retrieval per process.
- New/updated tests pass (including the cache behavior test).

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/security/test_fingerprint.py -v`
- New tests required: yes, add a Key Vault call count/caching test

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/design/requirements.md` (GOV‑009)
