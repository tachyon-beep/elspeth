# Test Audit: tests/contracts/source_contracts/test_csv_source_contract.py

**Lines:** 264
**Test count:** 10 tests (across 5 test classes)
**Audit status:** PASS

## Summary

This is a comprehensive contract test file for CSVSource that verifies both the protocol compliance (via inheritance from SourceContractPropertyTestBase) and CSVSource-specific behaviors including delimiter handling, quarantine behavior, discard mode, and file error handling. The tests exercise real code paths with proper Landscape recorder integration for audit trail verification.

## Findings

### 🔵 Info (minor suggestions or observations)

- **Lines 143-186:** `test_invalid_rows_are_quarantined` sets up a full Landscape recorder context to verify audit trail recording. This is the correct approach for contract tests - it verifies the complete integration rather than just surface behavior. The test correctly verifies both the yielded SourceRow objects AND the recorded validation errors in the database.

- **Lines 202-246:** Similar pattern in `test_discarded_rows_not_yielded_but_recorded` - verifies that even when rows are discarded (not yielded), they are still recorded in the audit trail. This is a critical contract requirement.

- **Lines 149-158:** The `register_node` call uses `SchemaConfig.from_dict({"mode": "observed"})` but the actual source uses `"mode": "fixed"` with strict validation. This mismatch is technically inconsistent but doesn't affect the test outcome because the node registration is for audit trail bookkeeping, not validation. However, it could be confusing for readers.

## Verdict

**KEEP** - This is a thorough contract test file that properly verifies CSVSource behavior including the critical quarantine and discard audit trail requirements. The tests interact with real components (Landscape recorder) rather than mocking, ensuring the contracts are actually enforced at integration points.
