# Test Audit: test_processor_pipeline_row.py

**File:** `/home/john/elspeth-rapid/tests/engine/test_processor_pipeline_row.py`
**Lines:** 182
**Batch:** 88

## Summary

Tests for RowProcessor with PipelineRow support, verifying that the processor correctly handles SourceRow input with contracts and creates proper PipelineRow tokens.

## Test Classes

### TestRowProcessorPipelineRow

Tests `process_row()` with SourceRow input.

### TestRowProcessorExistingRow

Tests `process_existing_row()` for resume scenarios.

## Issues Found

### 1. DEFECT: Overmocked Recorder Hides Production Path (Medium)

**Location:** `test_process_row_accepts_source_row` (lines 48-77), `test_process_row_creates_pipeline_row` (lines 79-110)

**Problem:** Tests use heavily mocked recorders that don't exercise real token/row creation logic:

```python
def _make_mock_recorder() -> MagicMock:
    recorder = MagicMock()
    recorder.create_row.return_value = Mock(row_id="row_001")
    recorder.create_token.return_value = Mock(token_id="token_001")
    return recorder
```

The mock returns `Mock()` objects for `create_row` and `create_token`, but the production `RowProcessor` uses `TokenManager.create_initial_token()` which does more than just call recorder methods.

**Impact:** Tests may pass even if production code has bugs in token creation flow. The `TestQuarantineIntegration` tests in the sibling file use real recorders - this file should follow that pattern.

**Recommendation:** Use `LandscapeDB.in_memory()` and real `LandscapeRecorder` like the quarantine tests do.

### 2. DEFECT: Mock Span Factory Context Manager Setup Incomplete (Low)

**Location:** `_make_mock_span_factory()` (lines 37-42)

**Problem:** The mock span factory sets up `__enter__` and `__exit__` on the return value but doesn't return `self` from `__enter__`:

```python
span_factory.row_span.return_value.__enter__ = Mock()
span_factory.row_span.return_value.__exit__ = Mock()
```

**Impact:** If code inside the context manager attempts to use the span object, it would get a `Mock` with no useful behavior. This works because the production code doesn't use the span return value, but it's fragile.

**Recommendation:** Use `Mock()` with proper spec or `MagicMock` which handles context managers correctly:

```python
span_factory.row_span.return_value.__enter__ = Mock(return_value=Mock())
```

### 3. Missing Coverage: Contract Preservation Through Transforms (Medium)

**Problem:** Tests verify that `PipelineRow` is created with contract, but don't verify that contracts are preserved/updated through transform execution.

**Impact:** Contract propagation bugs could slip through.

**Recommendation:** Add test that processes a row through actual transforms and verifies contract handling.

### 4. Missing Coverage: Error Cases in process_existing_row (Low)

**Problem:** No test for invalid inputs to `process_existing_row()` (e.g., missing contract on PipelineRow).

**Impact:** Edge case error handling untested.

## Structural Issues

### 5. Inconsistent Test Patterns Between Files (Low)

**Problem:** This file uses heavy mocking while `test_processor_quarantine.py` uses real components. This inconsistency makes it harder to understand test coverage.

**Recommendation:** Standardize on using real components with `LandscapeDB.in_memory()`.

## Test Path Integrity

- Tests DO NOT use `ExecutionGraph.from_plugin_instances()` but they don't need to - they're testing `RowProcessor` directly, not graph construction
- No manual graph construction violations
- Test classes properly named with "Test" prefix

## Verdict

**NEEDS IMPROVEMENT** - The heavy mocking obscures production behavior. The tests should use real recorders like the sibling test files do.

## Fixes Required

1. Replace mock recorders with real `LandscapeRecorder` and `LandscapeDB.in_memory()`
2. Add test for contract preservation through transforms
3. Consider consolidating with other processor tests that already use real components
