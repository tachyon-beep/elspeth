# Test Audit: tests/plugins/azure/test_blob_emulator_integration.py

**Auditor:** Claude Code Audit
**Date:** 2026-02-05
**Test File:** `/home/john/elspeth-rapid/tests/plugins/azure/test_blob_emulator_integration.py`
**Lines:** 150

## Summary

This file contains integration tests that use Azurite (Azure Storage emulator) to verify roundtrip write/read operations between `AzureBlobSink` and `AzureBlobSource`. These are high-value tests that exercise real Azure SDK code paths.

## Findings

### 1. GOOD: Real Integration Tests with Azurite

**Location:** All tests

These tests use a real Azurite instance via the `azurite_blob_container` fixture, providing true end-to-end validation:
- No mocking of Azure SDK
- Real blob upload/download operations
- Actual serialization/deserialization round-trips

### 2. ISSUE: Missing Fixture Definition

**Severity:** Medium
**Category:** Test Structure

**Location:** Line 15 - `azurite_blob_container` fixture

The `azurite_blob_container` fixture is not defined in this file. It must be defined in a `conftest.py` file (likely in `tests/plugins/azure/conftest.py` or `tests/conftest.py`).

**Risk:** If the fixture is not properly defined or Azurite is not available, these tests will fail or be skipped unexpectedly.

**Recommendation:** Verify the fixture exists and add a docstring or comment noting where it comes from.

### 3. ISSUE: CSV Roundtrip Uses String Values

**Severity:** Low
**Category:** Potential Defect

**Location:** Lines 108-150 (`test_blob_sink_source_roundtrip_csv`)

```python
rows = [
    {"id": "1", "value": "alpha"},  # Note: strings, not integers
    {"id": "2", "value": "beta"},
    {"id": "3", "value": "gamma"},
]
```

This test uses string values for all fields. CSV format doesn't preserve types, so this is correct behavior. However:

1. The JSONL test uses integers (`{"id": 1, "value": "alpha"}`)
2. The JSON test uses integers (`{"id": 10, "value": 1}`)
3. The CSV test uses strings (`{"id": "1", "value": "alpha"}`)

This inconsistency is intentional (CSV roundtrip preserves strings), but a comment explaining why CSV uses string values would improve clarity.

### 4. MINOR: Tests Don't Verify ArtifactDescriptor

**Severity:** Low
**Category:** Missing Coverage

**Location:** Lines 42, 88, 134 - `sink.write()` return values

The tests don't verify the `ArtifactDescriptor` returned by `sink.write()`. This is tested in `test_blob_sink.py`, but integration tests could also verify:
- Content hash matches
- Size bytes matches uploaded content

### 5. GOOD: Proper Import Skip Pattern

**Location:** Lines 17, 64, 110

```python
pytest.importorskip("azure.storage.blob")
```

Each test properly skips if the Azure SDK is not installed, preventing false failures in environments without the optional dependency.

### 6. MISSING: Error Path Integration Tests

**Severity:** Medium
**Category:** Missing Coverage

The file only tests happy-path scenarios. Missing integration tests for:
- Non-existent container
- Permission denied errors
- Network failures (harder to test with emulator)
- Overwrite=False when blob exists

### 7. MISSING: Schema Validation Integration Tests

**Severity:** Medium
**Category:** Missing Coverage

No tests verify that schema validation works correctly through the full roundtrip:
- Source with fixed schema rejects rows with missing fields
- Source with observed schema accepts any structure
- Quarantine behavior through emulator

## Test Path Integrity

**Status:** PASS

These tests use production plugin classes directly (`AzureBlobSink`, `AzureBlobSource`), not manual construction.

## Recommendations

1. **Add fixture location comment** to clarify where `azurite_blob_container` comes from
2. **Add comment to CSV test** explaining why string values are used
3. **Add error path integration tests** for common failure scenarios
4. **Add schema validation integration tests** to verify quarantine behavior end-to-end

## Overall Assessment

**Quality:** Good
**Coverage:** Moderate (happy path only)
**Risk Level:** Low

These are valuable integration tests that verify the complete Azure blob roundtrip. The lack of error-path testing is the main gap. The tests properly use `@pytest.mark.integration` marking for selective test runs.
