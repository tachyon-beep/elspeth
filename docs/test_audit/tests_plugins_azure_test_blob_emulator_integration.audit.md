# Test Audit: tests/plugins/azure/test_blob_emulator_integration.py

**Lines:** 150
**Test count:** 3
**Audit status:** PASS

## Summary

This is a focused integration test file that verifies round-trip data integrity between `AzureBlobSink` and `AzureBlobSource` using the Azurite emulator. The tests cover three format types (JSONL, JSON array, CSV) and properly use the `@pytest.mark.integration` marker and `pytest.importorskip` for conditional execution. The tests are valuable for verifying real Azure SDK behavior without mocks.

## Findings

### 🔵 Info

1. **Lines 15-58, 62-104, 108-150 - Good integration test pattern**: Each test follows a consistent write-then-read pattern, verifying that data written by the sink can be read back identically by the source. This is the correct approach for integration tests.

2. **Lines 17, 64, 110 - Proper SDK skip handling**: Uses `pytest.importorskip("azure.storage.blob")` to gracefully skip when the Azure SDK is not installed.

3. **Lines 116-120 - CSV type behavior**: The CSV roundtrip test uses string values for all fields, which correctly reflects CSV's string-based nature. This is intentional and documented by the test data.

4. **Fixture dependency**: The tests depend on an `azurite_blob_container` fixture (not shown in this file) which must be defined in conftest.py. This is appropriate for integration tests.

## Verdict

**KEEP** - Valuable integration tests that verify real Azure SDK behavior through the Azurite emulator. The tests are well-structured, properly marked for conditional execution, and cover all three supported formats. No issues found.
