# Test Bug Report: Split monolithic test file plugin_protocols

## Summary

- This file contains a single test that validates schema validation during CSVSource construction. While the test is valid and tests real behavior, the filename is misleading - it tests source initialization behavior, not plugin protocol contracts. The test coverage is minimal for a file titled "plugin_protocols".

## Severity

- Severity: minor
- Priority: P2
- Verdict: **SPLIT**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_contracts_test_plugin_protocols.audit.md

## Test File

- **File:** `tests/contracts/test_plugin_protocols`
- **Lines:** 27
- **Test count:** 1

## Findings

- **Line 6-27:**: The single test validates CSVSource schema validation during __init__, which is useful but does not match the file name "test_plugin_protocols.py". This should either be renamed to "test_source_validation.py" or moved to a more appropriate location (e.g., tests/plugins/sources/test_csv_source.py).
- **Lines 12-17:**: The "valid schema - should succeed" case has no assertion beyond "CSVSource(config)" not raising. While this is valid (testing no exception), adding `assert source is not None` or similar would make the intent clearer.


## Verdict Detail

**SPLIT** - The test itself is valid but lives in the wrong file. Consider moving to tests/plugins/sources/test_csv_source.py under a "schema validation during init" section, or rename this file to better reflect its actual content.

## Proposed Fix

- [ ] Large test file split into focused modules
- [ ] Each module has a single responsibility
- [ ] Shared fixtures extracted to conftest.py
- [ ] All original test coverage preserved

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/contracts/test_plugin_protocols -v`

## Notes

- Source audit: `docs/test_audit/tests_contracts_test_plugin_protocols.audit.md`
