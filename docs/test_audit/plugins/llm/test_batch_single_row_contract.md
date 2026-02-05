# Test Audit: test_batch_single_row_contract.py

**File:** `tests/plugins/llm/test_batch_single_row_contract.py`
**Lines:** 204
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file tests contract propagation in batch transforms when they process single rows via `_process_single`. Tests verify that when a batch transform processes one row by wrapping it in a list, the contract is correctly propagated to the result.

## Findings

### 1. GOOD: Critical Bug Regression Test

**Positive:** This file is a regression test for P2-2026-02-05 (contract lost in single-row fallback). The docstring clearly documents the bug being prevented.

### 2. OVERMOCKING: Mocking _process_batch Bypasses Production Code

**Severity:** High
**Issue:** Lines 95-96 and 187-188 mock `_process_batch` directly:
```python
with patch.object(transform, "_process_batch", return_value=batch_result):
    result = transform._process_single(input_row, ctx)
```
**Impact:** This tests that `_process_single` correctly propagates the contract from `_process_batch`'s return value, but it does NOT test:
- That `_process_batch` actually returns a contract
- That the contract is correctly constructed during real batch processing
- That `_download_results` (mentioned in comment) actually sets the contract

**The Real Bug Could Still Exist:** If `_process_batch` itself fails to set the contract, this test would still pass while production fails.

**Recommendation:** Add integration tests that exercise the full path without mocking `_process_batch`:
```python
# Test that calls _process_single with a mock LLM client, not mock _process_batch
```

### 3. GOOD: Tests Both Azure and OpenRouter

**Positive:** Tests are duplicated for both `AzureBatchLLMTransform` and `OpenRouterBatchLLMTransform`, ensuring both implementations have the same behavior.

### 4. STRUCTURAL: Duplicate Test Code

**Severity:** Medium
**Issue:** `TestAzureBatchSingleRowContractPropagation` and `TestOpenRouterBatchSingleRowContractPropagation` are nearly identical (lines 20-115 vs 117-204).
**Impact:** Maintenance burden - if the test needs to change, it must be changed in both places.
**Recommendation:** Parametrize the test class or use a base class:
```python
@pytest.mark.parametrize("transform_class", [AzureBatchLLMTransform, OpenRouterBatchLLMTransform])
def test_process_single_preserves_contract(transform_class, ...):
```

### 5. INCOMPLETE: Only Tests Happy Path

**Severity:** Medium
**Issue:** Only tests successful `_process_batch` result with contract.
**Impact:** Missing coverage for:
- What happens if `_process_batch` returns error result?
- What happens if `_process_batch` returns result without contract?
- What happens if batch returns multiple rows but we only want one?
**Recommendation:** Add tests for error cases and edge cases.

### 6. GOOD: Explicit Contract Field Verification

**Positive:** Lines 110-114 and 199-204 verify the contract can actually resolve the field:
```python
resolved = result.contract.resolve_name("llm_response")
assert resolved == "llm_response"
```
This catches the actual failure mode where downstream transforms would fail.

## Missing Coverage

1. **Error path in _process_single** - What if batch processing fails?
2. **Multiple rows from batch** - What if batch returns more than one row?
3. **Empty batch result** - What if batch returns empty list?
4. **Actual batch processing** - No test exercises real batch processing without mocking
5. **Contract field types** - Tests don't verify field types are correct

## Structural Issues

1. **Test duplication between Azure and OpenRouter** - 50% of file is copy-paste
2. **No shared fixtures** - Both test classes define identical fixtures
3. **Comments reference P2-2026-02-05** but no link to bug documentation

## Overall Assessment

**Rating:** Needs Improvement
**Verdict:** This test attempts to catch a real bug (contract loss in single-row fallback) but the overmocking of `_process_batch` means the actual bug could still exist in production. The test verifies the contract propagation *logic* in `_process_single` but not the actual *source* of the contract. An integration test without mocking `_process_batch` would provide much better confidence.

The test duplication between Azure and OpenRouter implementations should be refactored.
