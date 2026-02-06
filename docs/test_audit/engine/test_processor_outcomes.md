# Test Audit: tests/engine/test_processor_outcomes.py

**Lines:** 696
**Test count:** 15 test functions across 5 test classes
**Audit date:** 2026-02-05
**Batch:** 87

## Summary

Integration tests for processor outcome recording (AUD-001). Verifies that the processor records token outcomes at determination points, creating entries in the token_outcomes table for audit trail completeness. Covers all 9 outcome types, terminal uniqueness constraints, and explain() API integration.

## Test Inventory

| Class | Test | Lines | Purpose |
|-------|------|-------|---------|
| TestProcessorRecordsOutcomes | test_outcome_api_works_directly | 54-91 | Direct recorder API verification |
| TestAllOutcomeTypesRecorded | test_outcome_type_can_be_recorded (parametrized x7) | 103-159 | All 7 non-batch outcomes |
| TestAllOutcomeTypesRecorded | test_batch_outcome_type_can_be_recorded (parametrized x2) | 161-211 | CONSUMED_IN_BATCH, BUFFERED |
| TestTerminalUniquenessConstraint | test_only_one_terminal_outcome_per_token | 217-253 | Terminal uniqueness enforcement |
| TestTerminalUniquenessConstraint | test_multiple_buffered_outcomes_allowed | 255-307 | Non-terminal multiple allowed |
| TestExplainShowsRecordedOutcome | test_explain_shows_recorded_outcome | 313-344 | explain() returns recorded outcome |
| TestExplainShowsRecordedOutcome | test_explain_shows_outcome_context_fields | 346-383 | Context fields in explain() |
| TestExplainShowsRecordedOutcome | test_explain_returns_none_outcome_when_not_recorded | 385-412 | No outcome = None |
| TestEngineIntegrationOutcomes | test_processor_records_completed_outcome_with_context | 422-500 | Full RowProcessor integration |
| TestEngineIntegrationOutcomes | test_processor_records_quarantined_outcome_with_error_hash | 502-581 | Quarantine with error_hash |
| TestEngineIntegrationOutcomes | test_processor_records_forked_outcome_with_fork_group_id | 583-696 | Fork with parent/child lineage |

## Findings

### Defects

None found.

### Overmocking

None - All tests use real `LandscapeDB` (in-memory or fixture) and `LandscapeRecorder`.

### Missing Coverage

1. **No test for COALESCED outcome via RowProcessor**
   - `test_outcome_type_can_be_recorded` tests COALESCED via direct API
   - But no test exercises full processor path that results in COALESCED
   - Should add test with fork-coalesce configuration

2. **No test for EXPANDED outcome via RowProcessor**
   - Same as above - only direct API tested
   - Need processor test with deaggregation/expansion scenario

3. **No test for outcome idempotency edge cases**
   - What happens if same outcome is recorded twice?
   - Partial unique index only covers terminal, but what about same terminal twice?

4. **No test for race condition on terminal outcome**
   - What if two threads try to record different terminal outcomes?
   - The IntegrityError test is single-threaded

### Tests That Do Nothing

None - All tests have meaningful assertions.

### Inefficiency

1. **Lines 20-40: Duplicate make_source_row helper**
   - Yet another copy of this helper function
   - Should definitely be in shared conftest.py by now

2. **Lines 437-470: Inline _TestSchema definition**
   - Duplicates the schema from tests/engine/conftest.py
   - Should import from there

3. **Lines 517-519, 437-438: Repeated _TestSchema definition**
   - Two tests define identical `_TestSchema` classes
   - Should use shared definition

### Structural Issues

1. **Fixture scope mismatch**
   - `landscape_db` fixture in conftest.py is module-scoped
   - Some tests create their own `LandscapeDB.in_memory()` (lines 520, 593)
   - Inconsistent - should either all use fixture or document why some don't

2. **Test class in wrong file**
   - `TestEngineIntegrationOutcomes` (lines 415-696) tests RowProcessor behavior
   - Could be in test_processor_outcomes_integration.py for clarity
   - Or merged with test_processor_core.py

### Test Path Integrity

**PASS** - Tests use production code paths:
- Real `LandscapeRecorder` with in-memory database
- Real `RowProcessor` construction
- Real `GateSettings` for fork configuration
- Real edge registration for routing
- No manual graph construction or bypassed paths

### Info

1. **Lines 103-159: Excellent parametrized outcome coverage**
   - Tests all 7 non-batch outcomes with correct context fields
   - Assertions verify each outcome-specific field is stored correctly
   - Pattern: `(RowOutcome.X, {"context_field": "value"})`

2. **Lines 161-211: Proper FK constraint handling**
   - Batch outcomes (CONSUMED_IN_BATCH, BUFFERED) require real batch records
   - Test correctly creates batch via `recorder.create_batch()` first

3. **Lines 214-307: Critical constraint tests**
   - `test_only_one_terminal_outcome_per_token`: Verifies IntegrityError
   - `test_multiple_buffered_outcomes_allowed`: Verifies non-terminal bypass
   - These prevent audit trail corruption

4. **Lines 493-500: Clarifying comment about COMPLETED timing**
   - Comment explains: "COMPLETED token_outcomes are recorded by orchestrator at sink level"
   - Test then correctly verifies node_states instead
   - Good documentation of architectural split

5. **Lines 583-696: Comprehensive fork test**
   - Verifies FORKED parent has fork_group_id
   - Verifies children have parent lineage via `get_token_parents()`
   - Tests both outcome recording AND parent-child relationship

## Verdict

**PASS** - High-quality integration tests with comprehensive coverage of the outcome recording feature. Parametrized tests ensure all 9 outcome types are covered. Constraint tests prevent data integrity bugs. End-to-end tests verify processor-to-explain flow. Minor helper duplication and fixture inconsistency are cosmetic issues.

## Recommendations

1. **Add COALESCED and EXPANDED processor integration tests**
   - Create fork-coalesce scenario that exercises COALESCED
   - Create deaggregation scenario that exercises EXPANDED

2. **Consolidate make_source_row to conftest.py**
   - This helper is now in at least 4 test files
   - Move to tests/engine/conftest.py or tests/conftest.py

3. **Use shared _TestSchema from conftest**
   - Remove inline definitions, import from conftest

4. **Standardize fixture usage**
   - Either use `landscape_db` fixture everywhere
   - Or document why certain tests need isolated DBs

5. **Consider race condition test**
   - Add concurrent terminal outcome recording test
   - May require threading and asserting IntegrityError
