# Audit: tests/property/audit/test_terminal_states.py

## Overview
Property-based tests for THE foundational audit property: every token reaches exactly one terminal state.

**Lines:** 378
**Test Classes:** 3
**Test Methods:** 9

## Audit Results

### 1. Defects
**PASS** - No defects found.

Tests correctly verify:
- All tokens reach terminal state (count_tokens_missing_terminal)
- No duplicate terminal outcomes
- Error rows still reach terminal state (QUARANTINED)
- Valid RowOutcome enum values

### 2. Overmocking
**PASS** - Excellent use of production code paths.

- Uses `Orchestrator.run()` for full pipeline execution
- Uses `build_production_graph()` from test helpers (correct per CLAUDE.md)
- Real LandscapeDB with actual SQL queries

### 3. Missing Coverage
**MINOR** - Some edge cases:

1. **Aggregation terminal states**: No tests for CONSUMED_IN_BATCH outcome
2. **EXPANDED outcome**: Deaggregation not tested
3. **BUFFERED -> terminal transition**: Non-terminal to terminal not tested
4. **Multiple transforms with errors**: Only tests single transform error handling

### 4. Tests That Do Nothing
**PASS** - All tests have meaningful assertions.

The core invariant check is strong:
```python
missing = count_tokens_missing_terminal(db, run.run_id)
assert missing == 0, (
    f"AUDIT INTEGRITY VIOLATION: {missing} tokens missing terminal outcome. "
    ...
)
```

### 5. Inefficiency
**PASS** - Reasonable test efficiency.

- Uses `deadline=None` appropriately for DB tests
- `max_examples=100` for core invariant tests is thorough
- Edge case tests use fewer examples (20-50) appropriately

### 6. Structural Issues
**PASS** - Well organized.

- Clear class separation by test category
- `TestRowOutcomeEnumProperties` tests enum itself, not just usage
- Good use of helper functions for SQL queries

## Enum Coverage Analysis

The `TestRowOutcomeEnumProperties` class explicitly verifies:
- All outcomes have `is_terminal` defined
- BUFFERED is the only non-terminal
- Exactly 8 terminal outcomes exist

This is a good defensive test against enum changes breaking assumptions.

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | Uses production paths |
| Missing Coverage | MINOR | Aggregation outcomes not tested |
| Tests That Do Nothing | PASS | Strong invariant assertions |
| Inefficiency | PASS | Appropriate example counts |
| Structural Issues | PASS | Well organized |

**Overall:** EXCELLENT - Core audit property thoroughly tested. This is a critical test file and it's well implemented.
