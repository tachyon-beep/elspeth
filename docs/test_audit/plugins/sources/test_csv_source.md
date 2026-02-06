# Test Audit: tests/plugins/sources/test_csv_source.py

**Batch:** 136
**File:** tests/plugins/sources/test_csv_source.py (709 lines)
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file provides comprehensive tests for the CSVSource plugin, covering basic functionality, configuration validation, quarantine handling, and field normalization. The tests are well-structured with good coverage of edge cases including malformed CSV rows, empty files, and field count mismatches.

**Overall Assessment:** GOOD - Minor improvements possible

## Findings

### 1. Duplicate ctx Fixture Definition [INEFFICIENCY]

**Severity:** Low
**Location:** Lines 27-29, 211-214, 471-473

**Issue:** The `ctx` fixture is defined identically in three separate test classes:
- `TestCSVSource` (line 27-29)
- `TestCSVSourceQuarantineYielding` (line 211-214)
- `TestCSVSourceFieldNormalization` (line 471-473)

**Evidence:**
```python
@pytest.fixture
def ctx(self) -> PluginContext:
    """Create a minimal plugin context."""
    return PluginContext(run_id="test-run", config={})
```

**Recommendation:** Move the `ctx` fixture to module level or use a `conftest.py` file to avoid repetition.

### 2. Missing Test for Row-Level Line Numbers in Multiline Fields [MISSING COVERAGE]

**Severity:** Low
**Location:** `test_csv_error_handling_defensive` (lines 344-383)

**Issue:** The test verifies multiline quoted fields work correctly, but doesn't verify that `__line_number__` is accurate when a multiline field spans multiple physical lines. The `reader.line_num` tracking in the implementation may behave differently for multiline fields.

**Evidence:**
```python
# Tests multiline field but doesn't check line number tracking
csv_file.write_text('id,name\n1,alice\n2,"bob\nsmith"\n3,carol\n')
```

**Recommendation:** Add assertions checking that line numbers are accurately tracked for rows following multiline fields.

### 3. hasattr Usage May Violate No-Bug-Hiding Policy [STRUCTURAL ISSUE]

**Severity:** Low
**Location:** Line 44

**Issue:** Uses `hasattr()` to check for `output_schema`:
```python
assert hasattr(source, "output_schema")
```

Per CLAUDE.md, `hasattr()` is discouraged as a defensive pattern. However, in this test context, it's checking a protocol requirement, which is a legitimate use.

**Recommendation:** Consider using direct attribute access with type assertion instead:
```python
assert isinstance(source.output_schema, type)
assert issubclass(source.output_schema, PluginSchema)
```

### 4. Good Coverage of Edge Cases [POSITIVE]

**Location:** `TestCSVSourceQuarantineYielding` class (lines 208-465)

**Observation:** Excellent coverage of edge cases including:
- Empty rows being skipped (line 431)
- Malformed CSV rows with extra/fewer columns
- Skip rows line number accuracy
- Multiline quoted fields

### 5. Good Regression Test Documentation [POSITIVE]

**Location:** Multiple tests

**Observation:** Tests document their purpose as regression tests with clear explanations:
```python
def test_skip_rows_line_numbers_are_accurate(self, tmp_path: Path, ctx: PluginContext) -> None:
    """Line numbers in error messages should be accurate when skip_rows > 0.

    Regression test for P2 bug where line numbers were off by skip_rows amount.
    """
```

### 6. Good Contract Test Coverage [POSITIVE]

**Location:** `test_field_resolution_stored_for_audit` (lines 557-581)

**Observation:** Tests properly verify that field resolution is stored for audit trail, testing the `_field_resolution` attribute with its `resolution_mapping` and `normalization_version`.

## Missing Coverage Analysis

### Recommended Additional Tests

1. **Test for BOM handling in CSV files** - While field normalization handles BOM in headers, there's no test for a CSV file that starts with a UTF-8 BOM (`\ufeff`).

2. **Test for concurrent access** - No tests verify thread-safety when multiple threads call `load()` (though sources are typically single-threaded).

3. **Test for very large CSV files** - No memory/performance tests for large files.

4. **Test for get_field_resolution() before load()** - The `get_field_resolution()` method returns `None` before `load()` is called, but this isn't explicitly tested.

## Verdict

**Status:** PASS

The test file provides solid coverage of CSVSource functionality with well-documented regression tests. The main improvement opportunity is consolidating duplicate fixtures. No critical defects found.

## Recommendations Priority

1. **Low:** Consolidate duplicate `ctx` fixture definitions
2. **Low:** Add test for `get_field_resolution()` return value before `load()` is called
3. **Low:** Consider testing BOM handling at file level (not just header normalization)
