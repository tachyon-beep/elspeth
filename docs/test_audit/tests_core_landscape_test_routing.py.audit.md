# Test Audit: tests/core/landscape/test_routing.py

**Lines:** 39
**Test count:** 4 test functions
**Audit status:** ISSUES_FOUND

## Summary

This is a thin test file that verifies the re-export of `RoutingSpec` from the `elspeth.core.landscape` package. The tests are minimal and the file explicitly states that canonical tests are elsewhere (`tests/contracts/test_routing.py`). The tests validate basic construction and immutability but provide little additional coverage.

## Findings

### 🟡 Warning

1. **Near-duplicate of canonical tests (line 6)**: The file explicitly states "The canonical tests are in tests/contracts/test_routing.py." This raises the question of whether this file should exist at all - if it's just testing a re-export path, a single import test would suffice.

2. **Tests do not exercise actual re-export mechanism (lines 19-22)**: `test_can_import_from_landscape` just asserts `RoutingSpec is not None`. This doesn't verify that the re-export is correctly configured - it would pass even if `RoutingSpec` was defined locally or imported differently.

3. **Limited value**: The tests for `MOVE`/`COPY` modes (lines 24-33) and immutability (lines 35-39) duplicate what should be covered in the canonical test file.

### 🔵 Info

1. **File is well-documented**: The docstring clearly explains the purpose (re-export path testing) and directs readers to canonical tests.

## Verdict

**DELETE or MERGE** - This file adds minimal value. If the re-export path needs testing, a single test verifying the import works would suffice. The behavior tests should live in the canonical location. Consider deleting this file and adding a single re-export verification test to the canonical file, or consolidating into a general "public API exports" test file.
