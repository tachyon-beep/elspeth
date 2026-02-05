# Test Audit: tests/core/retention/test_purge.py

**Lines:** 2426
**Test count:** 37 test functions across 14 test classes
**Audit status:** PASS

## Summary

This is a comprehensive, well-structured test file for `PurgeManager` - the component responsible for payload retention and deletion in ELSPETH's audit trail. The tests cover normal operations, edge cases, bug regression tests, content-addressable storage semantics, cross-run isolation, reproducibility grade degradation, and I/O error handling. The test design follows best practices with clear documentation linking to specific bug tickets.

## Test Inventory

### Test Classes and Functions

1. **TestPurgeResult** (1 test)
   - `test_purge_result_fields` - Validates PurgeResult dataclass fields

2. **TestFindExpiredRowPayloads** (6 tests)
   - `test_find_expired_row_payloads` - Finds payloads older than retention period
   - `test_find_expired_respects_retention` - Does not flag recent payloads
   - `test_find_expired_ignores_incomplete_runs` - Does not flag running runs
   - `test_find_expired_excludes_null_refs` - Handles null source_data_ref
   - `test_find_expired_with_as_of_date` - Tests as_of parameter for cutoff
   - `test_find_expired_deduplicates_shared_refs` - Verifies deduplication

3. **TestPurgePayloads** (6 tests)
   - `test_purge_payloads_deletes_content` - Verifies actual deletion
   - `test_purge_preserves_landscape_hashes` - Hashes survive payload deletion
   - `test_purge_tracks_skipped_refs` - Non-existent refs tracked as skipped
   - `test_purge_tracks_failed_refs` - Failed deletions tracked correctly
   - `test_purge_measures_duration` - Duration measurement with monkeypatch
   - `test_purge_empty_list` - Empty refs list returns empty result

4. **TestFindExpiredCallPayloads** (2 tests)
   - `test_find_expired_includes_call_request_refs` - Call request payloads found
   - `test_find_expired_includes_call_response_refs` - Call response payloads found

5. **TestFindExpiredRoutingPayloads** (1 test)
   - `test_find_expired_includes_routing_reason_refs` - Routing reason payloads found

6. **TestFindExpiredAllPayloadRefs** (2 tests)
   - `test_find_expired_payload_refs_returns_deduplicated_union` - All types unified
   - `test_find_expired_payload_refs_respects_retention` - Retention respected

7. **TestContentAddressableSharedRefs** (4 tests)
   - `test_shared_row_ref_excluded_when_used_by_recent_run` - Shared refs protected
   - `test_shared_call_ref_excluded_when_used_by_recent_run` - Call refs protected
   - `test_exclusive_expired_ref_is_returned` - Exclusive refs returned
   - `test_shared_ref_excluded_when_used_by_running_run` - Running runs protect refs

8. **TestCallJoinRunIsolation** (2 tests)
   - `test_expired_call_ref_returned_when_same_node_id_exists_in_recent_run` - Cross-run isolation bug test
   - `test_recent_call_ref_not_returned_when_expired_run_has_same_node_id` - Inverse scenario

9. **TestRoutingJoinRunIsolation** (1 test)
   - `test_expired_routing_ref_returned_when_same_node_id_exists_in_recent_run` - Routing cross-run isolation

10. **TestPurgeUpdatesReproducibilityGrade** (8 tests)
    - `test_purge_degrades_replay_reproducible_to_attributable_only` - Core grade degradation
    - `test_purge_keeps_full_reproducible_unchanged` - Deterministic runs unchanged
    - `test_purge_keeps_attributable_only_unchanged` - Already lowest grade
    - `test_purge_updates_multiple_affected_runs` - Multi-run grade updates
    - `test_purge_empty_refs_does_not_update_any_grades` - Empty purge no-op
    - `test_purge_call_payloads_also_degrades_grade` - Call payload grade impact
    - `test_purge_does_not_degrade_grade_when_deletion_fails` - Failed deletion preserves grade
    - `test_purge_degrades_grade_when_some_deletions_succeed` - Partial success behavior

11. **TestFailedRunsIncludedInPurge** (3 tests)
    - `test_failed_run_payloads_are_eligible_for_purge` - Failed runs purgeable
    - `test_failed_run_does_not_protect_shared_refs` - Failed runs don't protect refs
    - `test_running_run_still_protects_refs` - Running runs still protected (regression)

12. **TestPurgeIOErrorHandling** (3 tests)
    - `test_purge_continues_after_exists_raises_exception` - exists() exception handling
    - `test_purge_continues_after_delete_raises_exception` - delete() exception handling
    - `test_purge_updates_grades_despite_io_errors` - Grade updates with I/O errors

## Findings

### 🔵 Info

1. **Excellent bug ticket traceability (Lines 726-732, 825-830, 1013-1019, 1231-1241, 1385-1392, 1476-1481, 2025-2031, 2185-2191)**: Test classes reference specific bug tickets (P2-2026-01-19, P2-2026-01-22, P2-2026-01-28, P2-2026-01-31) with clear explanations of the bug scenarios. This is exemplary practice for regression testing.

2. **Well-documented edge cases (Lines 1243-1259, 1394-1399)**: The cross-run isolation bug tests include detailed docstrings explaining the subtle join ambiguity issues with node_id reuse. This documentation will help future maintainers understand why these tests exist.

3. **Appropriate use of inline mock classes (Lines 635-664, 830-854, 2204-2234, 2264-2292, 2327-2355)**: Custom mock classes are defined inline with clear docstrings explaining their behavior (FailingPayloadStore, ExistsRaisingPayloadStore, etc.). This keeps test-specific mocks close to where they're used.

4. **Module-scoped database fixture (Lines 27-32)**: Uses `scope="module"` for the LandscapeDB fixture, which is appropriate for performance when tests don't conflict with each other.

5. **Comprehensive helper functions (Lines 35-221)**: The file includes well-documented helper functions for creating test data (_create_state, _create_token, _create_call, etc.) that reduce boilerplate in individual tests.

6. **MockPayloadStore properly implements interface (Lines 224-256)**: The main mock implements all necessary methods (store, exists, delete, retrieve) with appropriate behavior for testing.

### 🟡 Warning

1. **Large file size (2426 lines)**: While the tests are well-organized, the file size is substantial. Consider whether splitting into separate files by test category (e.g., `test_purge_expired.py`, `test_purge_grades.py`, `test_purge_io_errors.py`) would improve maintainability. However, since all tests share the module-scoped fixture and helper functions, keeping them together is defensible.

2. **Database state accumulation (potential)**: The module-scoped `landscape_db` fixture means test data accumulates across all tests. Each test creates unique UUIDs for isolation, but this could affect query performance in very large test runs. This is mitigated by the in-memory database, but worth noting.

## Verdict

**KEEP** - This is an exemplary test file that demonstrates best practices for:
- Regression testing with clear bug ticket references
- Testing content-addressable storage semantics
- Testing cross-run data isolation
- Testing error handling and partial failure scenarios
- Testing state transitions (reproducibility grade degradation)

The tests are thorough, well-documented, and test real integration scenarios using the actual database schema rather than excessive mocking. The file size is justified by the comprehensive coverage of a complex subsystem.
