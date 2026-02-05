# Test Audit: test_azure_batch.py

**File:** `tests/plugins/llm/test_azure_batch.py`
**Lines:** 1569
**Batch:** 121

## Summary

This test file validates the `AzureBatchLLMTransform` plugin, which handles Azure OpenAI Batch API for asynchronous LLM processing with checkpointing and resume capabilities. This is a complex transform with multi-phase processing (submit -> poll -> download results).

## Test Classes

| Class | Test Count | Purpose |
|-------|------------|---------|
| `TestBatchPendingError` | 3 | Exception handling |
| `TestAzureBatchConfig` | 11 | Config validation |
| `TestAzureBatchLLMTransformInit` | 7 | Transform initialization |
| `TestAzureBatchLLMTransformEmptyBatch` | 1 | Empty batch guard |
| `TestAzureBatchLLMTransformSubmit` | 6 | Batch submission (Phase 1) |
| `TestAzureBatchLLMTransformTemplateErrors` | 2 | Template error handling |
| `TestAzureBatchLLMTransformResume` | 7 | Status checking (Phase 2) |
| `TestAzureBatchLLMTransformTimeout` | 1 | Timeout handling |
| `TestAzureBatchLLMTransformSingleRow` | 1 | Single row processing |
| `TestAzureBatchLLMTransformResultAssembly` | 2 | Result ordering |
| `TestAzureBatchLLMTransformAuditRecording` | 2 | LLM call audit trail |
| `TestAzureBatchLLMTransformClose` | 2 | Resource cleanup |
| `TestAzureBatchLLMTransformMissingResults` | 2 | Missing result handling |

## Findings

### 1. POSITIVE: Checkpoint State Machine Coverage

Tests thoroughly cover the checkpoint-based state machine:
```python
# Fresh submission
def test_fresh_batch_submits_and_raises_pending():
    with pytest.raises(BatchPendingError):
        transform.process(rows, ctx)
    assert checkpoint["batch_id"] == "batch-456"

# Resume with existing checkpoint
def test_resume_with_checkpoint_checks_status():
    ctx._checkpoint["batch_id"] = "batch-456"
    with pytest.raises(BatchPendingError) as exc:
        transform.process(rows, ctx)
    assert exc.value.status == "in_progress"
```

### 2. POSITIVE: All Terminal States Tested

Tests cover all Azure Batch terminal states:
- `completed` -> download results
- `failed` -> return error with details
- `cancelled` -> return error
- `expired` -> return error
- `in_progress` -> raise `BatchPendingError`

### 3. CRITICAL: Potential Test Fragility with Internal Attributes

**Location:** Lines 482, 606, 687, 877, 902, 1002, etc.

Multiple tests directly access `ctx._checkpoint`:
```python
checkpoint = ctx._checkpoint  # type: ignore[attr-defined]
assert checkpoint["batch_id"] == "batch-456"
```

**Issue:** The `_checkpoint` attribute is internal (underscore prefix). Tests should use public methods like `ctx.get_checkpoint()` and `ctx.update_checkpoint()` if available.

**Impact:** Tests may break if internal implementation changes. The `# type: ignore` suggests this is a known workaround.

**Severity:** Medium - fragile but functional.

### 4. POSITIVE: Audit Trail Completeness (BUG-AZURE-01)

Tests verify LLM calls are recorded to the audit trail:
```python
def test_download_results_records_llm_calls(self):
    """Processing results should record LLM calls per row against batch state."""
    assert ctx.record_call.call_count == 3  # 1 HTTP + 2 LLM

    llm_call1 = calls[1].kwargs
    assert llm_call1["call_type"] == CallType.LLM
    assert llm_call1["request_data"]["messages"][0]["content"] == "Analyze: Hello"
    assert llm_call1["status"] == CallStatus.SUCCESS
```

This is critical for the ELSPETH audit trail requirements.

### 5. POSITIVE: Missing Result Handling (P2-2026-01-31)

Tests verify missing results from Azure still produce audit records:
```python
def test_missing_result_records_error_call(self):
    """Missing result from batch output records an ERROR Call for audit trail."""
    # Result should have error for missing row
    assert result.rows[1]["llm_response"] is None
    assert result.rows[1]["llm_response_error"]["reason"] == "result_not_found"

    # CRITICAL: Verify record_call was called for BOTH rows
    error_calls = [call for call in llm_calls if call.kwargs.get("status") == CallStatus.ERROR]
    assert len(error_calls) == 1
```

### 6. POTENTIAL ISSUE: Mock Client Injection

**Location:** Multiple tests directly set `transform._client`:
```python
mock_client = Mock()
...
transform._client = mock_client
```

**Issue:** This bypasses the production `_get_client()` method. If `_get_client()` has important initialization logic, tests won't catch bugs in it.

**Alternative approach:**
```python
with patch.object(transform, "_get_client", return_value=mock_client):
    transform.process(rows, ctx)
```

Some tests do use `patch.object(transform, "_get_client")` (lines 1205, 1292), showing inconsistency.

**Severity:** Medium - the direct injection tests work but miss client initialization bugs.

### 7. POSITIVE: Result Ordering Verification

Tests verify results are assembled in original row order regardless of Azure response order:
```python
# Results in random order from Azure
output_lines = [
    json.dumps({"custom_id": "row-2-ccc", ...}),  # Index 2
    json.dumps({"custom_id": "row-0-aaa", ...}),  # Index 0
    json.dumps({"custom_id": "row-1-bbb", ...}),  # Index 1
]

# But result order matches input
assert result.rows[0]["llm_response"] == "A"
assert result.rows[1]["llm_response"] == "B"
assert result.rows[2]["llm_response"] == "C"
```

### 8. MINOR GAP: No Concurrent Resume Test

**Issue:** No test verifies behavior when multiple processes try to resume the same batch (race condition scenario in distributed systems).

**Severity:** Low - likely handled at orchestrator level, not transform level.

### 9. POSITIVE: Empty Batch Guard

Test verifies empty batches crash immediately per CLAUDE.md:
```python
def test_empty_batch_raises_runtime_error():
    """Empty batch raises RuntimeError - engine invariant violated."""
    with pytest.raises(RuntimeError, match="Empty batch passed"):
        transform.process([], ctx)
```

### 10. MINOR: Inconsistent Fixture Usage

Some test classes define fixtures (`TestAzureBatchLLMTransformSubmit.transform`), while others create transforms inline. This is acceptable but inconsistent.

### 11. POSITIVE: Test Path Integrity

**Status:** Mostly Compliant

Tests use production code paths:
- `AzureBatchLLMTransform` constructor with real config
- `process()` method (the production entry point)
- Real checkpoint data structures

The direct `_client` assignment is a controlled mock injection, not bypassing production logic.

## Recommendations

1. **Medium Priority:** Replace direct `ctx._checkpoint` access with public methods if available
2. **Medium Priority:** Standardize on `patch.object(transform, "_get_client")` instead of `transform._client = mock`
3. **Low Priority:** Unify fixture vs inline transform creation pattern

## Risk Assessment

| Category | Risk Level |
|----------|------------|
| Defects | None identified |
| Overmocking | Medium - direct _client injection may hide client init bugs |
| Missing Coverage | Low - comprehensive |
| Tests That Do Nothing | None |
| Structural Issues | Minor - inconsistent patterns |

## Verdict

**PASS** - Comprehensive test coverage for a complex async batch transform. The checkpoint-based state machine and audit trail recording are well-tested. Minor improvements possible in mock injection consistency.

## Notable Good Practices

1. Tests explicitly verify audit trail completeness (BUG-AZURE-01 regression tests)
2. Tests verify missing result handling creates error audit records (P2-2026-01-31)
3. Tests verify result ordering is preserved
4. Tests cover all Azure Batch terminal states
5. Clear docstrings explain WHY each test exists
