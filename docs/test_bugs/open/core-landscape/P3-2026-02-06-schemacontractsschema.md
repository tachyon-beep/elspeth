# Test Bug Report: Fix weak assertions in schema_contracts_schema

## Summary

- This test file validates schema contract columns across three Landscape tables (runs, nodes, validation_errors). The tests are thorough for column existence and type verification but contain significant structural issues including code duplication, unnecessary imports, and tests that could be consolidated. The single integration test at the end provides good value by verifying actual database creation.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_core_landscape_test_schema_contracts_schema.audit.md

## Test File

- **File:** `tests/core/landscape/test_schema_contracts_schema`
- **Lines:** 204
- **Test count:** 22

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The tests provide value by verifying schema contracts, but they would benefit from parameterization to reduce duplication. The misleading "backward compatibility" docstrings should be corrected. The tests are functional and catch real schema issues; the problems are structural, not functional.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/core/landscape/test_schema_contracts_schema -v`

## Notes

- Source audit: `docs/test_audit/tests_core_landscape_test_schema_contracts_schema.audit.md`
