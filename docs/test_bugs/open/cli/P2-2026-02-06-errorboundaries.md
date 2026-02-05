# Test Bug Report: Rewrite weak assertions in error_boundaries

## Summary

- This test file tests CLI error boundary handling for various failure scenarios (YAML errors, database errors, source file errors, exit codes). The tests are well-structured and test real CLI behavior through typer.testing.CliRunner. However, several tests have weak or overly permissive assertions that could pass even when the actual behavior is broken.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_cli_test_error_boundaries.py.audit.md

## Test File

- **File:** `tests/cli/test_error_boundaries.py`
- **Lines:** 490
- **Test count:** 19

## Findings

- **Lines 44-47:**: `test_run_yaml_syntax_error_shows_helpful_message` has an overly permissive assertion. The check `("yaml" in output and "syntax" in output) or "error" in output` will pass if the output contains just the word "error" anywhere, which is almost guaranteed for any failure. The test should be more specific about the expected error message format.
- **Lines 57-59:**: `test_validate_yaml_syntax_error_shows_helpful_message` has the same overly permissive assertion pattern.
- **Lines 74-77:**: `test_run_yaml_with_tabs_shows_helpful_error` assertion `"yaml" in output or "tab" in output or "syntax" in output or "error" in output` is extremely permissive - nearly any failure output will contain "error".
- **Lines 90-93:**: `test_run_yaml_duplicate_key_error` only asserts `exit_code != 0` and no traceback. It doesn't verify that the error message actually mentions the duplicate key problem, making it a weak test that could pass even if duplicate key errors were silently swallowed.
- **Lines 145-147:**: `test_run_sqlite_path_not_writable` only asserts `exit_code != 0` and `output.strip() != ""`. This is extremely weak - any error will pass this test, even an unrelated error.
- **Lines 196-198:**: `test_run_sqlite_path_permission_denied` only asserts `exit_code != 0` with no verification of the actual error message.
- **Lines 283-286:**: `test_run_source_file_permission_denied` uses an overly permissive assertion pattern: `"permission" in output_lower or "denied" in output_lower or "error" in output_lower`. The fallback to just "error" makes this test pass for any failure.
- **Lines 430-444:**: `test_json_mode_error_is_valid_json` has a conditional assertion block (`if '{"event": "error"' in output`) that means if the JSON error format changes, the test silently passes with no assertions about JSON validity. This is a test that can silently do nothing.
- **Lines 476-480:**: `test_validate_shows_pydantic_errors_clearly` has the issue that the assertion `assert "configuration validation failed" in output or "validation" in output` is overly broad - "validation" could appear in many contexts.
- **Lines 152-155, 244-247:**: Good use of `@pytest.mark.skipif` for root user - these tests correctly skip when permissions tests won't work.
- **Line 340:**: In `test_exit_code_one_on_config_error`, the test name says "exit code 1" but doesn't explain what distinguishes code 1 from other non-zero codes. The test verifies correct behavior but the naming could be clearer about why 1 specifically.


## Verdict Detail

**REWRITE** - While this test file tests important error boundary behaviors, too many tests have overly permissive assertions that would pass even if the actual behavior is broken. The pattern of `"specific_keyword" in output or "error" in output` defeats the purpose of error boundary testing - almost any failure will satisfy the "or error in output" branch. Tests should be more specific about expected error messages or formats. The conditional assertion block in `test_json_mode_error_is_valid_json` is particularly problematic as it can silently do nothing.

## Proposed Fix

- [ ] Tests have specific, non-permissive assertions
- [ ] Each test verifies the exact expected behavior
- [ ] No "or 'error' in output" fallback patterns
- [ ] Tests fail when actual behavior differs from expected

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/cli/test_error_boundaries.py -v`

## Notes

- Source audit: `docs/test_audit/tests_cli_test_error_boundaries.py.audit.md`
