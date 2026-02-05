# Test Audit: tests/engine/test_audit_sweep.py

**Lines:** 920
**Test count:** 9 test functions
**Audit status:** PASS

## Summary

This is an excellent, well-designed test file that implements critical audit sweep queries to verify the Token Outcome Assurance contract. The tests use production code paths (via `build_production_graph` and `instantiate_plugins_from_config`) rather than mocking, which aligns with the codebase's "Test Path Integrity" principle. The SQL queries are directly from the specification document, ensuring tests validate actual contract requirements.

## Findings

### Information

- **Lines 42-164**: The `run_audit_sweep()` function implements 7 comprehensive SQL queries that directly verify audit trail invariants. This is excellent defense-in-depth testing that validates database-level consistency regardless of how individual component tests behave.

- **Lines 188-264**: Custom test fixtures (`_ValueSchema`, `_ListSource`, `_PassTransform`, `_CollectSink`) are well-implemented minimal implementations that avoid overmocking by still exercising real contract creation and schema handling.

- **Lines 470-549**: `test_fork_coalesce_merged_token_has_terminal_outcome` is particularly valuable - it documents and tests a P1 bug fix scenario with clear comments explaining the expected token lifecycle.

- **Lines 667-815**: `test_timeout_triggered_coalesce_records_completed_outcome` tests a complex edge case (timeout-triggered coalesce) with thorough documentation. The test includes a slow source implementation that properly exercises the timeout code path.

- **Lines 817-920**: `test_multiple_gates_fork_coalesce_step_index` tests a specific bug scenario with step index collisions. The test comments clearly document the bug being prevented.

### Design Notes

- The tests appropriately use real orchestrator runs rather than mocking internal state, validating the full stack from source to sink.

- Each test class is well-organized by scenario type: simple pipelines, gate routing, error handling, metrics, and fork/coalesce.

- The `assert_audit_sweep_clean()` helper provides actionable error messages that reference documentation when gaps are found.

## Verdict

**KEEP** - This is a high-quality test file that serves as a critical CI gate for audit trail completeness. The tests are thorough, well-documented, and use production code paths appropriately. No changes needed.
