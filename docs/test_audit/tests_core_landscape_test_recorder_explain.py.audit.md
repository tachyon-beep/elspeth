# Test Audit: tests/core/landscape/test_recorder_explain.py

**Lines:** 348
**Test count:** 9
**Audit status:** PASS

## Summary

This test file provides comprehensive coverage of the `explain_row()` functionality in LandscapeRecorder, testing graceful degradation when payloads are unavailable (purged, corrupted, or never stored). The tests are well-structured, exercise real code paths using in-memory databases without excessive mocking, and cover important edge cases including run ID mismatch validation.

## Findings

### Info

1. **Unused fixture parameter (lines 17, 66):** The `payload_store` fixture is passed to some tests but immediately shadowed by creating a new `FilesystemPayloadStore` inside the test. This appears intentional to control the store's location via `tmp_path`, but the fixture parameter could be removed for clarity.

2. **Repetitive setup pattern:** Each test creates its own `LandscapeDB.in_memory()`, `LandscapeRecorder`, run, and source node. While this provides test isolation, a shared fixture could reduce boilerplate by ~20 lines per test.

3. **Import location (lines 19-23, etc.):** Imports are performed inside test methods rather than at module level. This is a stylistic choice that provides clear isolation but adds minor overhead.

## Verdict

**KEEP** - This is a well-designed test file with meaningful assertions that verify audit trail integrity behavior. The tests exercise real LandscapeRecorder and PayloadStore code paths without mocking internals. The graceful degradation tests (corrupted payload, missing payload, run ID mismatch) are particularly valuable for audit integrity. No structural changes needed.
