# Test Bug Report: Fix weak assertions in fingerprint_keyvault

## Summary

- This test file documents and verifies a breaking change: the removal of automatic Key Vault lookup via environment variables in favor of YAML-based secrets configuration. The tests are well-structured and serve dual purpose as behavioral verification and migration documentation. However, there is significant duplication with `test_fingerprint.py`.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_core_security_test_fingerprint_keyvault.audit.md

## Test File

- **File:** `tests/core/security/test_fingerprint_keyvault`
- **Lines:** 224
- **Test count:** 17

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The tests for the breaking change (TestFingerprintKeyEnvVarOnly, TestOldKeyVaultEnvVarsNotRecognized, TestNoModuleLevelCache) are valuable and should remain. However, the TestSecretFingerprintFunction class should be removed to eliminate duplication with test_fingerprint.py.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/core/security/test_fingerprint_keyvault -v`

## Notes

- Source audit: `docs/test_audit/tests_core_security_test_fingerprint_keyvault.audit.md`
