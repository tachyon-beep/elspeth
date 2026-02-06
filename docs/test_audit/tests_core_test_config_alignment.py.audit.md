# Test Audit: tests/core/test_config_alignment.py

**Lines:** 956
**Test count:** 32
**Audit status:** PASS

## Summary

This is an exemplary test file that addresses a critical bug (P2-2026-01-21: field orphaning). The tests verify that Settings fields are correctly wired to Runtime configurations, preventing silent configuration failures. The file is exceptionally well-documented with clear explanations of categories (WIRED, PENDING, INTERNAL), contains comprehensive alignment tests for all subsystems, and includes property-based testing with Hypothesis for edge case coverage.

## Findings

### 🔵 Info

1. **Lines 1-25: Excellent documentation** - The module docstring thoroughly explains the purpose, categories, and how to respond when tests fail. This is a model for test documentation.

2. **Lines 30-104: TestRetryConfigAlignment** - Tests the RetrySettings to RuntimeRetryConfig mapping including field name translations (initial_delay_seconds -> base_delay). Tests verify bidirectional coverage and that from_settings() maps all fields.

3. **Lines 106-157: TestConcurrencySettingsAlignment** - Tests are appropriately simple for this single-field Settings class. The test correctly verifies the field flows through to Orchestrator.

4. **Lines 159-208: TestRateLimitSettingsAlignment** - Verifies RateLimitRegistry can be created from settings via RuntimeRateLimitConfig. Properly cleans up resources in test.

5. **Lines 210-256: TestLandscapeSettingsAlignment** - Documents PENDING_FIELDS (enabled, backend) that exist but are not validated at runtime. This is valuable documentation.

6. **Lines 258-306: TestCheckpointSettingsAlignment** - Tests checkpoint config wiring including the frequency transformation logic.

7. **Lines 308-332: TestPayloadStoreSettingsAlignment** - Simple but complete coverage of all three fields.

8. **Lines 335-399: TestElspethSettingsAlignment** - Meta-test verifying all settings are categorized. This is a safety net that catches new uncategorized fields.

9. **Lines 409-526: TestRuntimeFieldOrigins (Reverse Orphan Detection)** - Tests the inverse of field orphaning: Runtime fields without Settings origins. This is thorough defensive testing.

10. **Lines 535-643: TestExplicitFieldMappings** - Explicit assertions on each field mapping with comments documenting the mapping direction. Excellent for maintainability.

11. **Lines 652-734: TestExponentialBaseRegression** - Specific regression tests for the P2-2026-01-21 bug. Tests verify the value flows through the entire chain and affects actual behavior.

12. **Lines 744-901: TestPropertyBasedRoundtrip** - Uses Hypothesis to generate many valid configurations and verify round-trip preservation. This is excellent for catching edge cases.

13. **Lines 910-956: TestSettingsToRuntimeMapping** - Meta-test verifying SETTINGS_TO_RUNTIME documentation matches reality.

### 🟡 Warning

1. **Lines 382-398: test_subsystem_settings_have_alignment_tests** - The comment mentions "(xfail - pending)" for concurrency and rate_limit, but the test does not actually use xfail markers. The comment appears stale since the wiring tests exist and pass. Consider updating the comment.

## Coverage Assessment

- **Forward orphan detection** (Settings -> Runtime): Comprehensive
- **Reverse orphan detection** (Runtime fields undocumented): Comprehensive
- **Field name mappings**: Explicit and documented
- **Regression testing**: Specific test for original bug
- **Property-based testing**: Covers all major config types
- **Meta-testing**: Verifies documentation matches code

## Verdict

**KEEP** - This is an exceptionally well-designed test file that serves as both tests and documentation. It prevents a class of bugs (field orphaning) that would otherwise go undetected until runtime. The combination of structural tests, explicit mapping tests, regression tests, and property-based tests provides defense in depth. One minor stale comment does not warrant changes.
