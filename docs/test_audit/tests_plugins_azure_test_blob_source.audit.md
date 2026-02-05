# Test Audit: tests/plugins/azure/test_blob_source.py

**Lines:** 881
**Test count:** 51
**Audit status:** PASS

## Summary

This is a comprehensive test file for `AzureBlobSource` covering configuration validation, CSV/JSON/JSONL loading, field normalization, schema validation with quarantining, error handling, lifecycle methods, and authentication methods. The tests are well-organized into logical classes and use appropriate mocking to isolate the source from actual Azure SDK calls. The tests demonstrate good coverage of edge cases including malformed data quarantining.

## Findings

### 🔵 Info

1. **Lines 47-107 - Well-designed test helper**: The `make_config()` helper function mirrors the sink's helper, providing consistency across the test suite. It properly handles all authentication options with sensible defaults.

2. **Lines 269-287 - Field normalization coverage**: Tests verify the `normalize_fields` feature and the `get_field_resolution()` method, which is important for header restoration in sinks. The resolution version ("1.0.0") is also verified.

3. **Lines 398-456 - JSONL malformed line handling**: Excellent test coverage for malformed JSONL lines with both quarantine and discard modes. Tests verify that valid rows before and after malformed lines are processed correctly.

4. **Lines 559-607 - CSV parse error handling**: Tests for BUG-BLOB-01 verify that CSV parse errors quarantine rows instead of crashing the pipeline. This is important for the "zero trust" tier 3 data handling principle.

5. **Lines 113-117 - Protocol compliance test uses hasattr**: Line 117 uses `hasattr(source, "output_schema")` which is appropriate here since this is testing protocol compliance (checking interface existence).

6. **Lines 792-881 - Auth client creation tests**: Mirror the sink's auth tests, ensuring consistency. The conditional skip fixture pattern is used correctly.

### 🟡 Warning

1. **Lines 632-646 - Test mocks the method it's testing**: Similar to the sink file, this test patches `source._get_blob_client` to raise ImportError but doesn't test the actual import error handling path. It only verifies that an ImportError propagates. Consider documenting this as a "propagation test".

2. **Lines 585-607 - Weak assertions**: The test `test_csv_structural_failure_quarantines_blob` has a weak assertion (`assert len(rows) >= 0`). While the comment explains the intent ("No crash = success"), this could be strengthened to verify specific behavior (e.g., that a quarantined row is returned).

## Verdict

**KEEP** - This is a high-quality, comprehensive test file that covers the full range of `AzureBlobSource` functionality. The tests are well-organized, properly mocked, and demonstrate good coverage of edge cases and error scenarios. The two warnings are minor and don't significantly impact test quality.
