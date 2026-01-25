# Test Quality Review: test_blob_source.py

## Summary
The test file is well-structured with good organization and coverage of authentication methods. However, it has critical gaps in external system error handling, lacks property-based testing for schema validation edge cases, and contains assertions that access internal state violating encapsulation boundaries. Several tests violate the Three-Tier Trust Model by not verifying audit trail recording for quarantined rows.

## Poorly Constructed Tests

### Test: test_csv_parse_error_quarantines (line 518)
**Issue**: Weak assertion - does not verify quarantined row structure or audit trail recording
**Evidence**: Line 542 only checks `assert isinstance(rows, list)` - this passes even if quarantine logic is completely broken
**Fix**:
- Assert exactly 1 quarantined row is returned
- Verify quarantine_destination matches config
- Verify quarantine_error contains meaningful parse error
- Verify ctx.record_validation_error was called with parse mode
**Priority**: P1

### Test: test_csv_structural_failure_quarantines_blob (line 544)
**Issue**: Assertion is too weak - `assert len(rows) >= 0` is a tautology
**Evidence**: Line 565 - this assertion always passes, provides zero value
**Fix**:
- Assert exactly what quarantine behavior should occur (1 quarantined row with specific structure)
- Verify audit trail recording via ctx.record_validation_error
- Check quarantine_error message indicates structural failure
**Priority**: P1

### Test: test_close_clears_client (line 578)
**Issue**: Accesses internal state `source._blob_client` directly
**Evidence**: Line 588 - violates encapsulation, makes test brittle to implementation changes
**Fix**: Remove this test entirely - `close()` idempotency (line 572) is sufficient. Internal state clearing is an implementation detail, not a contract.
**Priority**: P2

### Test: test_auth_connection_string (line 611)
**Issue**: Multiple tests (lines 611-645) access internal `_auth_config` state
**Evidence**: Lines 614, 615, 627-628, 642-645 all assert on internal fields
**Fix**: These tests verify Pydantic model behavior, not plugin behavior. Consider:
- Move to `test_azure_auth.py` if testing AzureAuthConfig specifically
- Or delete entirely - config validation is already tested via PluginConfigError tests
**Priority**: P2

### Test: test_validation_failure_quarantines_row (line 420)
**Issue**: Does not verify audit trail recording via ctx.record_validation_error
**Evidence**: No assertion that ctx recorded the validation error
**Fix**: Add mock or spy on ctx.record_validation_error to verify:
- Called 1 time for the bad row
- Called with correct schema_mode
- Called with correct destination
**Priority**: P1

### Test: test_jsonl_malformed_line_quarantined_not_crash (line 358)
**Issue**: Does not verify audit trail recording
**Evidence**: Asserts quarantined row structure but not ctx.record_validation_error call
**Fix**: Verify ctx.record_validation_error was called with schema_mode="parse" for the malformed line
**Priority**: P1

## Misclassified Tests

### Tests: TestAzureBlobSourceAuthClientCreation (lines 751-841)
**Issue**: Tests are integration tests masquerading as unit tests
**Evidence**:
- Line 762 imports real Azure SDK modules
- Lines 776-791, 806-825, 832-840 patch Azure SDK calls
- Tests verify Azure SDK is called correctly, not plugin behavior
**Fix**:
- Move to `tests/integration/test_azure_blob_auth_integration.py`
- Mark with `@pytest.mark.integration`
- Require Azure SDK installed (not mocked)
- Current tests use mocks which provide false confidence - they verify mock call signatures, not actual Azure behavior
**Priority**: P1

### Tests: Config validation tests (lines 120-204)
**Issue**: These are Pydantic model tests, not plugin tests
**Evidence**: All tests in TestAzureBlobSourceConfigValidation verify Pydantic validation, not plugin logic
**Fix**:
- Consider moving to `tests/plugins/azure/test_azure_blob_config.py`
- Or accept as boundary testing - config validation failures ARE plugin initialization failures
- If kept, add docstring clarifying "These test config validation at initialization boundary"
**Priority**: P3 (lowest - arguable whether this is a problem)

## Infrastructure Gaps

### Gap: No property-based testing for schema validation
**Issue**: Schema validation with coercion is complex - edge cases likely untested
**Evidence**: Tests only cover basic type coercion (line 422-455) but not:
- Mixed valid/invalid types in same field across rows
- Coercion boundary cases (e.g., "123abc" as int)
- Unicode edge cases in string fields
- Nested JSON structures in free mode
**Fix**: Add `test_blob_source_schema_property_tests.py` using Hypothesis:
```python
@given(st.lists(st.dictionaries(st.text(), st.one_of(st.integers(), st.text(), st.none()))))
def test_schema_validation_handles_arbitrary_inputs(rows):
    # Verify no crash, all rows either valid or quarantined
```
**Priority**: P2

### Gap: No fixtures for mock Azure clients
**Issue**: Every test manually creates mock_client, sets return_value, patches download_blob
**Evidence**: Lines 213-214, 228-230, 242-243, 256-257, etc. - repeated 20+ times
**Fix**: Create fixtures:
```python
@pytest.fixture
def mock_csv_blob(mock_blob_client):
    def _make_csv(content: str):
        mock_client = MagicMock()
        mock_client.download_blob.return_value.readall.return_value = content.encode()
        mock_blob_client.return_value = mock_client
        return mock_client
    return _make_csv
```
Then use: `mock_csv_blob("id,name\n1,alice\n")`
**Priority**: P2

### Gap: No test for audit trail context recording
**Issue**: Tests verify quarantine row structure but not ctx.record_validation_error calls
**Evidence**: PluginContext is created (line 38) but never inspected or mocked
**Fix**:
- Mock ctx.record_validation_error in quarantine tests
- Assert it was called with correct (row, error, schema_mode, destination)
- This verifies the audit trail, not just the quarantine routing
**Priority**: P1

### Gap: No test for concurrent load() calls
**Issue**: Plugin might be called by multiple threads (DAG parallelism)
**Evidence**: No thread-safety tests for lazy _blob_client initialization (line 282)
**Fix**: Add test that calls load() from 2 threads simultaneously, verify no race condition in _get_blob_client
**Priority**: P3 (depends on whether engine parallelizes source loading)

### Gap: Missing error tests for external system failures
**Issue**: Only 3 generic error tests (lines 484-516), missing specific Azure SDK errors
**Evidence**:
- No test for `ClientAuthenticationError` (wrong credentials)
- No test for `ServiceRequestError` (network timeout)
- No test for `ResourceExistsError` (wrong resource type)
- No test for Azure throttling (429 responses)
**Fix**: Add specific Azure SDK error tests:
```python
def test_blob_download_authentication_error_propagates(...)
def test_blob_download_network_timeout_propagates(...)
def test_blob_download_throttled_propagates(...)
```
**Priority**: P1

### Gap: No test verifying blob is NOT re-downloaded on multiple load() calls
**Issue**: Current design re-downloads blob every time load() is called
**Evidence**: No test verifying caching behavior (or lack thereof)
**Fix**: Add test calling load() twice, verify _get_blob_client().download_blob() called twice (no caching). Document this as expected behavior or implement caching if needed.
**Priority**: P3

### Gap: No test for empty blob
**Issue**: What happens when blob exists but is 0 bytes?
**Evidence**: No test for empty CSV, empty JSON array, empty JSONL
**Fix**: Add tests:
```python
def test_empty_csv_blob_yields_no_rows(...)
def test_empty_json_array_yields_no_rows(...)
def test_empty_jsonl_blob_yields_no_rows(...)
```
**Priority**: P2

### Gap: No test for large blob handling
**Issue**: Memory usage for multi-GB blobs not tested
**Evidence**: All test blobs are tiny (< 1KB)
**Fix**: Add test with mock blob returning large content (10MB+), verify:
- No memory explosion
- Rows yielded incrementally (not all loaded into memory)
- HOWEVER: Current implementation reads entire blob into memory (line 325 `readall()`), so this is likely a DESIGN issue, not a test issue
**Priority**: P2 (flag as potential memory issue in production)

## Positive Observations

- **Excellent test organization**: Clear class-based grouping by concern (CSV, JSON, JSONL, validation, errors, auth)
- **Good use of make_config helper**: Eliminates boilerplate, makes test intent clear
- **Comprehensive auth method coverage**: All 3 auth methods tested (connection string, managed identity, service principal)
- **Clear test names**: Function names describe exactly what is being tested
- **Proper use of pytest.raises**: Error tests use context managers with match= for specificity
- **BUG-BLOB-01 regression coverage**: Lines 518-567 specifically test the bug fix, preventing regression

## Confidence Assessment

**Confidence Level**: Medium

These tests provide reasonable coverage of happy paths and basic error cases, but have gaps in:
- External system error handling (Azure SDK specific errors)
- Audit trail verification (ctx.record_validation_error calls)
- Schema validation edge cases (property-based testing needed)
- Internal state access violates encapsulation in several tests

## Risk Assessment

**High Risk Areas**:
1. **Weak quarantine tests** (P1): Current assertions too permissive, could miss broken quarantine logic
2. **Missing Azure SDK error tests** (P1): Production will encounter these, tests don't cover them
3. **No audit trail verification** (P1): Violates auditability standard - tests don't verify ctx recording

**Medium Risk Areas**:
1. **Misclassified integration tests** (P1 to reclassify): False confidence from mocked Azure SDK calls
2. **Missing property-based tests** (P2): Edge cases in schema validation likely uncovered

**Low Risk Areas**:
1. **Encapsulation violations** (P2): Tests access internal state, brittle but not wrong
2. **Missing concurrency tests** (P3): Depends on engine design

## Information Gaps

- **Unknown**: Does the engine call source.load() from multiple threads? (affects P3 concurrency gap)
- **Unknown**: Is blob caching expected or forbidden? (affects P3 caching gap)
- **Unknown**: What is the maximum expected blob size? (affects P2 memory gap)
- **Assumption**: ctx.record_validation_error is critical for audit trail (based on CLAUDE.md) - needs verification

## Caveats

- Review based on CLAUDE.md standards - some critiques may reflect project-specific rigor beyond typical practice
- "Poorly constructed" does not mean "wrong" - many tests work but could be more robust
- Misclassification of integration tests as unit tests is common but violates test pyramid principles
- Property-based testing gap is typical for most codebases, not a unique failure
- Internal state access is pragmatic for lifecycle tests (close()) but violates encapsulation ideals
