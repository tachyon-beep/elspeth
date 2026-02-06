# Bug Report: SanitizedWebhookUrl Leaves Fragment Tokens Unredacted

## Status: FIXED

**Fixed:** 2026-02-06
**Fixed by:** Claude Opus 4.5

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

## Fix Applied

### Code Changes

**File:** `src/elspeth/contracts/url.py`

1. **Parse fragment as query params** (line 156-158):
   ```python
   # Parse fragment as query params (e.g., #access_token=xxx&state=yyy)
   # SECURITY: OAuth implicit flow and some APIs put tokens in fragments
   fragment_params = parse_qs(parsed.fragment, keep_blank_values=True)
   ```

2. **Track sensitive fragment keys** (line 162):
   ```python
   has_sensitive_fragment_keys = any(k.lower() in SENSITIVE_PARAMS for k in fragment_params)
   ```

3. **Collect fragment sensitive values for fingerprinting** (lines 173-177):
   ```python
   # Check fragment params for sensitive keys
   for key, values in fragment_params.items():
       if key.lower() in SENSITIVE_PARAMS:
           # Only add non-empty values to fingerprint
           sensitive_values.extend(v for v in values if v)
   ```

4. **Gate early return on fragment keys** (lines 188-190):
   ```python
   # If no sensitive keys in query, fragment, or Basic Auth found, return URL unchanged
   if not has_sensitive_query_keys and not has_sensitive_fragment_keys and not has_basic_auth:
       return cls(sanitized_url=url, fingerprint=None)
   ```

5. **Strip sensitive fragment params** (lines 225-226):
   ```python
   # Remove sensitive fragment params
   sanitized_fragment_params = {k: v for k, v in fragment_params.items() if k.lower() not in SENSITIVE_PARAMS}
   ```

6. **Reconstruct sanitized fragment** (lines 241-243):
   ```python
   # Reconstruct fragment from sanitized params
   # Only include fragment if there are remaining params
   sanitized_fragment = urlencode(sanitized_fragment_params, doseq=True) if sanitized_fragment_params else ""
   ```

7. **Use sanitized fragment in URL reconstruction** (line 253):
   ```python
   sanitized_fragment,  # Previously: parsed.fragment
   ```

8. **Updated docstring** to document fragment handling.

### Tests Added

**File:** `tests/core/security/test_url.py`

Added `TestFragmentTokenSanitization` class with 15 comprehensive tests:

- `test_fragment_access_token_removed` - Basic fragment token stripping
- `test_fragment_token_removed` - Generic token param in fragment
- `test_fragment_with_multiple_params_strips_only_sensitive` - Selective stripping
- `test_fragment_and_query_both_sanitized` - Combined query + fragment secrets
- `test_fragment_fingerprint_matches_expected` - Verify HMAC correctness
- `test_fragment_and_query_fingerprint_combined` - Combined fingerprint
- `test_fragment_raises_when_no_key_production_mode` - Error path
- `test_fragment_dev_mode_sanitizes_without_fingerprint` - Dev mode
- `test_fragment_empty_value_strips_key` - Empty value handling
- `test_fragment_empty_does_not_trigger_error` - Empty value no error
- `test_fragment_case_insensitive` - Case insensitivity
- `test_non_sensitive_fragment_unchanged` - Non-sensitive preserved
- `test_plain_fragment_without_params_unchanged` - Plain anchor unchanged
- `test_oauth_implicit_flow_pattern` - Real-world OAuth URL

## Acceptance Criteria - VERIFIED

- [x] A fragment token (e.g., `#access_token=sk-abc`) is removed from `sanitized_url`.
- [x] A fingerprint is computed for fragment secret values when `ELSPETH_FINGERPRINT_KEY` is available.
- [x] `SecretFingerprintError` is raised in production mode when fragment secrets exist and no key is set.
- [x] Tests covering fragment sanitization pass.

## Tests

```bash
.venv/bin/python -m pytest tests/core/security/test_url.py -v
# Result: 70 passed in 0.53s
```

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:688-726`
