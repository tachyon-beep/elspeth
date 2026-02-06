# Test Audit: tests/engine/test_retry_policy.py

**Lines:** 226
**Test count:** 13 test methods across 2 test classes
**Audit status:** PASS

## Summary

This test file provides comprehensive validation of RetryPolicy TypedDict and schema alignment between RetrySettings, RuntimeRetryConfig, and RetryPolicy. The TestRetrySchemaAlignment class is particularly valuable for catching "config field orphaning" bugs (like P2-2026-01-21) at commit time. Tests use structural introspection to verify field mappings stay synchronized across configuration layers.

## Findings

### 🔵 Info

1. **Lines 10-25: test_retry_policy_schema** - Good structural test that verifies `__total__` is False (all fields optional) and exact field set. Uses `set()` comparison for order-independent verification.

2. **Lines 52-62: test_retry_policy_partial** - Verifies partial specification works correctly with defaults filled in. Tests ALL optional fields have defaults, not just a subset.

3. **Lines 73-99: Clamping tests** - Tests `test_retry_policy_exponential_base_clamped`, `test_retry_policy_exponential_base_exactly_one_clamped`, and `test_retry_policy_exponential_base_negative_clamped` verify input sanitization for invalid exponential_base values. Good edge case coverage.

4. **Lines 102-181: TestRetrySchemaAlignment class** - This is the crown jewel of the file. Uses structural introspection (`__dataclass_fields__`, `model_fields`, `__annotations__`) to verify:
   - POLICY_DEFAULTS matches RuntimeRetryConfig fields
   - RetrySettings fields map to RuntimeRetryConfig
   - Config doesn't have unexpected fields
   - RetryPolicy TypedDict matches Config

5. **Lines 114-120: Field mapping documentation** - The `FIELD_MAPPINGS` and `CONFIG_INTERNAL_ONLY` class variables document known name differences, making the tests maintainable.

6. **Lines 122-140: test_policy_defaults_matches_config_fields** - Detects missing/extra fields with clear error messages that tell developers exactly what to fix.

7. **Lines 202-226: test_from_settings_maps_all_fields_with_sentinel_values** - Uses distinctive non-default values (99, 9.9) to detect "forgot to map, used default instead" bugs. This would have caught P2-2026-01-21.

## Verdict

**KEEP** - Excellent defensive test file that:
- Prevents config field orphaning at commit time
- Uses structural introspection for maintainable alignment checks
- Documents known field mappings explicitly
- Uses sentinel values to detect mapping omissions
- Provides clear, actionable error messages
- Directly addresses lessons from P2-2026-01-21 bug
