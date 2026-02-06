# Test Audit: tests/core/landscape/test_exporter.py

**Lines:** 1265
**Test count:** 33
**Audit status:** PASS

## Summary

This is a comprehensive, well-structured test file for `LandscapeExporter`. It thoroughly tests export functionality including record extraction for all entity types (runs, rows, nodes, edges, tokens, node_states, artifacts, batches, batch_members, routing_events, token_parents, calls, operations), HMAC signing/verification, hash chain integrity, determinism guarantees, and Tier 1 corruption detection. The tests follow good patterns: they use real database operations (no overmocking), verify actual behavior, and include security-critical edge cases.

## Findings

### 🔵 Info

1. **Lines 16-43: Shared fixture `populated_db`** - Well-designed fixture that creates a minimal but complete run with a source node and one row. Used by 9 tests. Good fixture reuse pattern.

2. **Lines 201-599: `TestLandscapeExporterComplexRun`** - This class contains 10 tests, each setting up its own database and run. While this creates some setup duplication, each test needs different data structures (edges, tokens, artifacts, batches, etc.), so independent setup is appropriate. The tests are not inefficient; they are isolated by necessity.

3. **Lines 601-836: `TestLandscapeExporterSigning`** - Excellent coverage of HMAC signing including:
   - Signatures present when enabled (604-614)
   - Manifest with final hash (616-629)
   - No signatures when disabled (631-643)
   - Error when sign=True without key (645-651)
   - Record count verification (653-663)
   - Signature determinism (665-676)
   - Key-dependent signatures (678-691)
   - Algorithm metadata in manifest (693-702)
   - Multi-record determinism stress test (704-801)
   - Record order stability (803-835)

4. **Lines 838-912: `TestLandscapeExporterCallRecords`** - P1 priority test for external call export. Good coverage including request/response hashes, latency, and enum serialization.

5. **Lines 914-962: `TestLandscapeExporterManifestIntegrity`** - P1 priority test that actually recomputes the hash chain to verify correctness. This goes beyond just checking field existence - it validates the cryptographic integrity mechanism works.

6. **Lines 965-1004: `TestLandscapeExporterTier1Corruption`** - P1 priority test verifying the exporter crashes (not silently coerces) when encountering invalid enum values in the database. This aligns with the Three-Tier Trust Model in CLAUDE.md. Uses raw SQL to corrupt data, which is the correct way to test this edge case.

7. **Lines 1007-1265: `TestLandscapeExporterCompleteness`** - BUG #9 regression tests. These tests verify that exports include all required audit fields (context_before_json, context_after_json, error_json, success_reason_json, payload refs, timestamps). The comments indicate these tests were written to catch previously missing fields.

8. **Test naming** - All tests follow clear naming conventions that describe the expected behavior. Docstrings explain the audit/security rationale for each test, which is valuable for a compliance-critical component.

9. **No mocking** - Tests use real `LandscapeDB.in_memory()` and `LandscapeRecorder` instances. This is correct - the exporter's job is to extract data from a real database, so mocking the database would make the tests meaningless.

10. **Lines 704-801: Stress test for determinism** - Creates multiple records of each type and exports 5 times to verify the final hash is identical. This is important for legal-grade audit trail exports where non-determinism would undermine integrity verification.

## Verdict

**KEEP** - This is an exemplary test file for a security-critical component. It achieves comprehensive coverage without overmocking, includes both positive and negative tests, tests cryptographic integrity mechanisms, and documents the audit rationale in docstrings. The tests are well-organized into logical classes and follow good patterns. No significant issues found.
