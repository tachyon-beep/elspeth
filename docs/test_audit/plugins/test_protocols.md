# Audit: tests/plugins/test_protocols.py

## Summary
Comprehensive protocol conformance tests. Well-organized with good coverage of protocol definitions, but tests mostly verify structural conformance rather than behavioral correctness.

## Findings

### 1. Tests That Do Nothing - Protocol Attribute Checks

**Location:** Lines 30-34, 94-106, 627-643

**Issue:** Tests like `test_source_protocol_definition` check `hasattr(SourceProtocol, "__protocol_attrs__")`. This verifies Python internals, not ELSPETH code.

**Severity:** Low - documentation tests, but provide false confidence.

### 2. Excessive Inline Class Definitions

**Location:** Lines 44-74, 119-151, 170-203, 378-413, 423-445, 499-550, 563-620

**Issue:** Every test creates inline classes implementing protocols. This is 400+ lines of boilerplate. Common test fixtures would reduce duplication.

**Example pattern repeated:**
```python
class MySource:
    name = "my_source"
    output_schema = OutputSchema
    node_id: str | None = None
    determinism = Determinism.IO_READ
    plugin_version = "1.0.0"
    # ... 10+ more attributes
```

**Recommendation:** Create pytest fixtures or a test helper module with standard test implementations.

### 3. Type Ignore Proliferation

**Location:** Lines 80-83, 149-151, 207-210, 406-409, 450, 543, 611

**Issue:** Many `# type: ignore[unreachable]` comments after isinstance checks. This suggests mypy disagrees with runtime Protocol checking.

**Impact:** Low for correctness, but clutters test code.

### 4. Redundant Deletion Tests

**Location:** Lines 332-354

**Issue:** `TestAggregationProtocolDeleted` class duplicates tests from `test_node_id_protocol.py`.

**Recommendation:** Keep in one location only.

### 5. Coalesce Protocol Test Missing Branches

**Location:** Lines 357-459

**Issue:** `test_quorum_requires_threshold` doesn't actually test that QUORUM *requires* a threshold - it just creates a valid config with one. Should test that missing threshold raises an error.

**Severity:** Medium - test name promises more than it delivers.

### 6. Sink Protocol Row Parameter Name Check

**Location:** Lines 465-487

**Issue:** `test_sink_batch_write_signature` inspects method signature to verify parameter is named "rows" not "row". This is brittle - signature inspection can break with Python version changes or wrapper decorators.

**Severity:** Low - but unusual test pattern.

### 7. ClassVar Misuse in Test Classes

**Location:** Lines 573, multiple test sink implementations

**Issue:** Test sinks use `rows: ClassVar[list[dict[str, Any]]] = []` which makes rows shared across ALL instances of the class. This could cause test pollution.

**Example:**
```python
class MemorySink:
    rows: ClassVar[list[dict[str, Any]]] = []  # SHARED across all instances!
```

**Severity:** Medium - could cause intermittent test failures.

## Missing Coverage

1. **Protocol error handling** - what happens when process() raises?
2. **Async protocol methods** - if any exist
3. **Protocol versioning** - compatibility across versions
4. **Edge cases for batch processing** - empty lists, single items
5. **Coalesce edge cases** - missing branches, timeout behavior

## Structural Issues

### Copy-Paste Pattern
The test file shows heavy copy-paste patterns for protocol implementations. A single bad copy could hide bugs.

## Verdict

**Overall Quality:** Fair

Good structural coverage of protocol definitions, but:
- Tests mostly verify Python Protocol machinery works
- Excessive boilerplate reduces maintainability
- Some misleading test names (quorum test)
- Potential test pollution from ClassVar usage

## Recommendations

1. **Create test fixtures** for common protocol implementations
2. **Remove ClassVar** from instance attributes in test classes
3. **Add behavioral tests** that verify protocols work end-to-end
4. **Consolidate deletion tests** to one location
5. Fix `test_quorum_requires_threshold` to actually test the requirement
6. Consider using parameterized tests for repetitive protocol checks
