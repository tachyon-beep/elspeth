## Summary

`secret_fingerprint()` accepts an explicit empty HMAC key (`b""`), which degrades secret fingerprinting security and violates the project's "HMAC to avoid guessing oracle" intent.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — no production caller passes `key=b""`; all paths go through `get_fingerprint_key()` which validates non-empty)

## Location

- File: `src/elspeth/core/security/fingerprint.py`
- Line(s): 79-86 (missing explicit-key validation), 47-53 (env-key path does validate non-empty)
- Function/Method: `secret_fingerprint`, `get_fingerprint_key`

## Evidence

`get_fingerprint_key()` rejects empty environment keys:

```python
# src/elspeth/core/security/fingerprint.py:47-53
env_key = os.environ.get(_ENV_VAR)
if not env_key:
    raise ValueError(...)
return env_key.encode("utf-8")
```

But `secret_fingerprint()` does not validate explicit `key` at all:

```python
# src/elspeth/core/security/fingerprint.py:79-86
if key is None:
    key = get_fingerprint_key()

digest = hmac.new(
    key=key,
    msg=secret.encode("utf-8"),
    digestmod=hashlib.sha256,
).hexdigest()
```

Verified behavior: calling with `key=b""` succeeds and returns a digest (no error).
Also, tests only generate non-empty explicit keys (`tests/property/core/test_fingerprint_properties.py:38` uses `st.binary(min_size=1, ...)`), so this gap is currently untested.

This conflicts with documented security rationale that HMAC key secrecy is required to avoid offline guessing oracle behavior (`docs/architecture/overview.md:751-756`).

## Root Cause Hypothesis

Validation is split across two entry paths: environment-based key retrieval (`get_fingerprint_key`) enforces non-empty, but explicit-key usage in `secret_fingerprint` bypasses that check. The core primitive assumes caller correctness instead of enforcing the security invariant itself.

## Suggested Fix

In `secret_fingerprint()`, enforce non-empty key regardless of source:

```python
if key is None:
    key = get_fingerprint_key()
if len(key) == 0:
    raise ValueError("Fingerprint key must be non-empty")
```

Add regression tests in `tests/unit/core/security/test_fingerprint.py` for `key=b""` raising `ValueError`.

## Impact

If any internal/future caller passes an empty explicit key, secret fingerprints are computed with a known public key, weakening protection against offline guessing and undermining audit-trail secret confidentiality guarantees. This is a security validation gap in a core security primitive.
