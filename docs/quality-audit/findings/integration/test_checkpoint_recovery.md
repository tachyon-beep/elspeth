# Test Quality Review: test_checkpoint_recovery.py

## Summary
Integration tests for checkpoint/recovery functionality. Tests are well-structured with good isolation, but have several critical issues: mutable shared state across tests, missing auditability verification, incomplete error scenario coverage, and fixture pollution vulnerabilities.

## Poorly Constructed Tests

### Test: test_full_resume_processes_remaining_rows (line 293)
**Issue**: Mutation of shared file system state without cleanup guarantee
**Evidence**:
```python
# Creates output file that persists if test fails
output_path = tmp_path / "resume_output.csv"
with open(output_path, "w") as f:
    f.write("id,name\n")
    # ... writes rows 0-2
```
**Fix**: Use pytest fixture with explicit cleanup or ensure tmp_path cleanup is reliable. Add explicit assertion that output file starts in expected state before writing.
**Priority**: P2

### Test: test_full_resume_processes_remaining_rows (line 293)
**Issue**: Magic graph mutation bypasses proper construction
**Evidence**:
```python
# Manually set the sink_id_map and transform_id_map since we're building
# the graph manually (not from config)
graph._sink_id_map = {"default": "sink"}
graph._transform_id_map = {0: "xform"}
graph._output_sink = "default"
```
**Fix**: ExecutionGraph should provide a public API for this scenario, or the test should use proper config-based graph construction. Direct manipulation of private attributes violates encapsulation and will break silently if internal implementation changes.
**Priority**: P1

### Test: test_full_resume_processes_remaining_rows (line 293)
**Issue**: No verification of audit trail completeness after resume
**Evidence**: Test verifies rows were processed (`assert result.rows_processed == 2`) and output file content, but does not verify Landscape records (token states, node states, edges traversed) match expected audit trail for resumed run.
**Fix**: Query Landscape DB after resume and verify:
- All tokens have correct terminal states
- Node states recorded for resumed rows (3, 4)
- No duplicate audit records for checkpointed rows (0-2)
- Checkpoint was deleted after successful completion
**Priority**: P1

### Test: test_full_checkpoint_recovery_cycle (line 53)
**Issue**: Assertion-only test with no state verification
**Evidence**:
```python
# 5. Get unprocessed rows (setup creates 5 rows 0-4, checkpoint at sequence 2)
unprocessed = recovery_mgr.get_unprocessed_rows(run_id)
assert len(unprocessed) == 2  # rows 3 and 4
```
**Fix**: Verify which specific rows are returned (ids "r3" and "r4"), their order, and that they match expected row_index values. Current test would pass if ANY two rows were returned.
**Priority**: P2

### Test: test_recovery_with_aggregation_state (line 117)
**Issue**: No verification of aggregation state integrity constraints
**Evidence**: Test stores and retrieves aggregation state but doesn't verify:
- State structure matches expected schema
- Nested data types preserved correctly (list of dicts)
- State is NOT mutated during retrieval
**Fix**: Add assertions that verify the retrieved state is deeply equal (not just `==`), and that buffer contents are the exact objects stored. Consider testing edge cases like empty buffer, None values in state.
**Priority**: P2

### Test: test_checkpoint_sequence_ordering (line 79)
**Issue**: Weak ordering verification allows adjacent duplicates
**Evidence**:
```python
for i in range(len(checkpoints) - 1):
    assert checkpoints[i].sequence_number < checkpoints[i + 1].sequence_number
```
**Fix**: This allows `[1, 2, 2, 3]` to pass. Verify strict monotonic increase AND that sequence numbers match expected values `[2, 3, 4]`. Also verify no gaps (or document why gaps are acceptable).
**Priority**: P2

### Test: _setup_partial_run helper (line 207)
**Issue**: Hardcoded "failed" status masks actual run state
**Evidence**:
```python
conn.execute(
    runs_table.insert().values(
        # ...
        status="failed",
    )
)
```
**Fix**: The helper unconditionally sets status="failed", but recovery semantics may differ for "failed" vs "interrupted" vs "crashed". Test should explicitly document why "failed" is correct, or parameterize status to test different recovery scenarios.
**Priority**: P2

### Test: test_checkpoint_hash_matches_graph_at_creation_time (line 532)
**Issue**: Conditional assertion that can be silently skipped
**Evidence**:
```python
if expected_hash != modified_hash:
    # Graph modification changed the hash (as expected for topology changes)
    assert checkpoint.upstream_topology_hash != modified_hash, "..."
```
**Fix**: This assertion only runs IF the graph modification changed the hash. If graph structure changes don't affect hash (due to bug), this assertion never runs and test passes incorrectly. Make this unconditional: `assert expected_hash != modified_hash, "Test setup failed: graph modification must change hash"` followed by the checkpoint verification.
**Priority**: P1

## Misclassified Tests

### Test: TestCheckpointTopologyHashAtomicity (line 517)
**Issue**: Integration test class testing unit-level atomicity concern
**Evidence**: Tests specifically verify that `create_checkpoint()` captures topology hash correctly. This is testing internal implementation behavior (when hash is computed), not end-to-end checkpoint/recovery flow.
**Fix**: Move to unit test file `tests/core/checkpoint/test_manager_atomicity.py` or similar. Integration tests should verify observable behavior (recovery succeeds/fails), not implementation details (when hash is computed).
**Priority**: P2

### Test: test_checkpoint_validates_graph_parameter (line 621)
**Issue**: Unit test in integration suite
**Evidence**: Tests parameter validation for `create_checkpoint()` - this is input validation, not integration behavior.
**Fix**: Move to `tests/core/checkpoint/test_manager.py` with other parameter validation tests.
**Priority**: P3

### Test: test_checkpoint_validates_node_exists_in_graph (line 666)
**Issue**: Unit test in integration suite
**Evidence**: Same as above - tests parameter validation edge case.
**Fix**: Move to `tests/core/checkpoint/test_manager.py`.
**Priority**: P3

## Infrastructure Gaps

### Gap: No fixture for realistic audit trail
**Issue**: Tests create minimal database records but don't exercise complete audit trail (missing node_states, edges, route decisions, retry attempts).
**Evidence**: `_setup_partial_run` creates rows/tokens but no node states, no edges, no transform outputs.
**Fix**: Create fixture `realistic_partial_run` that:
- Records node states for processed rows (0-2)
- Creates edges for token movement
- Simulates a transform that actually modifies data
- Includes at least one retry attempt
This would catch recovery bugs where incomplete audit trail causes resume to fail.
**Priority**: P1

### Gap: No testing of checkpoint failure scenarios
**Issue**: No tests verify behavior when checkpoint creation fails (disk full, transaction rollback, database constraint violation).
**Evidence**: All tests assume `create_checkpoint()` succeeds.
**Fix**: Add test that mocks database failure during checkpoint write and verifies:
- Exception propagates correctly
- No partial checkpoint record remains
- Run can still be retried (no corruption)
**Priority**: P1

### Gap: Repeated database setup without reusable fixtures
**Issue**: Multiple tests create runs/nodes/rows with similar boilerplate.
**Evidence**: `test_full_resume_processes_remaining_rows` duplicates 80+ lines of setup from `_setup_partial_run` with slight variations.
**Fix**: Create parametrized fixtures:
- `@pytest.fixture` for run with N rows
- `@pytest.fixture` for checkpoint at position M
- Compose fixtures instead of copy-paste
**Priority**: P2

### Gap: No testing of concurrent checkpoint scenarios
**Issue**: No tests verify thread-safety or race conditions when multiple processes attempt checkpoint/recovery.
**Evidence**: All tests are single-threaded.
**Fix**: Add test that:
- Starts two threads attempting to resume same run
- Verifies only one succeeds
- Verifies no duplicate processing or audit corruption
Note: This may require database-level locks, not just application logic.
**Priority**: P2

### Gap: No property-based testing for checkpoint ordering
**Issue**: Sequence number ordering is critical but only tested with hand-picked values [2, 3, 4].
**Evidence**: `test_checkpoint_sequence_ordering` uses hardcoded sequences.
**Fix**: Use Hypothesis to generate random sequence numbers and checkpoint counts, verify ordering invariants hold. Would catch edge cases like MAX_INT, negative numbers, non-consecutive sequences.
**Priority**: P3

### Gap: Missing cleanup verification
**Issue**: No tests verify that test database is properly cleaned between tests.
**Evidence**: Tests use `tmp_path` fixture but don't explicitly verify isolation - if `_setup_partial_run` leaks state, subsequent tests could see it.
**Fix**: Add test class teardown that verifies:
- No rows remain in any Landscape tables
- No checkpoint records remain
- No orphaned payload files
Alternatively, add a test that runs twice and verifies second run sees empty database.
**Priority**: P2

### Gap: No verification of checkpoint retention policy
**Issue**: Tests verify checkpoint creation and deletion, but not retention policy (e.g., "keep last N checkpoints").
**Evidence**: `test_checkpoint_cleanup_after_completion` just verifies all deleted, not selective retention.
**Fix**: If retention policy exists, add tests that:
- Create 10 checkpoints
- Verify only last 3 retained (or whatever policy is)
- Verify oldest deleted correctly
**Priority**: P3

## Positive Observations

- **Good fixture isolation**: `test_env` fixture creates fresh database per test class, reducing cross-test pollution
- **Clear test naming**: Test names describe expected behavior ("test_full_checkpoint_recovery_cycle")
- **Good use of helper methods**: `_setup_partial_run` reduces duplication for common setup
- **Comprehensive checkpoint lifecycle**: Tests cover creation, retrieval, ordering, cleanup, and resume
- **Bug-specific regression tests**: TestCheckpointTopologyHashAtomicity documents Bug #1 and Bug #9 fixes with explicit test cases

---

## Confidence Assessment
**Confidence Level**: High

I have high confidence in this assessment because:
1. Read complete test file (724 lines)
2. Read CLAUDE.md to understand project standards (auditability, three-tier trust, no bug-hiding)
3. Analyzed test structure, assertions, setup/teardown patterns
4. Identified specific line numbers and code evidence for all findings

## Risk Assessment

**High Risk Issues** (P1):
- Mutable private state manipulation in tests (line 494-496)
- Missing audit trail verification after resume (line 293)
- Conditional assertion that can be skipped (line 617-619)
- No realistic audit trail fixture
- No checkpoint failure scenario testing

**Medium Risk Issues** (P2):
- Weak assertion on unprocessed rows (line 76)
- Incomplete aggregation state verification (line 117)
- Weak sequence ordering check (line 109-110)
- Hardcoded "failed" status without justification (line 240)
- File system mutation without cleanup guarantee (line 441-445)
- Test misclassification (atomicity tests)

**Low Risk Issues** (P3):
- Unit tests in integration suite
- Missing property-based testing
- Missing retention policy tests

## Information Gaps

1. **Checkpoint retention policy**: Unknown if system keeps all checkpoints or implements retention (affects whether gap is real)
2. **Expected run status semantics**: Unclear if "failed" vs "interrupted" vs "crashed" have different recovery behaviors (affects status hardcoding finding)
3. **Concurrency requirements**: Unknown if system must support concurrent recovery attempts (affects priority of concurrency gap)
4. **Graph API design**: Unknown if ExecutionGraph intentionally lacks public API for sink/transform mapping (affects priority of private attribute access finding)

## Caveats

1. **Integration vs Unit boundary**: I classified topology hash atomicity tests as "misclassified integration tests," but reasonable engineers could argue they belong in integration suite because they test cross-component behavior (CheckpointManager + ExecutionGraph interaction). This is a judgment call.

2. **Test philosophy**: My findings assume "no silent failures" philosophy from CLAUDE.md (crash on unexpected state). If project accepts defensive testing where tests pass with degraded coverage, some findings (conditional assertions, weak ordering checks) would be lower priority.

3. **Property testing priority**: I marked property-based testing gaps as P3 because existing tests cover documented bugs. However, if this is pre-release RC-1 code, undiscovered edge cases are high-risk, which would elevate priority to P1.

4. **Audit trail verification**: My P1 finding about missing audit trail verification after resume assumes this is critical for "auditability standard" compliance. If integration tests are meant to be coarse-grained "does it work" tests and unit tests verify audit completeness, this would be P2.
