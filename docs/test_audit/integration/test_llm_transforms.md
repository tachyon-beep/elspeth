# Test Audit: tests/integration/test_llm_transforms.py

**Batch:** 102
**File:** `/home/john/elspeth-rapid/tests/integration/test_llm_transforms.py`
**Lines:** 1030
**Audit Date:** 2026-02-05

## Summary

This file contains integration tests for LLM transform plugins, covering template rendering, API calls, response parsing, audit trail recording, and error handling. Uses real `LandscapeRecorder` with in-memory databases for audit trail verification.

## Test Classes Found

1. `TestLLMTransformIntegration` - Tests for BaseLLMTransform with mocked clients
2. `TestOpenRouterLLMTransformIntegration` - Tests for OpenRouter HTTP client integration
3. `TestAzureBatchLLMTransformIntegration` - Tests for Azure batch LLM processing
4. `TestAuditedLLMClientIntegration` - Tests for AuditedLLMClient recording

## Issues Found

### 1. DEFECT: Overmocking in `TestOpenRouterLLMTransformIntegration.recorder` Fixture (MEDIUM)

**Location:** Lines 384-391

**Problem:** The fixture creates a real `LandscapeRecorder` but then immediately replaces `record_call` with a Mock:

```python
@pytest.fixture
def recorder(self) -> LandscapeRecorder:
    """Create recorder with in-memory DB."""
    db = LandscapeDB.in_memory()
    rec = LandscapeRecorder(db)
    rec.record_call = Mock()  # type: ignore[method-assign]
    return rec
```

This means the actual call recording path (which is what these integration tests should verify) is never exercised. The `record_call` Mock silently accepts any arguments, so bugs in the recording logic wouldn't be caught.

**Impact:** Tests pass even if the audit trail recording is broken. The "integration" tests don't actually test the integration with the audit trail.

**Recommendation:** Either:
- Remove the mock and verify calls via `recorder.get_calls(state_id)` (like `TestLLMTransformIntegration` does), OR
- If call recording is too slow, at least verify the mock was called with expected arguments

### 2. DEFECT: Test Setup Doesn't Create node_state for Some Tests (LOW)

**Location:** Lines 456-506 (`test_http_client_call_and_response_parsing`)

**Problem:** The test creates a `TokenInfo` but the `execute_transform` method expects a valid `node_state` to be created. Looking at the `_create_token` helper:

```python
def _create_token(...) -> TokenInfo:
    row = recorder.create_row(...)
    recorder.create_token(row_id=row.row_id, token_id=token_id)
    pipeline_row = _make_pipeline_row(row_data)
    return TokenInfo(row_id=row_id, token_id=token_id, row_data=pipeline_row)
```

The `begin_node_state` is NOT called, which is required before recording calls. However, this may work because `record_call` is mocked - the bug is hidden by the overmocking issue above.

**Impact:** Potential test failures if mocking is removed. Integration tests aren't exercising the full state creation workflow.

### 3. MISSING COVERAGE: No Test for Concurrent LLM Calls (MEDIUM)

**Problem:** The `ConcreteLLMTransform` and `OpenRouterLLMTransform` tests don't verify behavior when multiple LLM calls are made concurrently. Given LLM transforms often use thread pools (`pool_size: 5`), concurrent call scenarios should be tested.

**Recommendation:** Add a test that makes multiple concurrent calls and verifies:
- Call indices are allocated correctly
- Audit trail records all calls
- No race conditions in state management

### 4. STRUCTURAL: `ChaosLLM` Test Server Fixture Dependency Not Validated (LOW)

**Location:** Lines 462, 515, 564 (uses `chaosllm_server` fixture)

**Problem:** The tests use `chaosllm_server` fixture but there's no explicit validation that the fixture is available. If the fixture isn't properly configured in conftest.py, tests would fail with confusing errors.

**Note:** The fixture appears to be from conftest.py (not visible in this file), which is fine. Just mentioning for completeness.

### 5. OBSERVATION: Good Pattern - Explicit `required_input_fields: []` Opt-Out

**Location:** Multiple tests (e.g., lines 168, 228, 271, etc.)

**Positive:** Tests explicitly set `required_input_fields: []` to opt out of input field validation. This is good practice as it documents the test's intent to bypass schema contract validation.

### 6. MINOR: Test Docstrings Could Be More Specific (LOW)

**Location:** Throughout

**Problem:** Some test docstrings are generic:
- `test_batch_submit_and_checkpoint_flow` - "Verify batch submission creates checkpoint with batch_id"

The docstrings could specify expected behavior more precisely (e.g., what fields should be in the checkpoint, what the row_mapping structure looks like).

## Test Coverage Analysis

### Well-Covered Scenarios:
- Template rendering with variable substitution
- API call recording in audit trail
- Error handling for API failures
- Rate limit error detection (RateLimitError raised)
- System prompt inclusion in messages
- Batch submission and checkpoint creation
- Batch resume and result mapping
- Per-row API errors in batch processing
- Multi-call indexing in audit trail

### Missing Coverage:
1. **Timeout handling** - No tests for LLM call timeouts
2. **Token limit exceeded** - No tests for token overflow scenarios
3. **Malformed JSON response** - Tests assume responses are valid JSON
4. **Template rendering failures** - Only partial test in batch context
5. **Concurrent call scenarios** - Thread pool behavior not tested
6. **State transitions** - No verification of node_state status changes

## Test Path Integrity

**Status:** PARTIAL COMPLIANCE

The tests use:
- Real `LandscapeRecorder` with in-memory DB (good)
- Real `TransformExecutor` (good)
- But overmocking of `record_call` breaks integration verification

The `ConcreteLLMTransform` subclass is a legitimate testing pattern - it provides a concrete implementation of the abstract `BaseLLMTransform` for testing base class behavior.

## Recommendations

1. **HIGH:** Remove `record_call` mock from `TestOpenRouterLLMTransformIntegration.recorder` fixture
2. **MEDIUM:** Add concurrent LLM call test
3. **MEDIUM:** Add tests for malformed LLM response handling
4. **LOW:** Consider adding explicit node_state creation to `_create_token` helper or document why it's not needed
5. **LOW:** Improve test docstrings with expected outcomes

## Final Assessment

**Quality Score:** 7/10

The tests are generally well-structured and cover important scenarios. The main issue is overmocking in one test class that undermines the integration testing goal. The Azure batch tests are thorough and properly test checkpoint/resume flows. The base LLM transform tests correctly verify audit trail recording.
