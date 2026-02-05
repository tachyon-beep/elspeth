# Test Audit: test_keyvault_fingerprint.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_keyvault_fingerprint.py`
**Lines:** 130
**Batch:** 100-101

## Summary

Integration tests for Azure Key Vault secret loading via the YAML-based secrets configuration. Tests require real Azure credentials and are marked with `@pytest.mark.integration`.

## Audit Findings

### 1. GOOD: Proper Integration Test Design

**Positive:**
- Tests are properly marked with `@pytest.mark.integration` for conditional execution
- Clear documentation on setup requirements and how to run
- Tests actual Key Vault integration (not mocked)
- Documents breaking change from old `ELSPETH_KEYVAULT_URL` approach

### 2. DEFECT: Missing Fixture Definition

**Severity:** High
**Location:** Line 32, 70, 106

Tests use `keyvault_url: str` fixture that is documented as coming from `tests/integration/conftest.py`:

```python
def test_load_fingerprint_key_via_secrets_config(self, keyvault_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
```

However, if this fixture is not properly defined or the `--keyvault-url` CLI option is not provided, tests will fail with `fixture 'keyvault_url' not found` or similar errors.

**Verification needed:** Confirm `tests/integration/conftest.py` properly defines this fixture with appropriate skip logic when the URL is not provided.

### 3. COVERAGE: Missing Error Handling Tests

**Severity:** Medium

Missing coverage for:
- Invalid vault URL (malformed URL)
- Vault URL that resolves but authentication fails
- Secret that doesn't exist in the vault
- Network timeout when accessing vault
- Partial success (one secret loads, another fails)

### 4. GOOD: Breaking Change Documentation

The test class `TestOldEnvVarApproachRemoved` properly documents and verifies the breaking change:

```python
def test_elspeth_keyvault_url_no_longer_used(self, keyvault_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ELSPETH_KEYVAULT_URL no longer triggers Key Vault lookup.
    ...
    """
```

This is excellent practice for documenting migration requirements.

### 5. STRUCTURAL: Environment Cleanup Concern

**Severity:** Low
**Location:** Line 95

After loading secrets, the test verifies:
```python
assert os.environ.get("ELSPETH_FINGERPRINT_KEY") is not None
```

However, this modifies `os.environ` which could leak between tests. While `monkeypatch.delenv()` is used to clear before the test, there's no cleanup after `load_secrets_from_config()` sets the value.

**Recommendation:** Either:
- Verify `monkeypatch` fixture automatically restores environment on teardown (it should)
- Or explicitly save/restore environment in a fixture

### 6. COVERAGE: No Test for Malformed Secrets

**Severity:** Low

No tests for secrets that:
- Are empty strings
- Contain invalid characters
- Are extremely long (potential buffer issues)

### 7. GOOD: Test Independence

Each test properly uses `monkeypatch.delenv()` to ensure clean state:
```python
monkeypatch.delenv("ELSPETH_FINGERPRINT_KEY", raising=False)
```

## Test Path Integrity

**Status:** PASS

Tests use production code paths:
- `SecretsConfig()` - production config class
- `load_secrets_from_config()` - production loader
- `get_fingerprint_key()` - production accessor

No manual construction or bypass of production paths.

## Recommendations

1. **High Priority:** Verify the `keyvault_url` fixture exists in conftest and handles missing CLI args gracefully
2. **Medium Priority:** Add error handling tests for vault access failures
3. **Low Priority:** Confirm pytest's monkeypatch auto-restores environment
4. **Enhancement:** Add tests for malformed/edge-case secret values
