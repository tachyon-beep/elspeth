# Test Audit: test_llm_transform_contract.py

**File:** `tests/plugins/llm/test_llm_transform_contract.py`
**Lines:** 247
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file tests LLM transform contract integration, verifying that PipelineRow contracts are correctly used for template rendering and propagated to transform results with new fields added by the LLM.

## Findings

### 1. GOOD: MockLLMTransform Design

**Positive:** `MockLLMTransform` (lines 14-38) is a well-designed test double:
- Extends actual `BaseLLMTransform`
- Overrides only `_get_llm_client`
- Returns controllable mock client
- Allows tests to verify actual transform behavior

### 2. GOOD: Original Name Template Test

**Positive:** `test_process_with_pipeline_row` (lines 76-102) verifies template can use original field name `"Product Name"` which resolves via contract to `"product_name"`. This is critical for backwards compatibility with legacy templates.

### 3. GOOD: Contract Propagation Tests

**Positive:** Tests at lines 132-184 verify:
- Result includes contract when input has contract
- Contract includes new LLM-added fields
- Even minimal FLEXIBLE contracts result in proper output contract

### 4. DEFECT: Error Test Assertion Too Loose

**Severity:** Low
**Issue:** `test_template_error_with_original_name_minimal_contract` (lines 186-215) asserts:
```python
assert "template" in str(result.reason.get("reason", "")).lower()
```
**Impact:** This assertion would pass if `reason` is `"template_foo"`, `"foo_template"`, or even just contains the substring. It's testing the error message, not the error code.
**Recommendation:** Assert the exact reason code:
```python
assert result.reason["reason"] == "template_rendering_failed"
```

### 5. GOOD: Contract Field Type Inference Test

**Positive:** `test_contract_propagation_adds_new_fields` (lines 217-247) verifies:
- New `analysis` field is added to contract
- Field type is inferred as `str`
- Field source is marked as `"inferred"`

This tests the schema evolution behavior.

### 6. INCOMPLETE: No Error Path Contract Tests

**Severity:** Medium
**Issue:** All tests assume successful LLM responses. No tests for:
- Does error result include contract?
- What contract do retryable errors have?
**Impact:** Unknown contract behavior on errors.
**Recommendation:** Add tests for error case contract handling.

### 7. OVERMOCKING: MagicMock Context

**Severity:** Low
**Issue:** `mock_context` fixture uses MagicMock with `ctx.contract = None` (lines 65-74).
**Impact:** PluginContext may have other attributes that affect behavior. Using spec would be safer.
**Recommendation:** Use `Mock(spec=PluginContext)` to catch attribute access errors.

### 8. MISSING: Multi-Field LLM Response Test

**Severity:** Low
**Issue:** Tests only add a single field (`llm_result` or `analysis`). No test for LLM adding multiple fields.
**Impact:** Unknown behavior if LLM response adds multiple fields to contract.

## Missing Coverage

1. **Error path contract propagation** - What contract do error results have?
2. **Multi-field LLM outputs** - LLM adding multiple fields to row
3. **Batch processing contracts** - No batch/multi-row contract tests
4. **Contract locking behavior** - Tests use `locked=True` but don't verify locking effects
5. **Required fields validation** - Tests use `required_input_fields: ["product_name"]` but don't test validation

## Structural Issues

1. **Mock client in class attribute** - `MockLLMTransform._mock_client` could have test isolation issues if not reset
2. **Fixture organization** - `data` and `contract` fixtures are always used together, could be combined

## Overall Assessment

**Rating:** Good
**Verdict:** Tests verify the critical contract integration between PipelineRow, LLM templates, and transform results. The mock transform design is correct and allows testing actual transform logic. Main gaps are error path handling and multi-field output scenarios. The file provides good regression coverage for contract propagation.
