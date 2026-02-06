# Test Audit: tests/plugins/sources/test_csv_source_contract.py

**Batch:** 136
**File:** tests/plugins/sources/test_csv_source_contract.py (196 lines)
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file tests the schema contract integration for CSVSource, verifying that sources properly create and propagate contracts to PipelineRow objects. The tests cover both OBSERVED and FIXED schema modes, contract locking behavior, and field resolution integration.

**Overall Assessment:** GOOD - Well-focused contract tests

## Findings

### 1. Mock Context May Hide Issues [OVERMOCKING]

**Severity:** Medium
**Location:** Lines 27-35

**Issue:** The `mock_context` fixture creates a minimal mock that doesn't actually implement `PluginContext`:

```python
@pytest.fixture
def mock_context() -> PluginContext:
    """Create a mock plugin context."""

    class MockContext:
        def record_validation_error(self, **kwargs: object) -> None:
            pass

    return MockContext()  # type: ignore[return-value]
```

This mock:
1. Uses `type: ignore` to suppress type errors
2. Has a no-op `record_validation_error` that discards validation errors
3. Doesn't implement other PluginContext methods

**Impact:** Tests may pass even if CSVSource calls methods that don't exist on MockContext.

**Recommendation:** Use the real `PluginContext` as in `test_csv_source.py`:
```python
@pytest.fixture
def ctx() -> PluginContext:
    return PluginContext(run_id="test-run", config={})
```

### 2. Good Contract Lifecycle Testing [POSITIVE]

**Location:** Lines 41-58

**Observation:** Properly tests that OBSERVED contracts are locked after consuming the iterator:

```python
def test_dynamic_schema_creates_observed_contract(self, temp_csv: Path, mock_context: PluginContext) -> None:
    # ...
    # Consume iterator to populate contract
    list(source.load(mock_context))

    contract = source.get_schema_contract()
    assert contract is not None
    assert contract.mode == "OBSERVED"
    assert contract.locked is True
```

### 3. Good Edge Case: All Rows Quarantined [POSITIVE]

**Location:** Lines 166-196

**Observation:** Tests the important edge case where all rows are quarantined but contract should still be locked:

```python
def test_empty_source_locks_contract(self, tmp_path: Path, mock_context: PluginContext) -> None:
    """Contract is locked even if all rows are quarantined."""
    # ...
    rows = list(source.load(mock_context))

    # All rows should be quarantined (id field not coercible to int)
    assert all(r.is_quarantined for r in rows)

    # Contract should still be locked
    contract = source.get_schema_contract()
    assert contract is not None
    assert contract.locked is True
```

### 4. CSV File with Inconsistent Quoting [POTENTIAL ISSUE]

**Severity:** Low
**Location:** Lines 117-124

**Issue:** The test CSV uses inconsistent quoting which may not reflect typical real-world data:

```python
csv_file.write_text(
    dedent("""\
    'Amount USD',Customer ID
    100,C001
""")
)
```

The header `'Amount USD'` has single quotes but `Customer ID` doesn't. This tests a specific edge case but the behavior depends on whether the quotes are part of the header name or delimiters.

**Observation:** This is actually testing that single quotes in the header are preserved in `original_name`, which is correct behavior.

### 5. Missing Test for Contract Propagation Through Multiple Rows [MISSING COVERAGE]

**Severity:** Low
**Location:** General

**Issue:** Tests verify that SourceRow has contract after consuming all rows, but don't verify that the same contract instance is used for all rows:

```python
# Current test
for row in rows:
    if not row.is_quarantined:
        assert row.contract is not None
        assert row.contract.locked is True

# Would be stronger
contracts = [row.contract for row in rows if not row.is_quarantined]
assert len(set(id(c) for c in contracts)) == 1  # All same instance
```

**Recommendation:** Add assertion that all valid rows share the same contract instance (or verify this is intentional design).

### 6. Good PipelineRow Conversion Test [POSITIVE]

**Location:** Lines 96-114

**Observation:** Tests the important conversion path from SourceRow to PipelineRow:

```python
def test_source_row_converts_to_pipeline_row(self, temp_csv: Path, mock_context: PluginContext) -> None:
    """SourceRow can convert to PipelineRow."""
    # ...
    pipeline_row = source_row.to_pipeline_row()

    assert isinstance(pipeline_row, PipelineRow)
    # CSV values are strings unless schema coerces them
    assert pipeline_row["id"] == "1"
```

## Missing Coverage Analysis

### Recommended Additional Tests

1. **Contract immutability after locking** - Verify that locked contracts can't be modified.

2. **Contract field type inference accuracy** - Test that inferred types match expected types for various CSV value patterns.

3. **Contract with all rows quarantined but different schema modes** - Current test is FIXED mode; add OBSERVED mode variant.

4. **Contract serialization for audit trail** - Test that contracts can be serialized to JSON for Landscape storage.

## Verdict

**Status:** PASS with recommendations

The test file provides good coverage of contract creation and propagation. The main concern is the mock context that may hide issues - using the real PluginContext would provide stronger guarantees.

## Recommendations Priority

1. **Medium:** Replace MockContext with real PluginContext to avoid hiding bugs
2. **Low:** Add test verifying all valid rows share the same contract instance
3. **Low:** Add test for contract with OBSERVED mode when all rows are quarantined
