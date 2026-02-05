# Test Audit: tests/core/landscape/test_recorder_tokens.py

**Lines:** 754
**Test count:** 20
**Audit status:** PASS

## Summary

This is the most comprehensive test file in the set, covering token lifecycle operations including creation, forking, coalescing, and expansion (deaggregation). It includes critical tests for parent lineage verification, step_in_pipeline tracking, empty branch rejection, and atomic outcome recording. The tests align well with CLAUDE.md audit integrity requirements.

## Findings

### 🔵 Info

1. **Hash correctness verification** (lines 44-73): test_create_row_hash_correctness verifies that the stored hash matches stable_hash(data), not just that it's non-null. This is a P1-level test for audit integrity - a regression in canonicalization would be caught.

2. **Parent lineage verification** (lines 134-178): test_fork_token_parent_lineage_verified confirms that token_parents entries are created correctly with proper parent_token_id and ordinal values. Critical for explain() query functionality.

3. **Comprehensive expand_token tests** (lines 334-536): TestExpandToken class thoroughly tests deaggregation audit trail including:
   - Parent relationship recording
   - Zero count rejection
   - step_in_pipeline storage
   - Single child edge case
   - expand_group_id preservation through retrieval

4. **Atomic outcome recording tests** (lines 539-753): TestAtomicTokenOperations validates that fork_token and expand_token atomically record parent outcomes, eliminating crash windows. This is critical for crash recovery correctness.

5. **Contract storage tests** (lines 589-625, 672-710): Tests verify that expected_branches_json stores branch names for forks and count for expansions, enabling downstream contract validation.

6. **Defense-in-depth validation** (lines 255-288): test_fork_token_rejects_empty_branches ensures that even if upstream validation fails, the recorder itself rejects invalid operations.

## Verdict

**KEEP** - Excellent test file with comprehensive coverage of token lifecycle operations. Tests properly verify:
- Hash correctness (not just existence)
- Parent lineage for forks and expansions
- Atomic outcome recording for crash recovery
- Contract storage for validation
- Edge cases (empty branches, single child, zero count)

No overmocking, no tests that do nothing, strong assertions throughout. This is a model test file.
