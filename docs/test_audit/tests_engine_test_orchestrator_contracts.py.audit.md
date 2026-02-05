# Test Audit: tests/engine/test_orchestrator_contracts.py

**Lines:** 732
**Test count:** 9 test methods (6 in TestOrchestratorContractRecording, 2 in TestOrchestratorSecretResolutions, 1 implicit from schema evolution)
**Audit status:** ISSUES_FOUND

## Summary

This test file provides excellent coverage of schema contract recording in the orchestrator, including source contracts, transform schema evolution, quarantine-first scenarios, and secret resolution recording. The tests verify database state directly via SQLAlchemy queries, ensuring audit trail integrity. However, there is moderate code duplication with similar plugin classes repeated across tests.

## Findings

### Warning

1. **Repeated `CollectSink` class definitions** (lines 82-93, 171-182, 239-250, 303-314, 403-414, 527-538, 609-620, 689-700): The `CollectSink` class is defined 8 times with nearly identical implementations. This should be extracted to module level.

2. **Multiple similar source class definitions** (lines 64-80, 157-169, 226-237, 288-301, 376-401, 499-511, 602-607, 682-687): Various source classes with similar patterns are defined inline. Consider a parameterized factory or module-level base class.

### Info

3. **Strong audit trail verification** (lines 114-137, 199-220, etc.): Tests directly query the Landscape database tables (`runs_table`, `nodes_table`, `secret_resolutions_table`) to verify contract data was correctly recorded. This is excellent for verifying audit integrity.

4. **Good edge case coverage** (lines 350-462): `test_contract_recorded_after_first_valid_row_not_first_iteration` is an excellent regression test that verifies contracts are recorded after the first VALID row, not the first iteration (fixing a documented bug).

5. **Schema evolution testing** (lines 464-586): `test_transform_schema_evolution_updates_contract` properly verifies that transforms which add fields have their evolved output contract recorded with the new fields marked as inferred.

6. **Production graph usage** (lines 106, 192, 260, 324, 425, 549, 630, 710): All tests use `build_production_graph()` helper, maintaining production code path integrity.

7. **Secret resolution testing** (lines 589-732): Comprehensive tests for secret resolution recording including fingerprint verification and the case where no secrets are provided.

8. **Good documentation** (lines 350-359, 464-472): Tests include detailed docstrings explaining the edge cases being tested and referencing bug fixes.

## Verdict

**KEEP** with minor cleanup - The tests provide strong coverage of critical audit trail functionality. The code duplication is moderate and doesn't significantly impair readability. Consider extracting `CollectSink` to module level when convenient, but the current structure is acceptable.
