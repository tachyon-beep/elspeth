# Test Audit: tests/core/test_token_outcomes.py

**Lines:** 598
**Test count:** 32
**Audit status:** PASS

## Summary

This is a comprehensive test file for the token outcome recording system, covering the dataclass structure, database schema, recorder methods, contract validation, and integration with the `explain()` lineage function. The tests are well-organized across six test classes, use appropriate fixtures with module-scoped database for efficiency, and exercise real database operations without excessive mocking.

## Findings

### Info

- **Lines 9-28**: Smart fixture design - module-scoped `landscape_db` avoids repeated schema creation (noted as ~5-10ms per instantiation), while function-scoped `recorder` provides test isolation. Tests use unique run_ids for data isolation within the shared database.
- **Lines 31-165** (`TestTokenOutcomeDataclass`, 9 tests): Thorough validation of the `TokenOutcome` dataclass structure - required fields, instantiation, immutability (frozen), optional fields, context fields (sink, batch), and enum usage. The loop over all `RowOutcome` values (lines 145-165) is a good pattern for exhaustive enum coverage.
- **Lines 168-216** (`TestTokenOutcomesTableSchema`, 5 tests): Schema verification tests confirm table existence, required columns, primary key, and foreign keys. These are valuable for schema contract enforcement.
- **Lines 219-351** (`TestRecordTokenOutcome`, 5 tests): Tests the recording path including terminal outcomes, BUFFERED-then-terminal sequences, and duplicate terminal rejection via `IntegrityError`.
- **Lines 354-496** (`TestOutcomeContractValidation`, 9 tests): Validates that each outcome type requires its expected context field (sink_name, fork_group_id, error_hash, batch_id, etc.). This is critical contract enforcement testing.
- **Lines 499-543** (`TestGetTokenOutcome`, 4 tests): Tests retrieval including terminal-over-buffered precedence and nonexistent token handling.
- **Lines 546-598** (`TestExplainIncludesOutcome`, 2 tests): Integration tests verifying that `explain()` includes outcome data when recorded and returns `None` when not.

### Warning

- **Lines 222-254, 360-379**: Two nearly identical `run_with_token` fixtures exist in different test classes. While this provides isolation, consider whether a shared fixture would reduce duplication without sacrificing clarity.

## Verdict

**KEEP** - This is an excellent, comprehensive test file. It covers dataclass structure, schema definition, recording operations, contract validation, retrieval, and integration with lineage. The fixture design balances efficiency (module-scoped DB) with isolation (function-scoped recorder). The tests exercise real database operations and validate important audit trail contracts.
