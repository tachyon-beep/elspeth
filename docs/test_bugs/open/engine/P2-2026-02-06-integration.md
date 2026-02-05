# Test Bug Report: Split monolithic test file integration

## Summary

- This is a comprehensive integration test file covering the full engine execution lifecycle including audit trail verification, fork/coalesce operations, routing, retry behavior, and error handling. The tests are valuable and thorough, but the file suffers from significant structural issues: excessive inline class duplication (10+ copies of nearly identical ListSource/CollectSink), very large file size making maintenance difficult, and some tests that manually build graphs rather than using production paths (though many do use production paths correctly). The core test logic is sound and validates critical audit requirements.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **SPLIT**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_integration.py.audit.md

## Test File

- **File:** `tests/engine/test_integration.py`
- **Lines:** 3696
- **Test count:** 28

## Findings

- See audit file for details


## Verdict Detail

**SPLIT** - The test logic is valuable and should be preserved, but the file needs structural improvement:

1. Extract the inline class definitions to use the existing `_ListSource`/`_CollectSink` module-level helpers, or move to conftest
2. Rename or rewrite `_build_production_graph` to either actually use production paths OR rename to `_build_test_graph` to be honest about what it does
3. Split into 4-5 smaller, focused test files by category (audit spine, fork/coalesce, retry, error recovery, explain queries)

The core test assertions and scenarios are well-designed and catch real issues; the structural problems are about maintainability, not correctness.

## Proposed Fix

- [ ] Large test file split into focused modules
- [ ] Each module has a single responsibility
- [ ] Shared fixtures extracted to conftest.py
- [ ] All original test coverage preserved

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_integration.py -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_integration.py.audit.md`
