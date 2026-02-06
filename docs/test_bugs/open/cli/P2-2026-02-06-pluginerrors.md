# Test Bug Report: Rewrite weak assertions in plugin_errors

## Summary

- This test file focuses on plugin instantiation error handling and configuration validation through the CLI. The tests cover important error scenarios (unknown plugins, missing required options, fork/join patterns) but several have weak assertions that could pass even when the system behavior is incorrect. The tests also use verbose YAML configurations that could be DRY'd up with fixtures.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_cli_test_plugin_errors.py.audit.md

## Test File

- **File:** `tests/cli/test_plugin_errors.py`
- **Lines:** 480
- **Test count:** 8

## Findings

- **Lines 46-47:**: `test_unknown_source_plugin_error` - The assertions `"nonexistent_source" in result.output.lower()` and `"available" in result.output.lower()` are too weak. These would pass if the output contained these strings anywhere, including in an unrelated error message or debug output. The test doesn't verify that a specific error type was raised or that the error message follows the expected format. This could provide false confidence.
- **Lines 71-72:**: `test_unknown_transform_plugin_error` - Same issue as above. The assertion only checks for substring presence rather than verifying the actual error structure.
- **Lines 109-117:**: `test_plugin_initialization_error` - The compound assertion `"path" in output_lower or "csv" in output_lower or "source" in output_lower` is extremely weak. This would pass if ANY of these common words appeared anywhere in the output. The test doesn't verify that the actual validation error was raised for the missing `path` option.
- **Lines 15-51, 75-121, 144-223:**: Multiple tests create nearly identical YAML configuration strings. This duplication should be refactored into fixtures or factory functions. Each test spends 20-30 lines on configuration that differs only in small ways.
- **Lines 144-222:**: `test_fork_join_validation` - The test validates that a fork/join configuration passes, but the assertion `"pipeline configuration valid" in result.output.lower()` only checks for substring presence. It doesn't verify that the fork/join topology was actually validated or that the DAG was correctly constructed.
- **Lines 225-303:**: `test_fork_to_separate_sinks_without_coalesce` - The comment on lines 297-300 acknowledges that the test cannot verify actual DAG structure. This limits the test's value to only checking that the configuration is accepted, not that it's correctly processed.
- **Lines 306-387:**: `test_coalesce_compatible_branch_schemas` - The extensive docstring (lines 306-320) essentially admits this test is incomplete: "LIMITATION: This test uses identical transforms on both branches, so schemas are always compatible." The test cannot actually verify schema incompatibility detection.
- **Lines 390-479:**: `test_dynamic_schema_to_specific_schema_validation` - Contains two sub-tests in one function (lines 404-436 and 439-479). These should be split into separate test functions. The docstring (lines 397-399) also mentions a "BUG" that needs to be addressed, suggesting the test may not be testing the intended behavior.
- **Lines 123-141:**: `test_schema_extraction_from_instance` - Good test that verifies critical invariant (schemas must not be None after instantiation). Uses appropriate assertions with descriptive messages.
- **Line 7:**: Imports `TypeAdapter` from pydantic - good use of typed configuration validation.
- **Lines 38-50, 101-120, 208-222, etc.:**: Good use of `finally` blocks to clean up temporary files, preventing test pollution.


## Verdict Detail

**REWRITE** - The test file covers important error handling scenarios but the assertions are too weak to provide meaningful confidence. The substring-presence checks could pass even when the system produces completely wrong output. The tests should:
1. Use more specific assertions (e.g., check for specific error codes, exception types, or structured error formats)
2. Extract common YAML configurations into fixtures
3. Split the multi-case tests into individual test functions
4. Address the acknowledged limitations in fork/join schema compatibility testing

## Proposed Fix

- [ ] Tests have specific, non-permissive assertions
- [ ] Each test verifies the exact expected behavior
- [ ] No "or 'error' in output" fallback patterns
- [ ] Tests fail when actual behavior differs from expected

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/cli/test_plugin_errors.py -v`

## Notes

- Source audit: `docs/test_audit/tests_cli_test_plugin_errors.py.audit.md`
