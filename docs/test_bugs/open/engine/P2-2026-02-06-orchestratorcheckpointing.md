# Test Bug Report: Rewrite weak assertions in orchestrator_checkpointing

## Summary

- This test file provides comprehensive coverage of the orchestrator's checkpointing functionality, including checkpoint creation frequency, interval-based checkpointing, checkpoint preservation on failure, and graceful handling when checkpointing is disabled. The tests properly use production graph construction via `build_production_graph()`. However, there is significant code duplication with nearly identical plugin class definitions repeated across tests.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_checkpointing.py.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_checkpointing.py`
- **Lines:** 718
- **Test count:** 8

## Findings

- See audit file for details


## Verdict Detail

**REWRITE** - The file tests important functionality correctly, but the extreme code duplication (~400 lines of repeated plugin class definitions) significantly hurts maintainability. Extract shared test plugins to module level or fixtures. Additionally, the manual graph construction in `test_checkpoint_preserved_on_failure` should be refactored to use production factories to maintain test path integrity.

## Proposed Fix

- [ ] Tests have specific, non-permissive assertions
- [ ] Each test verifies the exact expected behavior
- [ ] No "or 'error' in output" fallback patterns
- [ ] Tests fail when actual behavior differs from expected

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_checkpointing.py -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_checkpointing.py.audit.md`
