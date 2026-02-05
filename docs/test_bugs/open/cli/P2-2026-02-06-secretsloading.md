# Test Bug Report: Fix weak assertions in secrets_loading

## Summary

- This test file covers secret loading integration in the CLI, including Key Vault loading, env source, validation errors, and rejection of environment variable references in `vault_url`. The tests use mocking appropriately to avoid actual Key Vault calls while verifying the loading behavior. However, there are some assertions that could be more precise.

## Severity

- Severity: trivial
- Priority: P2
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/test_secrets_loading.audit.md

## Test File

- **File:** `tests/cli/test_secrets_loading`
- **Lines:** 214
- **Test count:** 7

## Findings

- **Line 50:**: The assertion `mock_loader.get_secret.assert_called_once_with("test-secret")` verifies the mock was called, but the test never checks that the secret value was actually used or injected into the environment. This tests that loading was attempted, not that loading succeeded and the result was used.
- **Lines 82-83:**: The assertion `assert "nonexistent-secret" in result.output or "Secret" in result.output` is very loose. The OR condition means either string matching would pass. A test for error handling should be more specific about the error message format.
- **Lines 134-135:**: The assertion `assert "HTTPS" in result.output or "secrets" in result.output.lower()` is loose. Since the test is specifically about HTTP vs HTTPS validation, checking for "HTTPS" alone would be more precise.
- **Lines 160-161:**: The assertion `assert "vault_url" in result.output.lower() or "secrets" in result.output.lower()` - again, the OR condition weakens the test. When testing for a missing required field, the error message should specifically mention that field.
- **Lines 181-186:**: The test `test_run_with_default_env_source_no_secrets_section` has a comment `# Should at least not fail on secrets loading (may fail elsewhere, but that's fine for this test)` - this is concerning because the test doesn't actually verify success; it only verifies the mock wasn't called. The pipeline might fail for unrelated reasons and the test would still pass.
- **Lines 104-108:**: The test `test_run_with_env_source_skips_keyvault` correctly verifies that `MockLoader.assert_not_called()` when source is `env`. This is a valid negative test.
- **Lines 212-214:**: The assertion `assert "${" in result.output or "VAR" in result.output or "variable" in result.output.lower()` uses three OR conditions, making it accept very different error messages. While flexible, this could pass for unrelated errors containing common words.


## Verdict Detail

**KEEP** - The tests cover important security integration behavior and the mocking approach is appropriate for avoiding actual Key Vault calls. The weak assertions should be tightened in a follow-up, but the tests do provide value in verifying the loading flow triggers correctly.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/cli/test_secrets_loading -v`

## Notes

- Source audit: `docs/test_audit/test_secrets_loading.audit.md`
