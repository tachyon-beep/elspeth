# Test Audit: tests/plugins/sources/test_null_source.py

**Batch:** 137
**File:** tests/plugins/sources/test_null_source.py (76 lines)
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file tests the NullSource plugin, which is a special-purpose source that yields no rows (used for resume operations where data comes from the payload store). The tests cover basic protocol compliance and attribute verification.

**Overall Assessment:** ADEQUATE - Basic coverage, missing some scenarios

## Findings

### 1. Tests Use Correct Protocol Verification [POSITIVE]

**Location:** Lines 34-40

**Observation:** Tests properly verify protocol satisfaction:

```python
def test_null_source_satisfies_protocol(self) -> None:
    """NullSource satisfies SourceProtocol."""
    from elspeth.plugins.sources.null_source import NullSource

    source = NullSource({})
    # This should not raise - source satisfies protocol
    assert isinstance(source, SourceProtocol)
```

### 2. Good Idempotent Close Test [POSITIVE]

**Location:** Lines 52-58

**Observation:** Tests that `close()` can be called multiple times:

```python
def test_null_source_close_is_idempotent(self) -> None:
    """close() can be called multiple times safely."""
    source = NullSource({})
    source.close()
    source.close()  # Should not raise
```

### 3. Missing Test: Context Not Used [MISSING COVERAGE]

**Severity:** Low
**Location:** General

**Issue:** The test passes a context to `load()` but doesn't verify that NullSource ignores it safely:

```python
def test_null_source_yields_nothing(self, ctx: PluginContext) -> None:
    """NullSource.load() yields no rows."""
    source = NullSource({})
    rows = list(source.load(ctx))
    assert rows == []
```

**Recommendation:** This is likely fine since the implementation docstring says `ctx` is unused, but consider adding a comment or separate test verifying context is truly not used (e.g., passing `None` or a mock that raises on any method call).

### 4. Missing Test: Schema Contract [MISSING COVERAGE]

**Severity:** Medium
**Location:** General

**Issue:** No test verifies that NullSource provides a schema contract. Other sources have `get_schema_contract()` tests.

**Recommendation:** Add test:
```python
def test_null_source_has_schema_contract(self) -> None:
    """NullSource provides a schema contract for protocol compliance."""
    source = NullSource({})
    # NullSource may not have a meaningful contract, but should have one
    # if SourceProtocol requires it
    contract = source.get_schema_contract()
    # Verify expected behavior
```

### 5. Missing Test: Default Schema Config [MISSING COVERAGE]

**Severity:** Low
**Location:** General

**Issue:** The implementation adds a default schema if not provided:

```python
def __init__(self, config: dict[str, Any]) -> None:
    config_copy = dict(config)
    if "schema" not in config_copy:
        config_copy["schema"] = {"mode": "observed"}
    super().__init__(config_copy)
```

But no test verifies this behavior works correctly.

**Recommendation:** Add tests for:
1. NullSource with no config `{}`
2. NullSource with explicit schema config

### 6. Missing Test: With Resume Context [MISSING COVERAGE]

**Severity:** Medium
**Location:** General

**Issue:** NullSource is documented as being used "for resume operations where row data comes from the payload store", but there's no integration test verifying this use case.

**Recommendation:** Consider adding a test that simulates the resume scenario, even if it's just a placeholder with a comment explaining the integration is tested elsewhere.

### 7. Good Determinism Verification [POSITIVE]

**Location:** Lines 60-67

**Observation:** Tests verify determinism marking:

```python
def test_null_source_has_determinism(self) -> None:
    """NullSource has appropriate determinism marking."""
    from elspeth.contracts import Determinism

    source = NullSource({})
    # NullSource is deterministic - always yields nothing
    assert source.determinism == Determinism.DETERMINISTIC
```

### 8. Test Imports Inside Test Methods [STRUCTURAL ISSUE]

**Severity:** Low
**Location:** Multiple tests

**Issue:** Imports are done inside test methods rather than at module level:

```python
def test_null_source_yields_nothing(self, ctx: PluginContext) -> None:
    from elspeth.plugins.sources.null_source import NullSource
    # ...
```

**Recommendation:** Move imports to module level for clarity and slight performance improvement. This pattern appears in other test files too, so it may be a project convention.

### 9. Missing Test: Output Schema Subclass Check [POTENTIAL ISSUE]

**Severity:** Low
**Location:** Lines 42-50

**Issue:** Test checks that `output_schema` is a subclass of `PluginSchema`, but doesn't verify it's specifically `NullSourceSchema`:

```python
def test_null_source_has_output_schema(self) -> None:
    """NullSource has an output_schema attribute."""
    from elspeth.contracts import PluginSchema
    source = NullSource({})
    assert hasattr(source, "output_schema")
    # output_schema must be a PluginSchema subclass
    assert issubclass(source.output_schema, PluginSchema)
```

**Recommendation:** Consider also asserting `source.output_schema.__name__ == "NullSourceSchema"` or checking specific expected behavior of the schema.

## Missing Coverage Analysis

### Recommended Additional Tests

1. **Schema contract verification** - Test that `get_schema_contract()` works
2. **Default schema config behavior** - Test with empty config
3. **Resume integration scenario** - Even if basic, document the intended use
4. **Explicit schema config** - Test with custom schema provided
5. **Multiple load calls** - Test that load can be called multiple times

## Verdict

**Status:** PASS with recommendations

The test file covers basic protocol compliance for NullSource, but given that NullSource is used in the critical resume path, more comprehensive testing would be valuable. The tests that exist are correct and well-written.

## Recommendations Priority

1. **Medium:** Add test for schema contract (`get_schema_contract()`)
2. **Low:** Add test for default schema config behavior
3. **Low:** Consider adding test that documents resume integration scenario
4. **Low:** Move imports to module level for consistency
