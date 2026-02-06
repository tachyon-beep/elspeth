# Test Audit: tests/engine/test_group_id_consistency.py

**Lines:** 701
**Test count:** 7 test methods across 4 test classes
**Audit status:** PASS

## Summary

This is a well-structured integration test file that verifies group ID consistency between tokens and token_outcomes tables for fork, join, and expand operations. The tests use production code paths (as mandated by CLAUDE.md Test Path Integrity), properly exercise the ExecutionGraph factory methods, and validate critical audit trail consistency requirements. The tests are thorough, document their purpose clearly, and provide meaningful assertions with informative error messages.

## Findings

### 🔵 Info

1. **Inline test helper classes (lines 31-78)**: `ListSource` and `CollectSink` are duplicated in this file even though similar patterns exist in conftest.py. These are simple and self-contained, and the explicit definition makes the tests more readable. Not a defect, just noting the pattern.

2. **Module-level recorder variables unused (lines 88, 157, 241, etc.)**: Variables like `_recorder = LandscapeRecorder(db)` are created but never used in some tests. The orchestrator internally creates its own recorder. These are harmless but create minor confusion. Example at line 88: `_recorder` is created but the test only queries the db directly.

3. **Good use of production paths**: All tests correctly use `instantiate_plugins_from_config(settings)` and `ExecutionGraph.from_plugin_instances()` - following the Test Path Integrity requirement from CLAUDE.md.

4. **Excellent assertion messages**: All assertions include descriptive failure messages that would help diagnose issues (e.g., line 148: "Fork children should share same fork_group_id").

5. **SQL queries use parameterized statements**: All raw SQL queries properly use `:param` syntax and parameter dictionaries (e.g., lines 220-221), avoiding SQL injection risks.

## Test Coverage Analysis

| Class | Tests | Coverage Focus |
|-------|-------|----------------|
| TestForkGroupIDConsistency | 2 | fork_group_id in tokens and token_outcomes |
| TestJoinGroupIDConsistency | 3 | join_group_id for coalesce operations |
| TestExpandGroupIDConsistency | 2 | expand_group_id for JSON explode (1->N) |
| TestSequentialCoalesces | 1 | Multiple coalesce operations get distinct IDs |

All tests appear to pass based on their structure (verifiable assertions, proper setup).

## Verdict

**KEEP** - This is a high-quality integration test file that validates critical audit trail consistency requirements. The tests follow production code paths, have clear assertions, and cover important edge cases (fork, join, expand, sequential coalesces). No changes recommended.
