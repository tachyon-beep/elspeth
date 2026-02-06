# Test Audit: test_processor_quarantine.py

**File:** `/home/john/elspeth-rapid/tests/engine/test_processor_quarantine.py`
**Lines:** 245
**Batch:** 88

## Summary

Integration tests for the quarantine flow in RowProcessor, verifying that:
- Pipelines continue processing after quarantining a row
- Audit trails are correctly recorded for quarantined rows

## Test Classes

### TestQuarantineIntegration

Full integration tests with real Landscape components.

## Issues Found

### 1. GOOD: Uses Real Components (Positive)

**Observation:** Unlike `test_processor_pipeline_row.py`, these tests properly use:
- `LandscapeDB.in_memory()`
- Real `LandscapeRecorder`
- Real `SpanFactory`

This is the correct pattern for integration tests.

### 2. DEFECT: Test Plugins Inherit from BaseTransform But Skip Constructor (Low)

**Location:** `ValidatingTransform.__init__` (lines 86-88), `StrictValidator.__init__` (lines 184-186)

**Problem:** Test plugins call `super().__init__()` with minimal config:

```python
def __init__(self, node_id: str) -> None:
    super().__init__({"schema": {"mode": "observed"}})
    self.node_id = node_id
```

This assigns `node_id` directly rather than letting the framework handle it. In production, `node_id` is assigned by the orchestrator via `_assign_node_ids_to_plugins()`. However, these tests work because `node_id` is a public attribute that the processor reads.

**Impact:** Minor - tests work correctly but don't exercise the production node_id assignment path.

### 3. Missing Coverage: Quarantine with on_error='continue' (Low)

**Problem:** Tests only use `_on_error = "discard"`. No test verifies behavior when `on_error` routes to a specific sink.

**Impact:** Quarantine routing to named sinks untested.

### 4. DEFECT: Weak Assertion on Error JSON Content (Low)

**Location:** Lines 243-245

**Problem:** Test parses error JSON to verify content but uses string comparison:

```python
error_data = json.loads(state.error_json)
assert error_data["reason"] == "missing_field"
assert error_data["error"] == "missing required_field"
```

**Impact:** If error message format changes, test fails with unhelpful diff. Consider checking for key presence and/or using `in` for substring matching on error messages.

### 5. Missing Coverage: Multiple Quarantined Rows Same Pipeline (Low)

**Problem:** `test_pipeline_continues_after_quarantine` processes 5 rows but doesn't verify that quarantined rows don't interfere with subsequent valid rows in terms of audit state.

**Impact:** Potential state bleed between rows untested.

### 6. INEFFICIENCY: Contract Created Per Row (Very Low)

**Location:** Lines 113-119

**Problem:** `_make_observed_contract()` is called for each row in the loop:

```python
for i, value in enumerate(test_values):
    results = processor.process_row(
        ...
        source_row=SourceRow.valid({"value": value}, contract=_make_observed_contract({"value": value})),
        ...
    )
```

**Impact:** Minor performance issue, but contracts are immutable so each row could share one contract.

**Recommendation:** Create contract once outside loop since schema is the same.

## Structural Issues

### 7. Good Test Isolation (Positive)

Each test creates its own `run_id` via `recorder.begin_run()`, ensuring test isolation even with module-scoped database fixture.

### 8. Comment About row.get() is Outdated (Low)

**Location:** Line 189

```python
# row.get() is allowed here - this is row data (their data, Tier 2)
if "required_field" not in row:
```

**Problem:** Comment mentions `row.get()` but code uses `in` operator. Comment should match code.

## Test Path Integrity

- Tests use real `RowProcessor` with real components
- No `ExecutionGraph` construction needed (tests processor directly)
- No manual graph construction violations
- Test classes properly named with "Test" prefix

## Verdict

**ACCEPTABLE** - These tests follow good integration test patterns. Minor issues don't affect correctness.

## Fixes Required (Optional)

1. Update comment at line 189 to match code
2. Consider adding test for `on_error` routing to named sink
3. Minor: reuse contract instance in loop
