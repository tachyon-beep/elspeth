# Test Audit: plugins/llm

**Audit Date:** 2026-02-05
**Batches:** 124-126
**Total Files:** 8
**Total Lines:** ~2,650

## Summary

| File | Lines | Rating | Key Issues |
|------|-------|--------|------------|
| test_azure_tracing.py | 432 | Good | Duplicate helper methods, fragile sys.modules patching |
| test_base.py | 666 | Good | Thorough config validation, missing edge cases |
| test_batch_errors.py | 181 | Acceptable | Tests dataclass with no logic, usage pattern tests are documentation |
| test_batch_single_row_contract.py | 204 | Needs Improvement | **Overmocking _process_batch bypasses production code** |
| test_capacity_errors.py | 58 | Good | Small, focused, correct |
| test_contract_aware_template.py | 185 | Good | Tests PipelineRow Jinja2 compatibility |
| test_llm_transform_contract.py | 247 | Good | Good mock transform design, missing error path tests |
| test_multi_query.py | 677 | Good | Comprehensive config tests, execution tested elsewhere |

## Critical Issues

### 1. Overmocking in test_batch_single_row_contract.py

**Severity:** High
**Issue:** Tests mock `_process_batch` directly, which means they verify `_process_single` correctly *propagates* a contract but NOT that `_process_batch` actually *produces* a contract. The real bug could still exist in production.

**Recommendation:** Add integration tests that exercise the full path from `_process_single` through real `_process_batch` (with only the LLM client mocked).

## Common Patterns

### Positive Patterns

1. **Test factory functions** - `create_test_transform_class()` for testing abstract classes
2. **Regression test documentation** - Tests reference specific bug tickets (P1-2026-01-31, P2-2026-02-05)
3. **Error propagation tests** - Clear distinction between retryable and non-retryable errors

### Issues to Address

1. **Duplicate code** - Helper methods duplicated across test classes
2. **`required_input_fields: []` everywhere** - Most tests opt-out of field validation
3. **Imports inside test methods** - Unusual pattern in test_multi_query.py
4. **Missing error path tests** - Several files only test happy path

## Missing Coverage Areas

1. **Concurrent LLM processing** - No thread safety tests
2. **Large payload handling** - No tests for memory with large rows/responses
3. **Unicode/special characters** - Limited testing of non-ASCII content
4. **Batch transform execution** - test_batch_single_row_contract mocks too much

## Recommendations

1. **Fix test_batch_single_row_contract.py** - Add integration tests without mocking _process_batch
2. **Extract common fixtures** - Reduce duplication in test helpers
3. **Add parametrized tests** - Combine similar tests for different providers
4. **Add error path coverage** - Test contract behavior when transforms fail
