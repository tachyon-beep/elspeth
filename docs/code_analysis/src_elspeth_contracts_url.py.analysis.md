# Analysis: src/elspeth/contracts/url.py

**Lines:** 239 (258 with trailing newline)
**Role:** URL sanitization types for audit-safe storage. Provides `SanitizedDatabaseUrl` and `SanitizedWebhookUrl` frozen dataclasses with factory methods that guarantee URLs cannot contain credentials when stored in the audit trail. Security-critical for SSRF prevention and secret leak prevention.
**Key dependencies:** Imports `urlparse`, `parse_qs`, `urlencode`, `urlunparse` from `urllib.parse`. Lazy-imports `_sanitize_dsn` from `elspeth.core.config`, `SecretFingerprintError` from `elspeth.core.config`, `get_fingerprint_key` and `secret_fingerprint` from `elspeth.core.security.fingerprint`. Consumed by `plugins/sinks/database_sink.py`, `contracts/results.py`, tests.
**Analysis depth:** FULL

## Summary

This is security-critical code responsible for ensuring secrets never reach the audit trail. The implementation is thorough with good coverage of query params, fragment params, and Basic Auth. However, there is one latent bug that would produce corrupted URLs when processing malformed URLs with credentials but no hostname. There are also missing entries in the SENSITIVE_PARAMS set that could allow secret leakage through less common parameter names. The code is well-tested (extensive test suite in `tests/core/security/test_url.py`) but the tests do not cover the hostname=None edge case.

## Critical Findings

### [Lines 235-238] hostname=None produces string "None" in reconstructed URL

**What:** When `has_basic_auth` is True but `parsed.hostname` is None (which happens for malformed URLs like `https://user:pass@/webhook`), the f-string at line 238 produces `netloc = f"{None}{port_str}"` which evaluates to the string `"None"`. The reconstructed URL would become `https://None/webhook` -- a syntactically valid URL pointing to a real (or resolvable) hostname.

**Why it matters:** This is both a data integrity issue and a potential security issue:
1. **Data integrity:** The audit trail would record a URL pointing to `None` as a hostname, which is incorrect and misleading.
2. **Security:** If the sanitized URL is later used for any purpose (logging, display, retry logic), it could resolve to a real DNS name `None` or `None.example.com`.
3. **Silent corruption:** The function returns successfully with a corrupted URL instead of raising an error.

**Evidence:**
```python
# Line 235-238
if parsed.hostname and ":" in parsed.hostname:
    netloc = f"[{parsed.hostname}]{port_str}"
else:
    netloc = f"{parsed.hostname}{port_str}"  # hostname is None -> "None"
```

Verified with Python's urlparse:
```python
>>> urlparse("https://user:pass@/webhook").hostname
None
>>> f"{None}"
'None'
```

The `parsed.hostname and ":" in parsed.hostname` guard at line 235 correctly skips the IPv6 branch when hostname is None (because `None` is falsy), but the else branch at line 238 still interpolates `None` as a string.

**Note:** While URLs of the form `https://user:pass@/webhook` are unusual, they can appear in misconfigured systems or through user error in pipeline configuration. The function should either raise a `ValueError` for URLs with auth but no hostname, or handle the None case explicitly.

## Warnings

### [Lines 32-57] SENSITIVE_PARAMS missing common cloud-specific parameter names

**What:** The `SENSITIVE_PARAMS` set covers common API authentication patterns but is missing several cloud-provider-specific sensitive parameter names that appear in real-world webhook URLs:

- `sas` / `sv` / `se` / `sp` / `ss` / `srt` (Azure SAS token components)
- `X-Amz-Security-Token` / `X-Amz-Credential` (AWS pre-signed URLs)
- `jwt` (JSON Web Tokens)
- `refresh_token` (OAuth refresh tokens)
- `code` (OAuth authorization codes)
- `private_token` (GitLab API)

**Why it matters:** If a pipeline uses Azure Blob Storage webhooks with SAS tokens or AWS S3 pre-signed URLs, the sensitive parameters would pass through unsanitized into the audit trail. The `signature` and `sig` params are included, which covers some Azure SAS scenarios, but the individual SAS components (`sv`, `se`, etc.) are not individually sensitive -- the `sig` parameter is the actual secret. This is partially mitigated.

**Evidence:**
```python
SENSITIVE_PARAMS = frozenset({
    "token", "api_key", "apikey", "key", "secret", "password", "auth",
    "access_token", "client_secret", "api_secret", "bearer",
    "signature", "sig",
    "authorization", "x-api-key",
    "credential", "credentials",
})
# Missing: jwt, refresh_token, code, private_token
```

### [Lines 204-206] get_fingerprint_key ValueError caught but mapped to have_key=False

**What:** The code catches `ValueError` from `get_fingerprint_key()` and maps it to `have_key = False`. This is the only place in the codebase where `get_fingerprint_key` failure is caught as `ValueError` rather than allowing the exception to propagate. The function then conditionally raises `SecretFingerprintError` based on `fail_if_no_key`.

**Why it matters:** This error translation is subtle. If `get_fingerprint_key()` starts raising different exception types for different failure modes (e.g., key exists but is empty, key is malformed), they would be silently swallowed. The broad `ValueError` catch could mask bugs in the fingerprint key configuration.

**Evidence:**
```python
try:
    get_fingerprint_key()
    have_key = True
except ValueError:
    have_key = False
```

### [Lines 60, 106] SanitizedDatabaseUrl and SanitizedWebhookUrl lack `slots=True`

**What:** Both dataclasses use `@dataclass(frozen=True)` without `slots=True`. Other frozen dataclasses in the contracts package (e.g., all event types in `events.py`) consistently use `@dataclass(frozen=True, slots=True)`.

**Why it matters:** This is a minor inconsistency. Without slots, each instance carries a `__dict__`, using slightly more memory. For URL objects that are created infrequently, this is negligible. However, it breaks the pattern established elsewhere in the contracts package.

## Observations

### [Lines 99-103] SanitizedDatabaseUrl.from_raw_url delegates to core.config._sanitize_dsn

The factory method imports and delegates to `_sanitize_dsn` from `elspeth.core.config`. This is a good pattern for reuse, but it means the database URL sanitization logic is split between two modules. The underscore prefix on `_sanitize_dsn` indicates it's a private function being used as a public API surface.

### [Lines 223-227] Case-sensitive key filtering after case-insensitive detection

The filtering at lines 224 and 227 uses `k.lower() in SENSITIVE_PARAMS`, which correctly handles case-insensitive matching. However, the original key casing is preserved in the non-sensitive params. This is correct behavior (preserving the original param name casing for non-sensitive params).

### [Lines 195-220] Fingerprint computation with sorted values is deterministic

The `sorted(sensitive_values)` at line 211 ensures deterministic fingerprints regardless of parameter order in the URL. This is good practice -- `?token=a&secret=b` and `?secret=b&token=a` produce the same fingerprint.

### [Lines 243-256] URL reconstruction with urlencode/urlunparse is correct

The reconstruction at lines 247-256 properly handles empty query strings and fragments (using conditional `urlencode` calls). The `doseq=True` parameter on `urlencode` correctly handles multi-valued query parameters (e.g., `?tag=a&tag=b`).

### Test coverage is comprehensive

The test file (`tests/core/security/test_url.py`) at 666 lines covers query params, fragment params, Basic Auth, IPv6, case insensitivity, empty values, fingerprint verification, and integration with ArtifactDescriptor. The only gap is the hostname=None edge case identified in the Critical finding.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Fix the hostname=None bug at line 238 -- either add a guard `if parsed.hostname is None: raise ValueError(...)` or handle it as `netloc = port_str` (empty hostname). Add a test for URLs with auth but no hostname. Consider adding `jwt`, `refresh_token`, and `private_token` to SENSITIVE_PARAMS.
**Confidence:** HIGH -- the hostname=None bug was verified with a live Python REPL. The SENSITIVE_PARAMS gap is a judgment call on coverage breadth.
