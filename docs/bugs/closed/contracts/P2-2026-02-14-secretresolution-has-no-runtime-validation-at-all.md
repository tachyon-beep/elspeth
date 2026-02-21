## Summary

`SecretResolution` has no runtime validation at all, allowing malformed secret-provenance records from Tier-1 storage to pass and export silently.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — defense-in-depth for Tier 1 corruption, only constructed from our own DB read/write paths)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/contracts/audit.py
- Line(s): 672-703
- Function/Method: `SecretResolution` (missing `__post_init__`)

## Evidence

`SecretResolution` defines fields but has no `__post_init__` validation. This differs from other audit contracts in the same file (e.g., `Run`, `Node`, `Batch`, `TokenOutcome`) that validate critical invariants.

Read path constructs `SecretResolution` directly from DB rows:

- `src/elspeth/core/landscape/_run_recording.py:404-416`

Export path then emits these fields verbatim:

- `src/elspeth/core/landscape/exporter.py:188-200`

Expected semantics (HMAC fingerprint, source provenance) are only documented in comments, not enforced:

- `src/elspeth/contracts/audit.py:674-692`
- `src/elspeth/core/landscape/schema.py:498-510` (no strict value-domain checks beyond nullability)

## Root Cause Hypothesis

`SecretResolution` was added as an immutable data shape but not treated as a strict Tier-1 contract object, so invariants were left implicit/documented rather than enforced.

## Suggested Fix

Add `SecretResolution.__post_init__` in `audit.py` to enforce core invariants, e.g.:

- `env_var_name`, `source`, `fingerprint` non-empty.
- `source` restricted to supported values (currently documented as `keyvault`).
- `fingerprint` format validated as 64-char lowercase hex.
- `timestamp` finite numeric.
- `resolution_latency_ms` non-negative when present.
- If `source == "keyvault"`, require non-empty `vault_url` and `secret_name`.

## Impact

Secret provenance records can become internally inconsistent without triggering a crash, undermining audit-trail trust for "which secret came from where" evidence.
