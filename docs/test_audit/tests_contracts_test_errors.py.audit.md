# Test Audit: tests/contracts/test_errors.py

**Lines:** 646
**Test count:** 44
**Audit status:** ISSUES_FOUND

## Summary

This file tests TypedDict schema contracts for error and reason types (ExecutionError, RoutingReason, TransformSuccessReason, TransformErrorReason, and nested types). Tests are divided into schema introspection tests (verifying `__required_keys__` and `__optional_keys__`) and usage tests (verifying dicts can be constructed with the TypedDict). The file is comprehensive but contains significant redundancy.

## Findings

### 🟡 Warning (tests that are weak, wasteful, or poorly written)

- **Lines 97-123 (TestExecutionError):** These tests create TypedDict instances and then assert they contain the values that were just assigned. For example, `test_execution_error_has_required_fields` creates `error: ExecutionError = {"exception": "...", "type": "..."}` then asserts `error["exception"] == "..."`. This is tautological - it tests dict assignment, not the TypedDict contract.

- **Lines 125-152 (TestRoutingReason):** Same issue - tests create dicts and verify the values that were assigned. The type annotations provide compile-time checks; at runtime these tests verify dict assignment works.

- **Lines 155-193 (TestTransformSuccessReason):** Same pattern. Tests like `test_transform_success_reason_has_action_field` just assign a dict and read it back.

- **Lines 218-256 (TestRoutingReasonUsage):** Repeats the pattern from TestRoutingReason. Tests construct dicts and verify values.

- **Lines 298-455 (TestTransformErrorReasonUsage):** Extensive tests that all follow the same pattern: construct a TypedDict, assert the values you just put in. While these document valid usage patterns, they provide minimal regression protection since dicts always work this way.

- **Lines 458-483 (TestNestedTypeDicts):** Same issue with TemplateErrorEntry, RowErrorEntry, and UsageStats.

- **Lines 502-525 (TestQueryFailureDetailUsage), 544-567 (TestErrorDetailUsage), 570-645:** All follow the same tautological pattern.

### 🔵 Info (minor suggestions or observations)

- **Lines 10-31 (TestExecutionErrorSchema):** Schema introspection tests (`__required_keys__`, `__optional_keys__`) are valuable - they verify the TypedDict is correctly defined and would catch accidental field changes.

- **Lines 33-58 (TestRoutingReasonSchema):** Good tests verifying the union type structure and that variants are TypedDicts.

- **Lines 61-94 (TestTransformSuccessReasonSchema):** Good schema introspection tests.

- **Lines 196-216 (TestRoutingReasonVariants):** Schema introspection tests for the discriminated union variants are valuable.

- **Lines 259-295 (TestTransformErrorReasonSchema):** Good schema verification.

- **Lines 486-499, 528-541:** Schema introspection tests are valuable.

## Verdict

**KEEP** - While the "usage" tests are largely tautological (testing dict assignment), they serve as documentation of valid usage patterns for the TypedDict contracts. The schema introspection tests (`__required_keys__`, `__optional_keys__`) are valuable. The file could be significantly reduced by removing the usage tests, but they are not actively harmful.
