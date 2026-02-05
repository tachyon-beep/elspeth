# Test Audit: tests/engine/test_processor_pipeline_row.py

**Lines:** 182
**Test count:** 5 test functions across 2 test classes
**Audit status:** ISSUES_FOUND

## Summary

This file tests the PipelineRow support in RowProcessor (Task 6 of some migration). While the tests verify the API contract, they rely heavily on mock objects which reduces their integration value. The tests are focused but thin - they verify that the correct methods are called but don't verify the data flows correctly through the system.

## Findings

### Warning

1. **Lines 29-43 - Mock-heavy test infrastructure**
   - `_make_mock_recorder()` and `_make_mock_span_factory()` create deep mocks
   - Tests using these mocks verify method calls but not actual behavior
   - Example: `test_process_row_accepts_source_row` only checks `recorder.create_row.assert_called_once()` without verifying what was passed

2. **Lines 48-77 - `test_process_row_accepts_source_row` is shallow**
   - Only verifies that `create_row` and `create_token` were called
   - Does not verify the arguments passed to these methods
   - Does not verify the actual return value from `process_row()`

3. **Lines 79-110 - `test_process_row_creates_pipeline_row` has mixed mocking**
   - Uses mock recorder but verifies real `PipelineRow` in result
   - The mock `create_row.return_value = Mock(row_id="row_001")` means the test doesn't exercise the real row creation path
   - Line 110 asserts `result.token.row_data.contract is contract` which is valuable but could fail in production if mocks hide issues

4. **Lines 144-182 - `TestRowProcessorExistingRow` also uses excessive mocking**
   - `test_process_existing_row_accepts_pipeline_row` uses mocks for recorder
   - Key assertion is `recorder.create_row.assert_not_called()` which only verifies negative case
   - Should verify the actual token creation and data preservation

### Info

1. **Lines 112-141 - `test_process_row_requires_contract_on_source_row` is valuable**
   - Tests error handling for missing contract
   - Uses `pytest.raises` to verify the error message
   - This is a genuine contract enforcement test

## Verdict

**REWRITE** - The tests verify API contracts exist but use excessive mocking that hides integration issues. These tests should be rewritten to use real `LandscapeDB.in_memory()` instances like other processor tests. The contract enforcement test (lines 112-141) is the only test that provides genuine value without mocking concerns.
