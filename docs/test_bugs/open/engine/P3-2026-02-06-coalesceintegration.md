# Test Bug Report: Fix weak assertions in coalesce_integration

## Summary

- This is a comprehensive integration test file that exercises fork/coalesce pipelines through the production code path using `build_production_graph()`. The tests are well-structured and follow the CLAUDE.md requirement to avoid manual graph construction. However, there are some issues with overmocking via `hasattr()` checks, module-scoped fixtures that may cause test pollution, and one potentially brittle timing-based test.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_coalesce_integration.py.audit.md

## Test File

- **File:** `tests/engine/test_coalesce_integration.py`
- **Lines:** 1187
- **Test count:** 11

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - This is valuable integration test coverage that exercises production code paths. The issues identified are minor:
- The `hasattr()` pattern should be fixed to call `to_dict()` directly
- The timing-based test could be improved with deterministic clock injection
- Module-scoped fixture is a minor concern but acceptable given run_id filtering

The tests provide important coverage for fork/coalesce scenarios and have caught real bugs per the documented regression test purposes.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_coalesce_integration.py -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_coalesce_integration.py.audit.md`
