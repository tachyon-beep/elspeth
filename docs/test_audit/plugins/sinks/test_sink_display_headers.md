# Test Audit: test_sink_display_headers.py

**File:** `tests/plugins/sinks/test_sink_display_headers.py`
**Lines:** 846
**Audit Date:** 2026-02-05
**Auditor:** Claude Opus 4.5

## Summary

Comprehensive tests for sink display header functionality including `display_headers`, `restore_source_headers`, and resume validation with header mapping. Covers both CSV and JSON sinks with good edge case coverage.

## Findings

### 1. Defects

None identified.

### 2. Overmocking

**SEVERITY: LOW**
- `MagicMock` used for Landscape in `restore_source_headers` tests. While appropriate for unit testing, there should also be integration tests with real Landscape (may exist elsewhere).

### 3. Missing Coverage

**SEVERITY: MEDIUM**
- No test for display header collision (two normalized fields mapping to same display name)
- Missing test for display headers with empty string values
- No test for `restore_source_headers` when source had no headers (e.g., headerless CSV)

**SEVERITY: LOW**
- No test for display headers with very long names
- Missing test for mixed case sensitivity in header mapping
- No test for unicode normalization differences (e.g., NFC vs NFD)

### 4. Tests That Do Nothing

None identified.

### 5. Inefficiency

**SEVERITY: MEDIUM**
- Significant fixture duplication across test classes (`ctx`, `output_path`, `sample_contract` appear multiple times)
- Similar test patterns repeated for CSV and JSON sinks - could use parametrization

### 6. Structural Issues

**SEVERITY: LOW**
- Very long file (846 lines) - consider splitting into:
  - `test_sink_display_headers_csv.py`
  - `test_sink_display_headers_json.py`
  - `test_sink_resume_validation.py`
- `TestFieldResolutionReverseMapping` (line 401) tests `FieldResolution` class which is from a different module - could be in a more appropriate test file

## Positive Observations

1. Excellent edge case coverage for special characters in headers (comma, quotes, newline)
2. Comprehensive resume validation testing with and without field resolution
3. Good testing of mutual exclusivity between `display_headers` and `restore_source_headers`
4. Tests verify both CSV-specific (column order) and JSON-specific (key names) behavior
5. Legacy compatibility properly tested alongside new header modes

## Recommendations

1. Extract common fixtures to conftest or use parametrization for CSV/JSON tests
2. Consider splitting into smaller, focused test files
3. Move `TestFieldResolutionReverseMapping` to appropriate test file
4. Add collision and edge case tests for display header mapping
5. Add integration test with real Landscape for `restore_source_headers`
