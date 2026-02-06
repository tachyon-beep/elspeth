# Test Audit: tests/core/test_config.py

**Lines:** 3106
**Test count:** 155
**Audit status:** ISSUES_FOUND

## Summary

This is a comprehensive and well-structured configuration test file covering ElspethSettings, Pydantic validation, secret fingerprinting, template file expansion, environment variable handling, and various configuration subsystems (gates, coalesce, checkpoints, rate limits, run modes). The tests are organized into logical test classes and follow good testing patterns. Minor issues include some code duplication and one test exhibiting redundant assertions, but overall the test suite is of high quality.

## Findings

### 🟡 Warning

1. **Duplicated assertions in `test_rate_limit_settings_default_requests_per_minute_must_be_positive` (lines 801-818)**
   - This test contains the exact same assertions twice: `RateLimitSettings(default_requests_per_minute=0)` and `RateLimitSettings(default_requests_per_minute=-1)` are each tested twice in sequence.
   - This appears to be a copy-paste error that should be cleaned up.

2. **Similar test patterns repeated across secret fingerprinting tests (lines 1711-2356)**
   - Many tests in `TestSecretFieldFingerprinting` follow nearly identical patterns:
     - `test_*_preserved_at_load_time` tests
     - `test_*_is_fingerprinted_in_resolve_config` tests
   - While each test is necessary, the repetition could potentially be refactored using pytest parametrization to reduce boilerplate. However, the current explicit approach is more readable and maintainable for such critical security functionality.

3. **Repeated validation error tests for CoalesceSettings (lines 1560-1584)**
   - `test_coalesce_settings_timeout_negative_rejected` and `test_coalesce_settings_timeout_must_be_positive` both test that timeout must be positive (one with 0, one with -1).
   - Similarly, `test_coalesce_settings_quorum_count_negative_rejected` and `test_coalesce_settings_quorum_count_must_be_positive` are redundant.
   - These could be consolidated using parametrized tests.

### 🔵 Info

1. **Large file size (3106 lines, 155 tests)**
   - While the file is large, it is well-organized into 30+ test classes with clear naming conventions.
   - The structure makes it easy to navigate and maintain.
   - Splitting is not recommended as the current organization groups related configuration tests logically.

2. **Good regression test coverage**
   - Several tests explicitly document bug IDs they're preventing (e.g., P2-2026-02-02, gate-route-destination-name-validation-mismatch).
   - This is excellent practice for maintaining test intent.

3. **Internal function testing (lines 2076-2143, 2262-2356)**
   - Tests for internal functions like `_fingerprint_secrets`, `_sanitize_dsn`, `_expand_template_files`, `_expand_env_vars`, `_fingerprint_config_for_audit`.
   - Testing internal functions directly is acceptable here as they represent critical security and configuration processing logic.

4. **PluginConfig tests at end of file (lines 3049-3097)**
   - `TestPluginConfigSchemaValidation` tests `PluginConfig.from_dict` which lives in `plugins/config_base.py`, not `core/config.py`.
   - Consider moving these tests to a more appropriate location (e.g., `tests/plugins/test_config_base.py`), though co-location is not incorrect.

5. **Import pattern: local imports inside test methods**
   - All tests import from `elspeth.core.config` inside the test methods rather than at module level.
   - This is a deliberate pattern that helps isolate tests and is acceptable.

## Verdict

**KEEP** - This is a high-quality, comprehensive test suite for configuration validation. The minor issues (duplicated assertions, potential parametrization opportunities) do not warrant a rewrite. The test coverage is thorough, the organization is clear, and the tests serve their purpose well. The duplicated assertions in `test_rate_limit_settings_default_requests_per_minute_must_be_positive` should be fixed, but this is a trivial cleanup.
