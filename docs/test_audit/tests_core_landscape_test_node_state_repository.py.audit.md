# Test Audit: tests/core/landscape/test_node_state_repository.py

**Lines:** 510
**Test count:** 21
**Audit status:** PASS

## Summary

This file tests the `NodeStateRepository.load()` method which deserializes database rows into discriminated union NodeState types. The tests thoroughly verify both happy paths (valid state loading) and Tier 1 violation detection (invalid field combinations that indicate audit data corruption). The mock `NodeStateRow` dataclass appropriately simulates SQLAlchemy row objects.

## Findings

### Info

- **Mock pattern**: The `NodeStateRow` dataclass (lines 28-49) is a lightweight mock for SQLAlchemy row objects. This is appropriate - it avoids database dependencies while accurately representing the data structure. The `session=None` pattern on line 70 (and throughout) shows the repository is designed to accept a session for real queries but doesn't need one for the `load()` method being tested.

- **Tier 1 enforcement**: Tests explicitly verify that invalid field combinations crash immediately per Data Manifesto:
  - OPEN with output_hash (line 104)
  - OPEN with completed_at (line 128)
  - OPEN with duration_ms (line 151)
  - PENDING without duration_ms (line 207)
  - PENDING without completed_at (line 227)
  - PENDING with output_hash (line 247)
  - COMPLETED without output_hash (line 309)
  - COMPLETED without duration_ms (line 330)
  - COMPLETED without completed_at (line 351)
  - FAILED without duration_ms (line 429)
  - FAILED without completed_at (line 450)

- **BUG #6 references**: Several tests reference "BUG #6" in docstrings (lines 104, 128, 151, 247), indicating these tests were written in response to a specific bug finding. This is good traceability.

- **Edge case coverage**:
  - OPEN state allows NULL context_before_json (line 84)
  - FAILED state allows output_hash for partial results (line 405)
  - Invalid status strings crash immediately (lines 475, 493)

## Verdict

**KEEP** - This is excellent repository-layer testing that directly enforces Tier 1 data integrity. The tests verify:
1. Correct discriminated union type selection based on status
2. Field validation per status (which fields must be NULL vs non-NULL)
3. Immediate crash behavior on invalid audit data
4. Edge cases like partial output on failure

The mock pattern is appropriate for unit testing the load logic without database coupling.
