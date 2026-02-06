# Audit: tests/plugins/test_node_id_protocol.py

## Summary
Tests verifying that `node_id` attribute is part of the plugin protocol contract for all plugin types. Generally well-structured with clear intent.

## Findings

### 1. Annotation Check Fragility (Minor)

**Location:** Lines 16-19, 54-55, 87-88, etc.

**Issue:** Tests check `__annotations__` for `str | None` type, which works only in Python 3.10+. If the codebase ever needs to support earlier Python versions, these tests would fail.

**Impact:** Low - codebase appears to target modern Python.

### 2. Redundant Deletion Tests

**Location:** Lines 115-125

**Issue:** `test_aggregation_protocol_deleted` and `test_base_aggregation_deleted` duplicate functionality from `test_protocols.py` (TestAggregationProtocolDeleted class). Having the same assertion in multiple files increases maintenance burden without additional coverage.

**Recommendation:** Consider consolidating deletion verification tests in one location.

### 3. Tests Do Nothing Problem - Weak Assertions

**Location:** Lines 21-47, 57-80, 90-113, 143-171

**Issue:** Tests create plugin instances, set `node_id`, and verify it was set. This only tests that Python attribute assignment works - it does not verify:
- That the engine actually uses `node_id`
- That `node_id` is passed through the audit trail correctly
- That missing `node_id` causes appropriate failures

**Severity:** Medium - tests provide false confidence about node_id integration.

## Structural Issues

### Test Class Discovery
No issues - single test class `TestNodeIdProtocol` will be discovered correctly.

## Missing Coverage

1. **No integration tests** verifying engine sets node_id during registration
2. **No negative tests** for what happens when node_id is None when it shouldn't be
3. **No audit trail verification** that node_id appears in Landscape records

## Verdict

**Overall Quality:** Fair

The tests verify the structural presence of `node_id` in protocol definitions and base classes, but do not verify functional integration. They serve as schema/contract documentation tests rather than behavioral tests.

## Recommendations

1. Add integration test verifying Orchestrator sets node_id after Landscape registration
2. Remove duplicate deletion tests (keep them in test_protocols.py)
3. Consider whether these protocol attribute tests belong in a dedicated contract verification module
