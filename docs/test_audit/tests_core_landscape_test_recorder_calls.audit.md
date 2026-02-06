# Test Audit: tests/core/landscape/test_recorder_calls.py

**Lines:** 734
**Test count:** 24
**Audit status:** PASS

## Summary

This is a comprehensive, high-quality test file covering external call recording in the audit trail. Tests are well-organized into four logical classes: basic recording, payload persistence, and cross-run isolation. The tests verify actual database constraints (FK, unique index) and hash determinism, which are critical for audit integrity.

## Findings

### 🔵 Info

1. **Lines 125-169, 171-208: Excellent P1 audit verification tests** - `test_persisted_call_fields_match_expected_values` and `test_persisted_error_call_fields` go beyond checking non-null to verify actual hash values match expected `stable_hash()` results and that enum types are preserved. This is exactly the level of verification needed for audit trail integrity.

2. **Lines 225-254: Important constraint verification** - `test_duplicate_call_index_rejected_at_db_level` verifies the partial unique index on `(state_id, call_index)`. The docstring clearly explains why this constraint exists (defense-in-depth for audit integrity).

3. **Lines 356-407: Hash determinism test** - `test_request_hash_is_deterministic` correctly creates a second run/state to verify hash determinism across different contexts. This is critical for replay/verify modes.

4. **Lines 410-559: Payload persistence tests** - `TestCallPayloadPersistence` thoroughly tests auto-persist behavior when payload store is configured, including edge cases: explicit refs not overwritten, error calls without response, and no-store behavior.

5. **Lines 561-734: Critical cross-run isolation tests** - `TestFindCallByRequestHashRunIsolation` addresses the composite PK pattern documented in CLAUDE.md. These tests verify that `find_call_by_request_hash` correctly isolates results to the requested run when node_ids are reused across runs. The helper method `_create_run_with_call` is well-documented with clear docstrings.

6. **Lines 446-469, 471-491: Unused fixture parameter** - `test_auto_persist_response_when_payload_store_configured` and `test_auto_persist_request_when_payload_store_configured` accept a `payload_store` fixture parameter but immediately create their own `FilesystemPayloadStore` inside a `TemporaryDirectory`. The fixture is shadowed and never used. This is a minor inefficiency but does not affect test correctness.

7. **Lines 515-535, 537-558: Same pattern with shadowed fixture** - `test_explicit_ref_not_overwritten` and `test_error_call_without_response_no_ref` have the same issue with the unused `payload_store` fixture parameter.

### 🟡 Warning

1. **Lines 446, 471, 515, 537: Shadowed fixture pattern** - Four tests in `TestCallPayloadPersistence` accept a `payload_store` fixture but create their own local `payload_store` variable, shadowing the fixture. While this works, it suggests either the fixture should be used or the parameter should be removed. This is a code smell but does not impact test validity.

## Verdict

**KEEP** - This is an exemplary test file demonstrating best practices for audit trail testing. Tests verify actual database constraints, hash determinism, cross-run isolation, and enum type preservation. The coverage of edge cases (error calls, explicit refs, missing payload store) is thorough. The only issue is the shadowed fixture parameters which is a minor cleanup opportunity.
