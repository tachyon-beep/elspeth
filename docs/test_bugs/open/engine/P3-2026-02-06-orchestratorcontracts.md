# Test Bug Report: Fix weak assertions in orchestrator_contracts

## Summary

- This test file provides excellent coverage of schema contract recording in the orchestrator, including source contracts, transform schema evolution, quarantine-first scenarios, and secret resolution recording. The tests verify database state directly via SQLAlchemy queries, ensuring audit trail integrity. However, there is moderate code duplication with similar plugin classes repeated across tests.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_contracts.py.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_contracts.py`
- **Lines:** 732
- **Test count:** 9

## Findings

- See audit file for details


## Verdict Detail

**KEEP** with minor cleanup - The tests provide strong coverage of critical audit trail functionality. The code duplication is moderate and doesn't significantly impair readability. Consider extracting `CollectSink` to module level when convenient, but the current structure is acceptable.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_contracts.py -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_contracts.py.audit.md`
