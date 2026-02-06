# Test Audit: tests/plugins/sources/test_json_source.py

**Batch:** 137
**File:** tests/plugins/sources/test_json_source.py (901 lines)
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file provides comprehensive tests for the JSONSource plugin, covering basic functionality, configuration validation, quarantine handling, parse error handling, non-finite constant rejection, and data_key structural errors. The tests are well-organized into logical test classes with clear documentation of the bugs they're designed to catch.

**Overall Assessment:** EXCELLENT - Thorough coverage with good regression tests

## Findings

### 1. Duplicate ctx Fixture Definition [INEFFICIENCY]

**Severity:** Low
**Location:** Lines 21-23, 282-285, 406-408, 568-572, 742-744

**Issue:** The `ctx` fixture is defined identically in five separate test classes:
- `TestJSONSource` (line 21-23)
- `TestJSONSourceQuarantineYielding` (line 282-285)
- `TestJSONSourceParseErrors` (line 406-408)
- `TestJSONSourceNonFiniteConstants` (line 568-572)
- `TestJSONSourceDataKeyStructuralErrors` (line 742-744)

**Evidence:**
```python
@pytest.fixture
def ctx(self) -> PluginContext:
    """Create a minimal plugin context."""
    return PluginContext(run_id="test-run", config={})
```

**Recommendation:** Move the `ctx` fixture to module level or use a `conftest.py` file.

### 2. Excellent Non-Finite Constant Testing [POSITIVE]

**Location:** Lines 557-726

**Observation:** Comprehensive tests for NaN/Infinity rejection per canonical JSON policy:

```python
def test_jsonl_nan_constant_quarantined_not_crash(self, tmp_path: Path, ctx: PluginContext) -> None:
    """JSONL with NaN constant is quarantined at parse time.

    NaN is a non-standard JSON constant that Python's json module accepts
    by default. It must be rejected at the source boundary to prevent
    downstream crashes in canonical hashing.
    """
```

Tests cover:
- NaN in JSONL
- Infinity and -Infinity in JSONL
- NaN in JSON array format
- Discard mode for non-finite values
- Raw line preservation in quarantined rows

### 3. Good Data Key Structural Error Testing [POSITIVE]

**Location:** Lines 729-901

**Observation:** Thorough testing of data_key error handling:

```python
def test_data_key_on_list_root_quarantined_not_crash(self, tmp_path: Path, ctx: PluginContext) -> None:
    """data_key configured but JSON root is a list - quarantine, not TypeError.

    This tests the case where an API changes from returning {results: [...]}
    to returning [...] directly. Should quarantine gracefully.
    """
```

Tests cover:
- data_key on list root (expects object)
- Missing data_key in object
- data_key extracts non-list value
- Discard mode for structural errors
- Validation error logging

### 4. Excellent Parse Error Handling Tests [POSITIVE]

**Location:** Lines 399-555

**Observation:** Good coverage of JSON parse error handling:

```python
def test_jsonl_malformed_line_quarantined_not_crash(self, tmp_path: Path, ctx: PluginContext) -> None:
    """Malformed JSONL line is quarantined, not crash the pipeline.

    This is the core bug: json.JSONDecodeError should be caught and
    the row quarantined, allowing subsequent valid lines to process.
    """
```

Tests verify:
- Malformed JSONL lines don't crash the pipeline
- Valid rows after malformed rows are still processed
- Raw line data is preserved in quarantined rows
- Discard mode works for parse errors

### 5. Test Assertion Could Be Fragile [STRUCTURAL ISSUE]

**Severity:** Low
**Location:** Lines 455, 620, 652

**Issue:** Some assertions rely on specific error message content which could break if messages change:

```python
assert "JSON" in quarantined.quarantine_error or "json" in quarantined.quarantine_error

assert "NaN" in quarantined.quarantine_error or "non-standard" in quarantined.quarantine_error.lower()
```

**Recommendation:** These are acceptable as they're testing that the error message contains relevant information for audit traceability. However, consider using more robust patterns or extracting message constants.

### 6. Good Documentation of Bug References [POSITIVE]

**Location:** Lines 564-567, 734-738

**Observation:** Tests document the specific bugs they're designed to catch:

```python
"""Tests for JSON source rejection of NaN/Infinity constants.

Bug: P2-2026-01-21-jsonsource-nonfinite-constants-allowed
"""
```

### 7. Missing Test for Encoding Errors [MISSING COVERAGE]

**Severity:** Low
**Location:** General

**Issue:** No test for what happens when the file contains bytes that can't be decoded with the specified encoding.

**Recommendation:** Add test for encoding errors (e.g., reading a UTF-16 file with UTF-8 encoding).

### 8. Missing Test for Empty JSON Array [MISSING COVERAGE]

**Severity:** Low
**Location:** General

**Issue:** No explicit test for an empty JSON array file `[]`.

**Evidence:** Implementation handles this case (empty array yields no rows), but there's no explicit test.

**Recommendation:** Add test verifying `[]` yields no rows without error.

### 9. Good Log Capture Test [POSITIVE]

**Location:** Lines 869-901

**Observation:** Tests verify that validation errors are logged when Landscape isn't connected:

```python
def test_data_key_structural_error_logs_validation_error(
    self, tmp_path: Path, ctx: PluginContext, caplog: pytest.LogCaptureFixture
) -> None:
    """Structural errors are recorded via ctx.record_validation_error().

    Without a Landscape connection, PluginContext logs a warning instead
    of persisting. This test verifies the recording path is called.
    """
```

### 10. Excellent Three-Tier Trust Model Alignment [POSITIVE]

**Location:** Throughout

**Observation:** Tests consistently reference and verify the Three-Tier Trust Model:

```python
def test_non_array_json_quarantined(self, tmp_path: Path, ctx: PluginContext) -> None:
    """Non-array JSON is quarantined per Three-Tier Trust Model.

    External data (Tier 3) with wrong structure should be quarantined,
    not raise exceptions. This allows audit trail to record the failure.
    """
```

## Missing Coverage Analysis

### Recommended Additional Tests

1. **Empty JSON array file** - Test `[]` yields no rows
2. **Encoding errors** - Test file with wrong encoding
3. **Very large JSON files** - Performance/memory tests
4. **Deeply nested data_key** - Test data_key like "results.items.data"
5. **Unicode in field names** - Test JSON with Unicode keys
6. **Duplicate keys in JSON object** - Test behavior when JSON has duplicate keys

## Verdict

**Status:** PASS - Excellent

This is a comprehensive test file with excellent coverage of edge cases, error handling, and security concerns (non-finite constants). The tests are well-documented with clear bug references and alignment with CLAUDE.md principles.

## Recommendations Priority

1. **Low:** Consolidate duplicate `ctx` fixture definitions
2. **Low:** Add test for empty JSON array `[]`
3. **Low:** Add test for encoding errors
4. **Low:** Consider testing deeply nested data_key paths
