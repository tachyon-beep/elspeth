# BUG #6: NodeStateRepository Missing Forbidden Field Validation

**Issue ID:** elspeth-rapid-tpbw
**Priority:** P1
**Status:** CLOSED
**Date Opened:** 2026-02-05
**Date Closed:** 2026-02-05
**Component:** core-landscape (repositories.py)

## Summary

The `NodeStateRepository.load()` method had **incomplete validation** for state invariants:
- PENDING/COMPLETED/FAILED states validated required NOT NULL fields
- But NO states validated forbidden NULL fields

Specifically:
1. **OPEN states** didn't validate that output_hash, completed_at, and duration_ms should be NULL
2. **PENDING states** didn't validate that output_hash should be NULL

This allowed corrupted audit data to be silently accepted instead of crashing immediately, violating Tier-1 audit integrity.

## Impact

- **Severity:** High - Tier-1 audit trail integrity
- **Effect:** Corrupted audit data with contradictory field values accepted silently
- **Risk:** OPEN states with completion timestamps, PENDING states with outputs

## Root Cause

The `load()` method (lines 300-391) had asymmetric validation:

**What was validated (lines 316-386):**
- PENDING: duration_ms NOT NULL, completed_at NOT NULL ✅
- COMPLETED: output_hash NOT NULL, duration_ms NOT NULL, completed_at NOT NULL ✅
- FAILED: duration_ms NOT NULL, completed_at NOT NULL ✅

**What was NOT validated:**
- OPEN: output_hash, completed_at, duration_ms should be NULL ❌
- PENDING: output_hash should be NULL ❌

**The contradiction:**

An OPEN state with `completed_at` is logically impossible - "operation in progress" contradicts "operation completed at timestamp X". Similarly, a PENDING state with `output_hash` contradicts "waiting for batch result" (no output available yet).

**Why this matters:**

These contradictions indicate one of:
1. **Database corruption:** Disk errors, partial writes
2. **Concurrent modification bugs:** Race conditions in state updates
3. **Manual tampering:** Direct database edits

Without validation, corrupted states would pass through undetected, polluting the audit trail with nonsensical data.

## Files Affected

- `src/elspeth/core/landscape/repositories.py` (lines 302-348)

## Fix

Added validation for forbidden NULL fields:

**OPEN states (lines 303-311):**
```python
if status == NodeStateStatus.OPEN:
    # BUG #6: OPEN states must have NULL completion fields
    # Operations haven't finished yet, so output_hash, completed_at, and duration_ms
    # must all be NULL. Non-NULL values indicate corrupted audit data.
    if row.output_hash is not None:
        raise ValueError(f"OPEN state {row.state_id} has non-NULL output_hash - audit integrity violation")
    if row.completed_at is not None:
        raise ValueError(f"OPEN state {row.state_id} has non-NULL completed_at - audit integrity violation")
    if row.duration_ms is not None:
        raise ValueError(f"OPEN state {row.state_id} has non-NULL duration_ms - audit integrity violation")

    return NodeStateOpen(...)
```

**PENDING states (lines 327-333):**
```python
elif status == NodeStateStatus.PENDING:
    # Existing validation for required NOT NULL fields...
    if row.duration_ms is None:
        raise ValueError(...)
    if row.completed_at is None:
        raise ValueError(...)

    # BUG #6: PENDING states must have NULL output_hash
    # Batch processing is in progress, no output available yet.
    # Non-NULL output_hash contradicts PENDING status.
    if row.output_hash is not None:
        raise ValueError(f"PENDING state {row.state_id} has non-NULL output_hash - audit integrity violation")

    return NodeStatePending(...)
```

**Validation pattern:**
- Check forbidden fields BEFORE constructing the state object
- Use descriptive error messages that include state_id and field name
- Raise ValueError (same as existing validation)

## Test Coverage

Added four comprehensive tests in `tests/core/landscape/test_node_state_repository.py`:

**OPEN state validation (3 tests):**
1. `test_load_crashes_on_open_with_output_hash`
2. `test_load_crashes_on_open_with_completed_at`
3. `test_load_crashes_on_open_with_duration`

**PENDING state validation (1 test):**
4. `test_load_crashes_on_pending_with_output_hash`

**Test strategy:**
- Create database row with invalid field combinations
- Verify `ValueError` is raised with appropriate message
- Confirm error message includes state_id and field name

**Test results:**
- RED: All 4 tests failed initially (validation missing)
- GREEN: All 4 tests passed after fix (validation added)
- All 19 node state repository tests pass

## Verification

```bash
# Run specific tests
.venv/bin/python -m pytest tests/core/landscape/test_node_state_repository.py::TestNodeStateRepositoryOpen::test_load_crashes_on_open_with_output_hash -xvs
.venv/bin/python -m pytest tests/core/landscape/test_node_state_repository.py::TestNodeStateRepositoryPending::test_load_crashes_on_pending_with_output_hash -xvs

# Run all node state repository tests
.venv/bin/python -m pytest tests/core/landscape/test_node_state_repository.py -x
```

**Results:** All 19 tests pass

## State Invariants Reference

For future reference, here are the complete field requirements per status:

| Status | output_hash | completed_at | duration_ms | error_json |
|--------|-------------|--------------|-------------|------------|
| **OPEN** | NULL | NULL | NULL | NULL |
| **PENDING** | NULL | NOT NULL | NOT NULL | NULL |
| **COMPLETED** | NOT NULL | NOT NULL | NOT NULL | NULL |
| **FAILED** | Optional | NOT NULL | NOT NULL | Optional |

**Rationale:**

- **OPEN:** Operation in progress, nothing finished yet
- **PENDING:** Operation finished, waiting for batch result (no output yet)
- **COMPLETED:** Operation succeeded with output
- **FAILED:** Operation failed (may have partial output, may have error details)

## Pattern Observed

This is the fifth instance of incomplete validation in Tier-1 code:
1. Bug #3 (database_ops) - missing rowcount validation
2. Bug #5 (payload_store) - missing file integrity check
3. Bug #8 (schema validation) - missing Phase 5 columns
4. Bug #10 (operations) - missing BaseException handling
5. **Bug #6 (this bug)** - missing forbidden field validation

**Lesson:** When implementing state machines with invariants, validate BOTH:
1. **Required fields:** What must be present (NOT NULL)
2. **Forbidden fields:** What must be absent (NULL)

Many bugs only check one direction. Complete validation requires checking both.

## Real-World Scenario

**Before fix:**
1. Operation starts (OPEN state created: output_hash=NULL, completed_at=NULL)
2. Disk corruption or race condition sets completed_at to non-NULL
3. Repository loads corrupted row, silently accepts it
4. Audit trail now has "OPEN" state with completion timestamp (nonsense!)
5. Lineage queries return contradictory data

**After fix:**
1. Operation starts (OPEN state created: output_hash=NULL, completed_at=NULL)
2. Disk corruption or race condition sets completed_at to non-NULL
3. Repository loads corrupted row, detects completed_at is non-NULL
4. ValueError raised: "OPEN state state_123 has non-NULL completed_at - audit integrity violation"
5. Operator investigates database, fixes corruption
6. Audit trail remains pristine

## TDD Cycle Duration

- RED (write failing tests): 6 minutes
- GREEN (implement fix): 4 minutes
- Verification (run all tests): 2 minutes
- **Total:** ~12 minutes

## Related Bugs

- Part of Group 1: Tier-1 Audit Trail Integrity (10 bugs total)
- Follows same pattern as Bugs #1-10 (validation gaps in Tier-1 code)
