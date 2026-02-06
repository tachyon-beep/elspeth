# Analysis: src/elspeth/core/security/fingerprint.py

**Lines:** 88
**Role:** HMAC-SHA256 fingerprinting of secrets for audit trail recording. Provides the core cryptographic primitive that allows the audit trail to verify "the same secret was used" without storing actual secret values. This is a foundational security building block used across the entire codebase.
**Key dependencies:** Imports `hashlib`, `hmac`, `os` (all standard library). Consumed by `config_secrets.py` (indirectly via recorder), `config.py` (`_fingerprint_secrets`, `_sanitize_dsn`), `contracts/url.py`, `plugins/clients/http.py`, `core/landscape/recorder.py`, and multiple test files.
**Analysis depth:** FULL

## Summary

This is a small, focused module with correct cryptographic implementation. The HMAC-SHA256 construction is standard and correct. However, there is one warning-level finding around the fingerprint key itself being treated as a regular string (UTF-8 encoded) rather than requiring minimum entropy or length. The module is sound for its purpose.

## Warnings

### [53] No minimum key length or entropy validation on fingerprint key

**What:** The `get_fingerprint_key()` function on line 47-53 reads `ELSPETH_FINGERPRINT_KEY` from the environment, checks it is non-empty, and encodes it as UTF-8 bytes. There is no validation of key length, entropy, or format. A single character like `"a"` would be accepted as a valid HMAC key.

**Why it matters:** HMAC-SHA256 is cryptographically secure with any key length, but a weak key makes brute-force attacks feasible. If an attacker obtains a fingerprint from the audit trail and the key is short/predictable, they could brute-force the original secret value. For a government emergency dispatch system where the audit trail must withstand formal inquiry, the fingerprint key should have minimum entropy requirements. A key like `"test"` or `"1234"` would produce valid fingerprints that are trivially reversible given the fingerprint.

**Evidence:**
```python
def get_fingerprint_key() -> bytes:
    env_key = os.environ.get(_ENV_VAR)
    if not env_key:  # Only checks for empty/None
        raise ValueError(...)
    return env_key.encode("utf-8")  # No length/entropy check
```

For context, NIST recommends HMAC keys be at least as long as the hash output (32 bytes for SHA-256). A warning log or minimum length check (e.g., 16 bytes) would catch misconfiguration.

### [48] Empty string check uses falsy evaluation

**What:** Line 48 uses `if not env_key:` which treats both `None` and `""` (empty string) as invalid. However, it also treats strings like `"0"` or `"False"` as valid keys, and whitespace-only strings like `"   "` would also be accepted (they are truthy). A key of all spaces would produce consistent fingerprints but represents a likely misconfiguration.

**Why it matters:** Low severity. A whitespace-only key is unlikely in practice but would not be caught by the current validation. The key `" "` would produce valid HMAC digests but would be trivially guessable.

**Evidence:**
```python
if not env_key:  # " " is truthy, passes this check
    raise ValueError(...)
return env_key.encode("utf-8")  # " ".encode() = b" " -- valid but weak
```

## Observations

### [82-86] HMAC construction is correct

**What:** The `hmac.new(key=key, msg=secret.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()` call is the standard HMAC-SHA256 construction. The key is bytes, the message is UTF-8 encoded, and the output is a deterministic 64-character hex string. This is correct and consistent with CLAUDE.md's specification.

### [56] Keyword-only `key` parameter is good API design

**What:** The `key` parameter is keyword-only (`*` separator implied by usage pattern), preventing accidental positional argument confusion between the secret and the key. This is good practice for a security-sensitive function.

### [29-31] Clean removal of module-level cache

**What:** The comment on line 29-31 documents removal of a previous module-level cache for Key Vault lookups, noting that env var lookups via `os.environ` don't need caching. This is correct -- `os.environ` is a dict, so lookups are O(1).

### [1-19] Docstring is accurate and helpful

**What:** The module docstring correctly describes both usage patterns (explicit key and env var) and notes the Key Vault integration path. This matches the actual implementation.

## Verdict

**Status:** SOUND
**Recommended action:** Consider adding a minimum key length warning (not enforcement, to avoid breaking existing deployments during RC) that logs a warning if the fingerprint key is shorter than 16 bytes. This would catch misconfiguration in development without breaking production. The core HMAC implementation is correct and does not need changes.
**Confidence:** HIGH -- The module is 88 lines of straightforward cryptographic code with no branching complexity. All paths are trivially verifiable.
