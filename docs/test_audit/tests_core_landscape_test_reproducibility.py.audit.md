# Test Audit: tests/core/landscape/test_reproducibility.py

**Lines:** 257
**Test count:** 9 test functions
**Audit status:** PASS

## Summary

This test file verifies the reproducibility grade management system, including grade computation based on node determinism and grade degradation after payload purges. The tests use real in-memory databases with proper setup/teardown, validating both happy paths and Data Manifesto crash-on-corruption behavior.

## Findings

### 🔵 Info

1. **Inline imports (lines 14-19, 39-45, etc.)**: Each test method imports its dependencies inline rather than at module level. This is unusual but creates self-contained tests. The pattern is consistent throughout the file and does not affect test correctness.

2. **Real database usage**: Tests use `LandscapeDB.in_memory()` rather than mocks, which provides integration-level confidence that the reproducibility logic works with actual database operations. This is appropriate for testing database-dependent behavior.

3. **Direct SQL manipulation for corruption tests (lines 104-108, 131-135, 185-189)**: Tests use raw SQL (`text("UPDATE runs SET reproducibility_grade = ...")`) to simulate database corruption. This is the correct approach for testing crash-on-corruption behavior - you cannot corrupt data through the normal API.

4. **Good coverage of grade transitions**: Tests verify REPLAY_REPRODUCIBLE degrades to ATTRIBUTABLE_ONLY, while FULL_REPRODUCIBLE and ATTRIBUTABLE_ONLY remain unchanged after purge.

5. **Tests validate Determinism enum handling**: TestComputeGradeValidation verifies that invalid determinism values cause crashes and that IO_READ/IO_WRITE nodes correctly result in REPLAY_REPRODUCIBLE grade.

## Verdict

**KEEP** - Well-structured tests that validate important reproducibility grade invariants and Data Manifesto compliance. The inline imports are unconventional but the tests are correct and valuable.
