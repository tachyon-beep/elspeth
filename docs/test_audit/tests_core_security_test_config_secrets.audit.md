# Test Audit: tests/core/security/test_config_secrets.py

**Lines:** 618
**Test count:** 20
**Audit status:** PASS

## Summary

This test file provides comprehensive coverage of the `load_secrets_from_config` function and related CLI helper `_load_settings_with_secrets`. Tests are well-organized into logical classes covering env source, keyvault source, error handling, edge cases, idempotency, and CLI integration. The mocking strategy is appropriate for Azure SDK interactions without overmocking.

## Findings

### 🔵 Info

1. **Lines 106-110**: Test imports `time` inside the test function rather than at module level. This is a minor style inconsistency but does not affect correctness.

2. **Lines 267-282**: The `test_azure_sdk_not_installed_shows_helpful_error` test uses a complex `builtins.__import__` patch. This is fragile and may break if the import structure changes, but it's the only way to test missing dependency behavior.

3. **Lines 411-415**: Comment in `test_load_secrets_idempotent` explains why Key Vault is called twice. This is good documentation of expected behavior that might otherwise seem like a bug.

4. **Lines 571-618**: The `test_load_settings_with_secrets_raises_on_missing_secret` test imports `SecretNotFoundError` from a different module than the exception raised (`SecretLoadError`). This correctly tests the exception wrapping behavior.

## Verdict

**KEEP** - This is a well-structured, comprehensive test file with meaningful tests that verify real behavior. Tests cover happy paths, error conditions, edge cases (unicode, multiline, long secrets), and integration with the CLI layer. The mocking is appropriately scoped to external Azure dependencies.
