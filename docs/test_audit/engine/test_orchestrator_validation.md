# Test Audit: test_orchestrator_validation.py

**File:** `/home/john/elspeth-rapid/tests/engine/test_orchestrator_validation.py`
**Lines:** 524
**Audit Date:** 2026-02-05
**Auditor:** Claude

## Summary

Tests for Orchestrator transform error sink validation. Verifies that `_validate_transform_error_sinks()` properly validates that transform `on_error` settings reference existing sinks at startup time, before any rows are processed.

**Overall Assessment:** GOOD - Well-structured tests using production code paths with clear intent and meaningful assertions.

## Test Classes

### TestTransformErrorSinkValidation (5 tests)

Tests for transform on_error sink validation at startup.

## Findings

### 1. POSITIVE: Uses Production Code Path

**Severity:** N/A (Good Practice)

The tests correctly use `build_production_graph(config)` from `orchestrator_test_helpers.py`, which internally calls `ExecutionGraph.from_plugin_instances()`. This follows the Test Path Integrity requirement from CLAUDE.md.

```python
# Lines 134-135, 213, etc.
orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)
```

### 2. POSITIVE: Verifies Validation Happens Before Processing

**Severity:** N/A (Good Practice)

Tests properly verify that validation errors occur BEFORE source load is called:

```python
# Lines 136-138
with pytest.raises(RouteValidationError):
    orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)
# Verify source.load was NOT called (validation happens before processing)
assert not source.load_called
```

### 3. Minor Inefficiency: Duplicate Helper Classes

**Severity:** Low
**Type:** Inefficiency

Multiple test methods define identical inner classes like `CollectSink`, `ListSource`, etc. These could be extracted to module-level or a shared fixture.

**Locations:**
- `CollectSink` defined at lines 102-119, 178-195, 258-275, 327-344, 396-413, 483-503
- `ListSource` defined at lines 152-162, 232-242, 302-312, 370-380
- `TrackingSource` defined at lines 72-86, 453-466

**Impact:** Code duplication, slightly slower test execution. However, this is a minor issue and keeping classes local to tests improves readability and makes each test self-contained.

### 4. POSITIVE: Error Message Verification

**Severity:** N/A (Good Practice)

Test `test_error_message_includes_transform_name_and_sinks` verifies the error message contains useful debugging information:

```python
# Lines 215-222
error_msg = str(exc_info.value)
assert "my_bad_transform" in error_msg
assert "phantom_sink" in error_msg
assert "default" in error_msg
assert "error_archive" in error_msg
```

### 5. POSITIVE: Comprehensive Edge Case Coverage

**Severity:** N/A (Good Practice)

Tests cover all valid `on_error` configurations:
- `test_on_error_discard_passes_validation` - "discard" special value
- `test_on_error_none_passes_validation` - None (not configured)
- `test_valid_on_error_sink_passes_validation` - valid sink name
- Plus invalid sink name cases

### 6. POSITIVE: Complete Tracking in Timing Verification

**Severity:** N/A (Good Practice)

`test_validation_occurs_before_row_processing` uses comprehensive tracking to verify NO processing occurred:

```python
# Lines 447-451
call_tracking: dict[str, bool] = {
    "source_load_called": False,
    "transform_process_called": False,
    "sink_write_called": False,
}
```

All three assertions verify nothing was called (lines 522-524).

## Missing Coverage

### 1. Multiple Invalid on_error Configurations

**Severity:** Low

No test verifies behavior when multiple transforms have invalid `on_error` settings. Does validation fail on first invalid sink, or report all? This is an edge case but could be useful for user feedback.

### 2. on_error with Empty String

**Severity:** Low

No test for `_on_error = ""` (empty string vs None). This should probably be treated as "not configured" or fail validation.

## Structural Issues

None identified. Test class is properly named with "Test" prefix and will be discovered by pytest.

## Recommendations

1. **Consider extracting common test helpers** to module level (e.g., `CollectSink`, `ListSource`) to reduce duplication, but this is optional since current structure is clear.

2. **Add test for multiple invalid sinks** to verify error reporting behavior.

3. **Add test for empty string on_error** to clarify expected behavior.

## Verdict

**PASS** - Tests are well-written, use production code paths, and verify meaningful behavior. Minor duplication is acceptable for test clarity.
