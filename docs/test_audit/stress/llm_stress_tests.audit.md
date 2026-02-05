# Audit: tests/stress/llm/ (6 files)

## Files Covered
1. `test_azure_llm_stress.py` (420 lines)
2. `test_azure_multi_query_stress.py` (375 lines)
3. `test_mixed_errors.py` (527 lines)
4. `test_openrouter_llm_stress.py` (344 lines)
5. `test_openrouter_multi_query_stress.py` (427 lines)
6. `conftest.py` (443 lines)

## Summary
Stress tests for LLM transforms using a ChaosLLM HTTP server fixture that injects errors (rate limits, capacity errors, malformed JSON, timeouts) at configurable rates.

**Total Lines:** ~2,536
**Test Classes:** 5
**Test Methods:** 17
**Marker:** `pytest.mark.stress` (skipped by default)

## Verdict: PASS WITH RECOMMENDATIONS

The stress tests are well-designed for their purpose but share significant code duplication. The tests exercise real HTTP communication and validate important behaviors (AIMD backoff, error handling, FIFO ordering).

---

## Detailed Analysis

### 1. Defects
**Potential issue: Probabilistic assertion bounds**

Multiple tests use probabilistic assertions that could be flaky:

```python
# test_azure_llm_stress.py:211
assert output.success_count > 50, f"Expected >50 successes, got {output.success_count}"

# test_azure_multi_query_stress.py:226
assert output.success_count >= 35, f"Expected at least 70% success, got {output.success_count}/50"
```

With random error injection, these bounds are estimates. If ChaosLLM happens to inject errors non-uniformly, tests could fail spuriously.

**Recommendation:** Increase the bounds slightly or document the statistical basis (e.g., "With 30% error rate and AIMD retry, 3-sigma bound on failures is X").

### 2. Overmocking
**None - Excellent!**

The tests use:
- Real HTTP server (ChaosLLM) with actual TCP connections
- Real LandscapeDB and LandscapeRecorder for audit trail
- Real LLM transforms (AzureLLMTransform, OpenRouterLLMTransform, etc.)
- No mocking of internal behavior

The `CollectingOutputPort` is a test double that implements the OutputPort protocol, which is appropriate.

### 3. Missing Coverage
**Gaps identified:**

1. **No test for exact error recording in audit trail** - Tests verify `output.total_count` but don't check that errors are properly recorded in Landscape tables with correct error details.

2. **No test for LLM response content** - Tests verify rows complete but don't check that successful responses contain expected LLM output fields.

3. **No test for connection pooling under stress** - Pool size is configured but behavior under pool exhaustion isn't tested.

4. **No timeout behavior test** - `max_capacity_retry_seconds` is set but there's no test verifying behavior when timeout is reached.

### 4. Tests That Do Nothing
**Minor issue in test_openrouter_llm_stress.py:271:**

```python
[e[0].get("reason") for e in output.errors]
# Malformed JSON could result in various error reasons...
```

This creates a list comprehension that's never used. The result is discarded. Either add an assertion or remove the line.

**Same pattern in test_mixed_errors.py** - Several places compute values but don't assert on them.

### 5. Inefficiency
**Major duplication: CollectingOutputPort**

The `CollectingOutputPort` class is duplicated identically in all 5 test files (lines 42-102 in each). This should be in conftest.py.

**Major duplication: create_recorder_and_run()**

Similar function duplicated in each test file with minor variations. Should be consolidated in conftest.py.

**Minor: Repeated row creation loop**

Every test has a 30-line loop that:
1. Creates a token
2. Creates a row record
3. Creates a token record
4. Begins node state
5. Creates context
6. Calls transform.accept()

This pattern should be extracted to a helper function.

### 6. Structural Issues
**Test class discovery is correct** - All classes prefixed with `Test`.

**Good practice: pytestmark for stress tests**

```python
pytestmark = pytest.mark.stress
```

This ensures stress tests are skipped by default but can be run explicitly.

**Issue: @pytest.mark.chaosllm decorator usage**

The `@pytest.mark.chaosllm(...)` decorator appears to configure the ChaosLLM server, but there's no code in conftest.py that reads these markers. The fixture `chaosllm_http_server` must handle this elsewhere.

**Verified:** The marker is handled by `tests/stress/conftest.py` (not shown in this audit) via the `request.node.get_closest_marker("chaosllm")` pattern.

---

## Notable Patterns (Positive)

### Real HTTP Communication
Tests use actual HTTP requests to a local ChaosLLM server, validating:
- Request/response serialization
- HTTP error handling (429, 503, 504, 529)
- Connection management

### Audit Trail Verification
`test_audit_trail_integrity_under_stress` (test_mixed_errors.py:291) verifies that every row has:
- Row record in database
- Token record
- Node state records

This aligns with ELSPETH's "no silent drops" principle.

### FIFO Ordering Validation
Multiple tests verify that output order matches input order for successful rows, which is a critical invariant for the BatchTransformMixin.

---

## Recommendations

### High Priority

1. **Consolidate CollectingOutputPort** - Move to conftest.py to eliminate 5x duplication.

2. **Extract row creation helper** - Create a helper function in conftest.py:
   ```python
   def process_rows_through_transform(
       transform, recorder, run_id, node_id, rows, output
   ) -> None:
       """Process rows through a transform with proper audit recording."""
   ```

3. **Fix discarded comprehensions** - Either assert on the results or remove the dead code.

### Medium Priority

4. **Add error recording verification** - Add test that verifies Landscape `transform_errors` table contains expected error details.

5. **Test timeout exhaustion** - Add test with very short `max_capacity_retry_seconds` and very high error rate to verify timeout behavior.

### Low Priority

6. **Document statistical bounds** - Add comments explaining the probabilistic assertion thresholds.

7. **Add explicit test for pool_size > row_count** - Verify behavior when more workers than work items.

---

## Test Quality Score: 7/10

Good stress tests that exercise real HTTP and audit behavior, but significant code duplication and some dead code reduce maintainability. The tests validate important invariants but miss some edge cases around error recording and timeout behavior.
