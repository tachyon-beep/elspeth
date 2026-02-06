# Test Audit: tests/plugins/azure/test_blob_source.py

**Auditor:** Claude Code Audit
**Date:** 2026-02-05
**Test File:** `/home/john/elspeth-rapid/tests/plugins/azure/test_blob_source.py`
**Lines:** 881

## Summary

This file provides comprehensive unit tests for `AzureBlobSource`, covering config validation, CSV/JSON/JSONL loading, field normalization, schema validation, error handling, auth methods, and lifecycle management. The test structure mirrors `test_blob_sink.py` for consistency.

## Findings

### 1. GOOD: Consistent Mocking Strategy with Sink Tests

**Location:** Lines 40-44 (`mock_blob_client` fixture)

```python
@pytest.fixture
def mock_blob_client() -> Generator[MagicMock, None, None]:
    """Create a mock blob client for testing."""
    with patch("elspeth.plugins.azure.blob_source.AzureBlobSource._get_blob_client") as mock:
        yield mock
```

The fixture patches at the same abstraction level as the sink tests, maintaining consistency.

### 2. ISSUE: Fixture Returns Different Mock Type

**Severity:** Low
**Category:** Inconsistency

**Location:** Line 40 vs test_blob_sink.py Line 39

The source tests mock `_get_blob_client` (returns blob client), while sink tests mock `_get_container_client` (returns container client). This is correct for each plugin, but the fixture names don't match:
- `mock_blob_client` for source
- `mock_container_client` for sink

This is semantically correct but worth noting for maintainability.

### 3. GOOD: Comprehensive CSV Loading Tests

**Location:** Lines 209-305 (`TestAzureBlobSourceCSV`)

Tests cover:
- Basic CSV loading with headers
- Custom delimiter
- Without header row (numeric column names)
- Non-UTF8 encoding (latin-1)
- Field normalization (matching CSVSource behavior)
- Field mapping
- Error when normalize_fields conflicts with has_header=False

### 4. ISSUE: JSON Data Type Inconsistency

**Severity:** Low
**Category:** Clarity

**Location:** Lines 310-324 (`test_load_json_from_blob`)

```python
assert rows[0].row == {"id": 1, "name": "alice"}
```

The test expects integer `id` (correct for JSON). However, CSV tests expect string `id`:

```python
assert rows[0].row == {"id": "1", "name": "alice", "value": "100"}
```

This is correct behavior (JSON preserves types, CSV doesn't), but a comment explaining this would help readers understand the difference is intentional.

### 5. GOOD: JSONL Malformed Line Handling Tests

**Location:** Lines 398-456

Tests verify both quarantine and discard modes for malformed JSONL lines:

```python
def test_jsonl_malformed_line_quarantined_not_crash(...)
def test_jsonl_malformed_line_with_discard_mode(...)
```

These tests verify the source follows the Three-Tier Trust Model:
- External data (JSONL content) is zero trust
- Malformed lines are quarantined/discarded, not crashed

### 6. ISSUE: Quarantine Error Message Assertions May Be Brittle

**Severity:** Low
**Category:** Fragility

**Location:** Lines 426-429

```python
assert results[1].quarantine_error is not None
assert "JSON parse error" in results[1].quarantine_error
assert "line 2" in results[1].quarantine_error
```

These assertions depend on exact error message wording. If the error message changes (e.g., "JSON parse error" -> "Invalid JSON"), tests fail.

**Recommendation:** Consider asserting on presence of error rather than exact wording, or use constants for error messages.

### 7. GOOD: Schema Validation Tests

**Location:** Lines 458-519 (`TestAzureBlobSourceValidation`)

Tests verify quarantine behavior:
- Invalid rows are quarantined with error info
- Original values preserved in quarantined rows
- Discard mode silently drops invalid rows

### 8. GOOD: BUG Reference Tests

**Location:** Lines 559-607

```python
def test_csv_parse_error_quarantines(self, mock_blob_client: MagicMock, ctx: PluginContext) -> None:
    """BUG-BLOB-01: CSV parse errors quarantine instead of crashing."""
```

Tests reference specific bug IDs (BUG-BLOB-01), making it clear they're regression tests for past issues.

### 9. ISSUE: Weak Assertion in CSV Parse Error Test

**Severity:** Medium
**Category:** Test Weakness

**Location:** Lines 577-583

```python
# Should NOT raise - should quarantine instead
rows = list(source.load(ctx))
# Pipeline continues (doesn't crash)
# Note: With on_bad_lines="warn", pandas may parse some rows or quarantine the whole file
# Either way, we should not crash
assert isinstance(rows, list)  # Got results, not a crash
```

The assertion `isinstance(rows, list)` is always true if the function completes without raising. This doesn't verify the quarantine behavior occurred.

**Recommendation:** Assert that rows contains either quarantined items or is empty with specific reasons.

### 10. ISSUE: Similar Weak Assertion

**Severity:** Medium
**Category:** Test Weakness

**Location:** Lines 602-607

```python
rows = list(source.load(ctx))
# Should get one quarantined "row" representing the unparseable blob
assert len(rows) >= 0  # Either empty or quarantined row
# No crash = success
```

`len(rows) >= 0` is always true for any list. This assertion provides no validation.

**Recommendation:** The test should verify specific quarantine behavior (e.g., all rows are quarantined, error messages reference parse failure).

### 11. ISSUE: Internal Attribute Access in Lifecycle Test

**Severity:** Low
**Category:** Test Fragility

**Location:** Lines 619-629

```python
source.close()
assert source._blob_client is None
```

Same issue as in sink tests - testing private attributes couples tests to implementation.

### 12. GOOD: Auth Method Tests

**Location:** Lines 649-789 (`TestAzureBlobSourceAuthMethods`)

Comprehensive tests for all auth methods and error cases, mirroring sink auth tests for consistency.

### 13. GOOD: Auth Client Creation Tests

**Location:** Lines 792-881 (`TestAzureBlobSourceAuthClientCreation`)

Tests verify correct Azure SDK credential usage with proper `pytest.importorskip()` for optional dependency.

### 14. MINOR: Unused ctx Parameter

**Severity:** Low
**Category:** Inefficiency

**Location:** Lines 806, 834

Same issue as sink tests - `ctx: PluginContext` parameter passed but unused in auth client creation tests.

## Test Path Integrity

**Status:** PASS

This file tests the `AzureBlobSource` plugin directly using production classes. No manual graph construction or test path integrity violations.

## Recommendations

1. **Fix weak assertions** in CSV parse error tests (lines 583, 606) - these effectively test nothing
2. **Add comments** explaining JSON vs CSV type preservation differences
3. **Remove unused ctx parameters** or document why they're needed
4. **Test observable behavior** instead of private attributes in lifecycle tests
5. **Consider error message constants** to reduce assertion fragility

## Overall Assessment

**Quality:** Good
**Coverage:** Comprehensive
**Risk Level:** Medium (due to weak assertions in error handling tests)

The test file provides thorough coverage of the source plugin, but two tests (lines 559-607) have assertions that don't actually verify the intended behavior. These should be fixed to ensure quarantine behavior is properly tested.
