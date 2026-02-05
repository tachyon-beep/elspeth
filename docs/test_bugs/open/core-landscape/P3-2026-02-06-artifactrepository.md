# Test Bug Report: Fix weak assertions in artifact_repository

## Summary

- This file tests the `load()` methods of `ArtifactRepository` and `BatchMemberRepository`, verifying field mapping from database rows to domain objects. The tests are well-structured but rely entirely on MagicMock objects, which means they only verify the field-to-field mapping logic without testing real database integration or the repository's query logic.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_core_landscape_test_artifact_repository.audit.md

## Test File

- **File:** `tests/core/landscape/test_artifact_repository`
- **Lines:** 99
- **Test count:** 4

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The tests serve a valid purpose (verifying field mapping in the `load()` method), but additional integration tests using real database fixtures would provide more confidence. The overmocking is a concern but not critical given the narrow scope of what's being tested.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/core/landscape/test_artifact_repository -v`

## Notes

- Source audit: `docs/test_audit/tests_core_landscape_test_artifact_repository.audit.md`
