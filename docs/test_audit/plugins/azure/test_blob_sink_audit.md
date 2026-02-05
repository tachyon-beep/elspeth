# Test Audit: tests/plugins/azure/test_blob_sink.py

**Auditor:** Claude Code Audit
**Date:** 2026-02-05
**Test File:** `/home/john/elspeth-rapid/tests/plugins/azure/test_blob_sink.py`
**Lines:** 987

## Summary

This file provides comprehensive unit tests for `AzureBlobSink`, covering config validation, CSV/JSON/JSONL writing, path templating, overwrite behavior, artifact descriptors, auth methods, and schema validation. The tests use appropriate mocking to isolate the sink from Azure SDK.

## Findings

### 1. GOOD: Consistent Mocking Strategy

**Location:** Lines 39-42 (`mock_container_client` fixture)

The fixture mocks at the `_get_container_client` method level, which is the correct abstraction boundary:
- Tests the sink's logic without Azure SDK
- Doesn't mock too deeply (avoids coupling to implementation details)
- Doesn't mock too high (still exercises serialization/formatting logic)

### 2. ISSUE: Potential Test Pollution from Fixture

**Severity:** Medium
**Category:** Test Structure

**Location:** Lines 39-42

```python
@pytest.fixture
def mock_container_client() -> Generator[MagicMock, None, None]:
    """Create a mock container client for testing."""
    with patch("elspeth.plugins.azure.blob_sink.AzureBlobSink._get_container_client") as mock:
        yield mock
```

The fixture patches at the class level but doesn't configure return values. Each test must configure its own mock behavior (e.g., `mock_container.get_blob_client.return_value = mock_blob_client`), leading to:
1. Repetitive setup code across tests
2. Risk of forgetting to configure mocks (would cause AttributeError)

**Recommendation:** Create a more complete fixture that provides a configured mock hierarchy.

### 3. GOOD: Comprehensive Config Validation Tests

**Location:** Lines 112-188 (`TestAzureBlobSinkConfigValidation`)

Tests cover all validation rules:
- Missing auth method
- Empty connection string
- Missing container/blob_path/schema
- Unknown fields (extra='forbid')
- Mutual exclusivity (display_headers vs restore_source_headers)

### 4. ISSUE: Missing Test for Invalid Format Value

**Severity:** Low
**Category:** Missing Coverage

**Location:** Class `TestAzureBlobSinkConfigValidation`

No test verifies that an invalid format value (e.g., `format="xml"`) is rejected.

### 5. GOOD: Schema Mode Tests

**Location:** Lines 857-987 (`TestAzureBlobSinkSchemaValidation`)

Tests verify the three schema modes:
- `flexible`: Includes declared fields + extras from data
- `fixed`: Only declared fields
- Field ordering (declared first, then extras)

These mirror the tests in `test_csv_sink.py`, ensuring consistent behavior across sinks.

### 6. ISSUE: Test Uses Internal Attribute

**Severity:** Low
**Category:** Test Fragility

**Location:** Lines 587-597 (`test_close_clears_client`)

```python
assert sink._container_client is None
```

Testing private attributes (`_container_client`) couples the test to implementation details. If the attribute is renamed, the test fails even if the behavior is correct.

**Recommendation:** Test observable behavior (e.g., calling write after close raises error) rather than internal state.

### 7. GOOD: Template Path Tests

**Location:** Lines 396-436 (`TestAzureBlobSinkPathTemplating`)

Tests verify Jinja2 template rendering for:
- `{{ run_id }}` - rendered correctly
- `{{ timestamp }}` - rendered with ISO format

### 8. ISSUE: Timestamp Test is Time-Sensitive

**Severity:** Low
**Category:** Potential Flakiness

**Location:** Lines 419-436 (`test_blob_path_with_timestamp_template`)

```python
assert rendered_path.startswith("results/20")
assert "T" in rendered_path  # ISO format has T separator
```

This test assumes the year starts with "20" (true until 2100) and that ISO format is used. It would be better to use a regex pattern or freeze time.

### 9. ISSUE: Inconsistent Error Assertion Patterns

**Severity:** Low
**Category:** Inconsistency

**Location:** Lines 550-576 (`TestAzureBlobSinkErrors`)

```python
with pytest.raises(Exception, match="Failed to upload blob"):
    ...
with pytest.raises(Exception, match="Connection refused"):
    ...
```

Tests catch generic `Exception` with string matching. If the production code raises a specific exception type (e.g., `AzureBlobError`), tests should match that type for better specificity.

### 10. GOOD: Auth Client Creation Tests

**Location:** Lines 765-855 (`TestAzureBlobSinkAuthClientCreation`)

Tests verify the correct Azure SDK credential classes are instantiated for each auth method:
- `DefaultAzureCredential` for managed identity
- `ClientSecretCredential` for service principal
- `from_connection_string` factory for connection string

The `skip_if_no_azure` autouse fixture properly skips when Azure SDK is unavailable.

### 11. MINOR: Unused ctx Parameter

**Severity:** Low
**Category:** Inefficiency

**Location:** Lines 779, 807 (`test_managed_identity_uses_default_credential`, `test_service_principal_uses_client_secret_credential`)

The `ctx: PluginContext` parameter is passed to these tests but never used. The tests only call `sink._auth_config.create_blob_service_client()`, not any sink methods that require context.

## Test Path Integrity

**Status:** PASS

This file tests the `AzureBlobSink` plugin directly using production classes. No manual graph construction or test path integrity violations.

## Recommendations

1. **Add invalid format test** to verify `format="xml"` is rejected
2. **Refactor fixture** to provide more complete mock hierarchy, reducing repetitive setup
3. **Test observable behavior** instead of internal attributes in lifecycle tests
4. **Use freezegun** or regex for timestamp tests to reduce flakiness
5. **Use specific exception types** in error tests if production code defines them
6. **Remove unused ctx parameters** or use them if needed

## Overall Assessment

**Quality:** Good
**Coverage:** Comprehensive
**Risk Level:** Low

The test file is well-organized with clear class structure by concern (protocol, config, CSV, JSON, JSONL, etc.). The 987 lines provide thorough coverage of the sink's functionality. Main issues are minor code quality concerns rather than test defects.
