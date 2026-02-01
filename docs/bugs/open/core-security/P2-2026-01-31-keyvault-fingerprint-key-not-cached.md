# Bug Report: Key Vault fingerprint key retrieved on every call (no cache)

## Summary

- `get_fingerprint_key()` makes a Key Vault API call every time when `ELSPETH_FINGERPRINT_KEY` is unset but `ELSPETH_KEYVAULT_URL` is set.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/security/fingerprint.py:58-99` - `get_fingerprint_key()` has no caching.
- Every call when env var unset makes Key Vault API call

## Impact

- User-facing impact: Performance degradation, potential rate limiting
- Data integrity: None
- Cost: Increased Key Vault API costs

## Proposed Fix

- Add module-level `_CACHED_FINGERPRINT_KEY: bytes | None = None` and return if populated

## Acceptance Criteria

- Key Vault called at most once per process

## Verification (2026-02-01)

**Status: STILL VALID**

- `get_fingerprint_key()` still performs a Key Vault lookup on every call when env var is unset. (`src/elspeth/core/security/fingerprint.py:58-95`)
