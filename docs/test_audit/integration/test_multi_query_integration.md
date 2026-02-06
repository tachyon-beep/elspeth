# Test Audit: tests/integration/test_multi_query_integration.py

**Batch:** 102
**File:** `/home/john/elspeth-rapid/tests/integration/test_multi_query_integration.py`
**Lines:** 365
**Audit Date:** 2026-02-05

## Summary

This file contains integration tests for Azure Multi-Query LLM transform, which processes a 2x5 assessment matrix (2 case studies x 5 criteria = 10 LLM calls). Tests verify multi-query processing via the `TransformExecutor`.

## Test Classes Found

1. `TestMultiQueryIntegration` - Full integration tests for multi-query transform via TransformExecutor

## Issues Found

### 1. DEFECT: Overmocking in `recorder` Fixture (MEDIUM)

**Location:** Lines 139-145

**Problem:** Same pattern as `test_llm_transforms.py` - the fixture mocks `record_call`:

```python
@pytest.fixture
def recorder() -> LandscapeRecorder:
    """Create recorder with in-memory DB."""
    db = LandscapeDB.in_memory()
    rec = LandscapeRecorder(db)
    rec.record_call = Mock()  # type: ignore[method-assign]
    return rec
```

**Impact:** The integration tests don't actually verify that LLM calls are recorded in the audit trail. Since the multi-query transform makes 10 LLM calls per row, verifying audit trail recording is critical.

**Recommendation:** Remove the mock and add assertions verifying `recorder.get_calls(state_id)` returns the expected number of calls.

### 2. MISSING COVERAGE: No Audit Trail Verification (MEDIUM)

**Problem:** Neither test verifies that LLM calls are recorded in the audit trail. For an integration test, this is a significant gap.

The tests verify:
- Correct number of `mock_client.chat.completions.create.call_count`
- Output fields exist in result

But NOT:
- Calls recorded in Landscape
- Call hashes computed
- Latency recorded

**Recommendation:** Add assertions like:
```python
# Get all node states for the run
states = recorder.get_node_states(run_id)
# Verify calls were recorded (would fail if record_call mocked)
for state in states:
    calls = recorder.get_calls(state.state_id)
    assert len(calls) > 0  # Each state should have calls
```

### 3. MISSING COVERAGE: No Error Handling Tests (MEDIUM)

**Problem:** No tests for:
- What happens when one of 10 LLM calls fails
- Partial success scenarios (e.g., 8 of 10 calls succeed)
- Rate limiting with multiple concurrent calls
- Timeout on individual queries within the batch

This is particularly important for multi-query since partial failure handling is complex - do you fail the whole row, or return partial results?

### 4. MISSING COVERAGE: No Tests for Input Field Validation (LOW)

**Problem:** The tests use `required_input_fields: []` to opt out of validation:

```python
"required_input_fields": [],  # Explicit opt-out for this test
```

While this is fine for some tests, there should be at least one test verifying that missing input fields are properly caught.

### 5. OBSERVATION: Good Test for Deadlock Regression (Positive)

**Location:** Lines 280-365 (`test_multiple_rows_through_multi_query`)

**Positive:** The test comment mentions "this would hang with the old bug", indicating this is a regression test for a deadlock issue. This is valuable for preventing regression.

```python
# All 3 should succeed (this would hang with the old bug)
assert all(r.status == "success" for r in results)
```

### 6. STRUCTURAL: Context Manager Pattern is Good

**Location:** Lines 96-136 (`mock_azure_openai_multi_query`)

**Positive:** The `@contextmanager` pattern for mocking Azure OpenAI is clean and reusable:

```python
@contextmanager
def mock_azure_openai_multi_query(
    responses: list[dict[str, Any]],
) -> Generator[Mock, None, None]:
```

This allows tests to control response behavior while keeping the mock setup DRY.

### 7. MINOR: Response Cycling Could Mask Bugs (LOW)

**Location:** Lines 110-112

**Problem:** The mock cycles through responses:

```python
content = json.dumps(responses[call_count[0] % len(responses)])
call_count[0] += 1
```

If the transform makes more calls than expected, the test still passes by cycling responses. This could mask bugs where extra calls are made.

**Recommendation:** Consider failing if more calls are made than responses provided, or at least asserting the exact call count.

## Test Coverage Analysis

### Well-Covered Scenarios:
- Full 2x5 assessment matrix (10 LLM calls)
- Output field generation for all case study/criterion combinations
- Multiple rows without deadlock
- Original row data preservation

### Missing Coverage:
1. **Audit trail recording** - Mocked away
2. **Partial failure scenarios** - No tests
3. **Rate limiting** - No tests for 429 handling with multiple queries
4. **Timeout scenarios** - No tests
5. **Invalid JSON responses** - No tests
6. **Schema contract validation** - Explicitly disabled
7. **Output field type validation** - No tests (e.g., `score` should be integer)

## Test Path Integrity

**Status:** PARTIAL COMPLIANCE

The tests use:
- Real `TransformExecutor` (good)
- Real `LandscapeRecorder` with in-memory DB (good)
- Production `AzureMultiQueryLLMTransform` (good)

But overmocking of `record_call` means the integration with audit trail is not verified.

## Recommendations

1. **HIGH:** Remove `record_call` mock and add audit trail verification
2. **HIGH:** Add tests for partial failure scenarios (some queries fail)
3. **MEDIUM:** Add tests for invalid JSON response handling
4. **MEDIUM:** Add explicit call count assertions (not just cycling responses)
5. **LOW:** Add at least one test with `required_input_fields` enabled

## Final Assessment

**Quality Score:** 6.5/10

The tests cover the happy path well and include a valuable deadlock regression test. However, the overmocking of `record_call` and missing error handling tests significantly reduce the integration test value. The multi-query transform is complex (fan-out to N calls, fan-in results), and the tests don't adequately cover the failure modes this complexity introduces.
