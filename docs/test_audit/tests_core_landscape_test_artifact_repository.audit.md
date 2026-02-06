# Test Audit: tests/core/landscape/test_artifact_repository.py

**Lines:** 99
**Test count:** 4
**Audit status:** ISSUES_FOUND

## Summary

This file tests the `load()` methods of `ArtifactRepository` and `BatchMemberRepository`, verifying field mapping from database rows to domain objects. The tests are well-structured but rely entirely on MagicMock objects, which means they only verify the field-to-field mapping logic without testing real database integration or the repository's query logic.

## Findings

### 🟡 Warning

1. **Overmocking (lines 18-31, 47-61, 73-77, 88-92)**: All tests use `MagicMock` objects for both the database connection AND the row data. This means:
   - The `ArtifactRepository(MagicMock())` constructor receives a mock database, so no actual database interaction is tested
   - The row data is mocked, so there's no verification that the repository can handle actual SQLAlchemy row objects
   - If the SQLAlchemy row API changes (e.g., attribute access vs dict-like access), these tests would still pass

2. **No query/find tests**: The repositories presumably have methods beyond `load()` (e.g., `find_by_id`, `find_by_run_id`), but only `load()` is tested. This represents a coverage gap.

3. **No persistence tests**: There are no tests for `save()` or `insert()` methods, which repositories typically have.

### 🔵 Info

1. **Test structure is good**: Tests are clearly named, well-organized into classes per repository, and test both happy path and edge cases (NULL optionals).

2. **Field mapping coverage is complete**: All fields on `Artifact` and `BatchMember` are verified in the tests.

## Verdict

**KEEP** - The tests serve a valid purpose (verifying field mapping in the `load()` method), but additional integration tests using real database fixtures would provide more confidence. The overmocking is a concern but not critical given the narrow scope of what's being tested.
