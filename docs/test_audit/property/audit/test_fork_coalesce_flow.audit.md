# Audit: tests/property/audit/test_fork_coalesce_flow.py

## Overview
Property-based tests for the complete fork-coalesce-continue flow, verifying token accounting invariants through Hypothesis-driven input generation.

**Lines:** 590
**Test Classes:** 2
**Test Methods:** 5

## Audit Results

### 1. Defects
**PASS** - No defects found.

The tests correctly verify:
- Token accounting (FORKED + COALESCED + COMPLETED counts)
- Parent link recording for coalesced tokens
- Data preservation through fork-coalesce

### 2. Overmocking
**PASS** - No overmocking issues.

- Uses `LandscapeDB.in_memory()` for real database testing
- Uses `MockPayloadStore()` appropriately (payload storage is not the test subject)
- Exercises full production code path via `Orchestrator.run()`
- Uses `ExecutionGraph.from_plugin_instances()` per CLAUDE.md guidance

### 3. Missing Coverage
**MINOR** - Some edge cases could be added:

1. **Three-way fork**: Tests only cover 2-branch forks. A 3+ branch test would increase confidence.
2. **Nested fork-coalesce**: Source -> fork -> coalesce -> fork -> coalesce pattern not tested.
3. **Mixed routing**: Some rows fork, others continue - not tested.

### 4. Tests That Do Nothing
**PASS** - All tests have meaningful assertions.

Each test:
- Asserts on token counts (forked_count, coalesced_count, completed_count)
- Verifies no tokens are lost (count_tokens_missing_terminal)
- Verifies sink receives correct number of results

### 5. Inefficiency
**MINOR** - Repeated setup patterns.

Lines 244-295, 339-388, 407-456 duplicate similar setup code for:
- Creating gate, coalesce, config, graph, settings, orchestrator

**Recommendation:** Extract a helper function:
```python
def run_fork_coalesce_pipeline(rows: list[dict], n_branches: int = 2) -> tuple[Run, dict]:
    """Create and run a fork-coalesce pipeline, return stats."""
```

### 6. Structural Issues
**PASS** - Well organized.

- Clear class separation (TestForkCoalesceFlow, TestForkCoalesceEdgeCases)
- Helper functions at top for SQL queries
- Appropriate use of `deadline=None` for DB-heavy tests

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | Uses production paths |
| Missing Coverage | MINOR | 3-way fork, nested patterns |
| Tests That Do Nothing | PASS | All assertions meaningful |
| Inefficiency | MINOR | Duplicated setup code |
| Structural Issues | PASS | Well organized |

**Overall:** HIGH QUALITY - Tests thoroughly verify fork-coalesce invariants using production code paths. Minor efficiency improvements possible.
