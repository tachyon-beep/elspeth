# Test Bug Report: Fix weak assertions in node_id_assignment

## Summary

- Solid unit test coverage for `Orchestrator._assign_plugin_node_ids()` method. Tests cover happy paths, error paths, and edge cases (pre-assigned aggregation IDs). However, heavy use of MagicMock raises concerns about overmocking - the tests verify the method's behavior with mocks but may miss issues that arise with real plugin instances.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_node_id_assignment.audit.md

## Test File

- **File:** `tests/engine/test_node_id_assignment`
- **Lines:** 220
- **Test count:** 8

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - Tests are valid and provide good coverage of the `_assign_plugin_node_ids` method. Consider adding one integration test that exercises this method through the production path (`Orchestrator.run()`) to complement these unit tests and catch any mock/real divergence.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_node_id_assignment -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_node_id_assignment.audit.md`
