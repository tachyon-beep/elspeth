# Test Audit: tests/core/security/test_fingerprint_keyvault.py

**Lines:** 224
**Test count:** 17
**Audit status:** ISSUES_FOUND

## Summary

This test file documents and verifies a breaking change: the removal of automatic Key Vault lookup via environment variables in favor of YAML-based secrets configuration. The tests are well-structured and serve dual purpose as behavioral verification and migration documentation. However, there is significant duplication with `test_fingerprint.py`.

## Findings

### 🟡 Warning

1. **Lines 138-199 (TestSecretFingerprintFunction)**: This entire test class duplicates 7 tests from `test_fingerprint.py` exactly:
   - `test_fingerprint_returns_hex_string`
   - `test_fingerprint_is_deterministic`
   - `test_different_secrets_have_different_fingerprints`
   - `test_different_keys_produce_different_fingerprints`
   - `test_fingerprint_length_is_64_chars`
   - `test_fingerprint_golden_vector`
   - `test_fingerprint_without_key_uses_env_var`
   - `test_fingerprint_without_key_raises_if_env_missing`

   This duplication increases maintenance burden. Consider keeping these tests only in `test_fingerprint.py` since they test the same functionality.

### 🔵 Info

1. **Lines 1-12**: Good documentation header explaining the breaking change and what the tests verify. This serves as migration documentation.

2. **Lines 75-136 (TestOldKeyVaultEnvVarsNotRecognized)**: These tests are valuable as regression tests ensuring the old behavior is truly removed. They document the breaking change explicitly.

3. **Lines 209-224 (TestNoModuleLevelCache)**: Tests that env var changes are reflected immediately. This verifies the simplified implementation has no hidden caching complexity.

4. **Lines 39-40, 62-63, 94-95, 115-116, 195-196**: Multiple uses of `os.environ.pop(_ENV_VAR, None)` pattern inside `patch.dict` context. While functional, this is slightly awkward - using `monkeypatch` would be cleaner.

## Verdict

**KEEP** - The tests for the breaking change (TestFingerprintKeyEnvVarOnly, TestOldKeyVaultEnvVarsNotRecognized, TestNoModuleLevelCache) are valuable and should remain. However, the TestSecretFingerprintFunction class should be removed to eliminate duplication with test_fingerprint.py.
