# Test Audit: tests/property/engine/test_processor_properties.py

## Overview
Property-based tests for RowProcessor work queue semantics - critical for audit trail integrity.

**File:** `tests/property/engine/test_processor_properties.py`
**Lines:** 900
**Test Classes:** 5

## Findings

### PASS - Comprehensive Work Queue Testing

This is a large, critical test file that verifies work conservation and order correctness.

**Strengths:**
1. **Work conservation tested** - No rows lost, all reach terminal states
2. **Order correctness verified** - Transforms execute in declared order
3. **Iteration guard tested** - MAX_WORK_QUEUE_ITERATIONS prevents runaway
4. **Token identity verified** - All IDs unique, fork creates distinct children
5. **Uses real database** - `LandscapeDB.in_memory()` for realistic testing
6. **Uses production graph builder** - `build_production_graph(config)` avoids dual code paths

### Issues

**1. Low Priority - Complex helpers for audit verification (Lines 62-133)**
```python
def count_tokens_missing_terminal(db: LandscapeDB, run_id: str) -> int:
    """Count tokens that lack a terminal outcome."""
    with db.connection() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM tokens t
            JOIN rows r ON r.row_id = t.row_id
            LEFT JOIN token_outcomes o ON o.token_id = t.token_id AND o.is_terminal = 1
            WHERE r.run_id = :run_id AND o.token_id IS NULL
        """), {"run_id": run_id}).scalar()
```
- Direct SQL queries for verification
- This is appropriate for property tests verifying database state

**2. Good Pattern - Production path verification (Lines 279-339)**
```python
def test_fork_preserves_row_count_across_branches(self, num_rows: int) -> None:
    ...
    graph = ExecutionGraph.from_plugin_instances(...)  # Production factory
    orchestrator = Orchestrator(db)
    run = orchestrator.run(config, graph=graph, settings=settings, ...)
```
- Uses production `from_plugin_instances()` factory
- Follows CLAUDE.md guidance on avoiding dual code paths

**3. Good Pattern - Iteration guard canary test (Lines 483-489)**
```python
def test_max_iterations_constant_value(self) -> None:
    assert MAX_WORK_QUEUE_ITERATIONS == 10_000, (
        f"MAX_WORK_QUEUE_ITERATIONS changed from 10_000 to {MAX_WORK_QUEUE_ITERATIONS}. "
        "Update this test if this is intentional."
    )
```
- Documents expected value and catches accidental changes

**4. Good Pattern - Fork-coalesce balance test (Lines 819-900)**
```python
def test_fork_coalesce_balance(self, num_rows: int) -> None:
    """Property: Fork-coalesce maintains token conservation."""
    ...
    forked_count = count_outcome_by_type(db, run.run_id, RowOutcome.FORKED)
    assert forked_count == num_rows

    coalesced_count = count_outcome_by_type(db, run.run_id, RowOutcome.COALESCED)
    assert coalesced_count == num_rows * 2
```
- Verifies complete fork-coalesce flow

### Coverage Assessment

| Work Conservation | Tested | Notes |
|-------------------|--------|-------|
| All rows reach terminal | YES | |
| Multi-transform preserves count | YES | |
| Error rows reach QUARANTINED | YES | |
| Fork creates children | YES | |
| Fork children reach terminal | YES | |

| Order Correctness | Tested | Notes |
|-------------------|--------|-------|
| Transforms in declared order | YES | |
| Rows in source order | YES | |
| No-transform preserves order | YES | |

| Iteration Guard | Tested | Notes |
|-----------------|--------|-------|
| Constant is reasonable | YES | 1000-100000 |
| Constant is 10000 | YES | Canary |
| Normal pipeline under guard | YES | |
| Fork stays under guard | YES | |

| Token Identity | Tested | Notes |
|----------------|--------|-------|
| All IDs unique | YES | |
| Fork creates distinct children | YES | |
| row_id preserved through transforms | YES | |

| Edge Cases | Tested | Notes |
|------------|--------|-------|
| Empty source | YES | |
| Single row | YES | |
| All rows error | YES | |
| Fork-coalesce balance | YES | |

## Verdict: PASS

Excellent integration-level property tests that use real database and production code paths. The work conservation tests are critical for ensuring no rows are silently dropped.
