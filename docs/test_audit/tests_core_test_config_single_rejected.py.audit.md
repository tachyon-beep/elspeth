# Test Audit: tests/core/test_config_single_rejected.py

**Lines:** 65
**Test count:** 5
**Audit status:** PASS

## Summary

This is a focused regression test file that verifies the deprecated 'single' output mode is properly rejected with a helpful migration hint. The tests are concise, well-targeted, and serve an important purpose: ensuring users migrating from an older API get clear guidance. Tests verify both rejection of invalid values and acceptance of valid alternatives.

## Findings

### 🔵 Info

1. **Lines 1-7: Clear purpose** - The docstring and imports clearly indicate this file tests deprecation behavior for output_mode='single'.

2. **Lines 9-21: test_aggregation_config_rejects_single_mode** - Verifies that 'single' mode raises ValidationError and that the error message contains both "single" and "transform" (migration hint). This is a well-designed test that verifies not just the error but also the user guidance.

3. **Lines 24-32: test_aggregation_config_accepts_transform_mode** - Positive test confirming the replacement value is accepted.

4. **Lines 35-43: test_aggregation_config_accepts_passthrough_mode** - Confirms the other valid output mode is accepted.

5. **Lines 46-53: test_aggregation_config_default_is_transform** - Verifies the default value is 'transform', not the deprecated 'single'.

6. **Lines 56-65: test_aggregation_config_expected_output_count** - Tests that expected_output_count field can be set when using transform mode. This appears to test a related but distinct feature.

### 🟡 Warning

1. **Potential overlap with test_config_aggregation.py** - Tests 2-5 in this file overlap significantly with tests in `test_config_aggregation.py` (specifically: test_aggregation_settings_default_output_mode, test_aggregation_settings_passthrough_mode, test_aggregation_settings_transform_mode). The unique value this file provides is test 1 (rejection of 'single' mode with migration hint).

## Coverage Assessment

- **Deprecated mode rejection**: Covered with error message verification
- **Migration hint in error**: Covered
- **Valid alternatives**: Covered
- **Default value**: Covered

## Verdict

**KEEP** - While there is some overlap with test_config_aggregation.py, this file serves a distinct purpose: it specifically documents and tests the deprecation of 'single' mode with user-friendly migration guidance. The explicit focus on the deprecation scenario makes it valuable as a regression test. The overlap is minor (4 simple assertions) and does not justify consolidation given the clear purpose separation.
