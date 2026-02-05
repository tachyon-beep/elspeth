# Test Audit: test_multi_query.py

**File:** `tests/plugins/llm/test_multi_query.py`
**Lines:** 677
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file tests the multi-query LLM transform configuration, including QuerySpec, CaseStudyConfig, CriterionConfig, MultiQueryConfig, OutputFieldConfig, and response format building. This is the config-only test file for the multi-query transform.

## Findings

### 1. GOOD: Comprehensive Config Validation

**Positive:** Tests thoroughly cover config validation:
- Required fields: case_studies, criteria, output_mapping
- Nested config validation: CaseStudyConfig, CriterionConfig
- Empty list rejection
- Invalid type rejection

### 2. GOOD: Regression Tests for P1-2026-01-31

**Positive:** Tests at lines 375-455 are explicit regression tests for "multi-query-output-key-collisions":
- Duplicate case_study names rejected
- Duplicate criterion names rejected
- Reserved suffix collision rejected (`_usage`)

These prevent serious data corruption bugs.

### 3. GOOD: Query Expansion Tests

**Positive:** `test_expand_queries_creates_cross_product` (lines 338-373) verifies that 2 case studies x 2 criteria = 4 query specs with correct output prefixes.

### 4. INCOMPLETE: No Transform Execution Tests

**Severity:** High
**Issue:** This file ONLY tests configuration. There are no tests for:
- Actually executing multi-query transform
- Processing rows through the transform
- LLM call behavior
- Result merging
**Impact:** Configuration is validated but actual transform behavior is not tested in this file.
**Recommendation:** Verify there's a separate file testing multi-query transform execution. If not, this is a critical gap.

### 5. GOOD: JSON Schema Generation Tests

**Positive:** `TestOutputFieldConfig` (lines 458-537) and `TestResponseFormatBuilding` (lines 540-677) verify:
- All JSON types map correctly (string, integer, number, boolean, enum)
- Enum requires non-empty values list
- Non-enum rejects values parameter
- build_json_schema generates correct schema
- build_response_format generates correct OpenAI format

### 6. MISSING: Template Context Row Field Test

**Severity:** Medium
**Issue:** `test_query_spec_build_template_context` (lines 26-50) verifies `context["row"] == row` but doesn't test that `row` is accessible in templates as intended.
**Impact:** Template rendering may fail even if context is correct.
**Recommendation:** Add tests that actually render templates with this context.

### 7. STRUCTURAL: Imports Inside Test Methods

**Severity:** Low
**Issue:** Several tests import inside the test method:
```python
def test_case_study_requires_name(self) -> None:
    from elspeth.plugins.llm.multi_query import CaseStudyConfig
```
**Impact:** Unusual pattern, harder to read. If import fails, test fails with ImportError not assertion.
**Recommendation:** Move imports to module level. If testing optional dependencies, use `pytest.importorskip`.

### 8. GOOD: to_template_data Tests

**Positive:** Tests for `CaseStudyConfig.to_template_data()` and `CriterionConfig.to_template_data()` (lines 144-221) verify the dict format used for template injection.

### 9. MISSING: Response Parsing Tests

**Severity:** High
**Issue:** Tests verify we *send* the correct response_format to OpenAI, but don't test *parsing* the structured response back.
**Impact:** LLM may return correct JSON but parsing/extraction may fail.
**Recommendation:** Add tests for response parsing with different output_mapping configurations.

## Missing Coverage

1. **Transform execution** - No tests for actual row processing
2. **Response parsing** - No tests for extracting fields from LLM response
3. **Error handling** - No tests for malformed LLM responses
4. **Concurrency** - No tests for parallel query execution
5. **Template rendering** - No tests for actual Jinja2 rendering with context
6. **Field mapping** - No tests for output field name construction (`{prefix}_{suffix}`)

## Structural Issues

1. **Config-only testing** - 677 lines of config tests but no execution tests
2. **Imports inside methods** - Unusual pattern for commonly-used imports
3. **No fixtures** - Every test creates config from scratch, could use fixtures

## Overall Assessment

**Rating:** Good
**Verdict:** This file provides excellent coverage for multi-query config validation and JSON schema generation. It intentionally focuses on configuration testing as execution is covered by separate test files (`test_azure_multi_query.py`, etc.). The config tests are thorough and include good regression tests for collision bugs (P1-2026-01-31).

**Note:** Multi-query transform execution IS tested elsewhere:
- `test_azure_multi_query.py` - Azure implementation
- `test_azure_multi_query_retry.py` - Retry behavior
- `test_openrouter_multi_query.py` - OpenRouter implementation

This file correctly focuses on config-only testing as a separation of concerns.
