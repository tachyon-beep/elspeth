# Test Audit: test_audit_integration_fixes.py

**File:** `tests/integration/test_audit_integration_fixes.py`
**Lines:** 237
**Batch:** 95

## Summary

This test file verifies integration audit fixes (Tasks 1-7) from a previous remediation effort. It tests plugin discovery, DAG edge contracts, error payloads, and plugin context integration.

## Findings

### 1. TEST PATH INTEGRITY - MIXED USAGE

**Status:** Acceptable for Test Scope

**Location:** Lines 56-67, 137-161

```python
def test_dag_uses_typed_edges(self) -> None:
    graph = ExecutionGraph()
    schema_config = {"schema": {"mode": "observed"}}
    graph.add_node("src", node_type=NodeType.SOURCE, plugin_name="csv", config=schema_config)
    graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv", config=schema_config)
    graph.add_edge("src", "sink", label="continue", mode=RoutingMode.MOVE)
```

These tests use manual graph construction, but they're specifically testing:
1. `EdgeInfo` dataclass structure
2. `RoutingMode` enum preservation
3. DAG edge operations

These are graph utility tests, not pipeline execution tests. Manual construction is acceptable per CLAUDE.md guidelines.

### 2. GOOD: Uses Real Plugin Manager

**Location:** Lines 31-54, 163-205

```python
def test_full_plugin_discovery_flow(self) -> None:
    manager = PluginManager()
    manager.register_builtin_plugins()

    # All built-in plugins discoverable
    assert len(manager.get_sources()) >= 2
    assert len(manager.get_transforms()) >= 2
```

The tests correctly use the production `PluginManager` and instantiate real plugins.

### 3. GOOD: Type System Verification

**Location:** Lines 77-99

```python
def test_error_payloads_are_structured(self) -> None:
    """Error payloads follow ExecutionError schema."""
    error: ExecutionError = {
        "exception": "Test error",
        "type": "ValueError",
    }
```

This test verifies TypedDict schemas work correctly. While simple, it ensures type contracts are functioning.

### 4. POTENTIAL ISSUE: Resource Cleanup

**Severity:** Low

**Location:** Lines 100-119, 207-237

```python
def test_plugin_context_accepts_real_recorder(self) -> None:
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)
    # ... test logic ...
    # Cleanup
    db.close()
```

Manual cleanup with `db.close()` is used instead of fixtures or context managers. If an assertion fails before cleanup, resources may leak.

**Recommendation:** Use a fixture or `try/finally` for cleanup:

```python
@pytest.fixture
def landscape_db():
    db = LandscapeDB.in_memory()
    yield db
    db.close()
```

### 5. GOOD: Immutability Test

**Location:** Lines 121-135

```python
def test_edge_info_immutability(self) -> None:
    """EdgeInfo dataclass is frozen (immutable)."""
    edge = EdgeInfo(...)
    with pytest.raises(AttributeError):
        edge.from_node = "c"  # type: ignore[misc]
```

Good practice - verifies the frozen dataclass contract is enforced.

### 6. DEPRECATED COMMENT: Gate Plugins

**Severity:** Info

**Location:** Lines 37, 195-196

```python
assert len(manager.get_gates()) >= 0  # Gate plugins removed in WP-02
# ...
# Test gate - SKIPPED: Gate plugins removed in WP-02
```

The comments indicate gate plugins were removed in WP-02, but the code still checks for them (even if allowing 0). This is fine but may be confusing.

### 7. ALL TEST CLASSES PROPERLY NAMED

**Status:** Good

- `TestIntegrationAuditFixes` - Will be discovered by pytest

## Test Path Integrity

| Test | Uses Production Path | Notes |
|------|---------------------|-------|
| `test_full_plugin_discovery_flow` | YES | Uses real PluginManager |
| `test_dag_uses_typed_edges` | NO | Acceptable - testing DAG utilities |
| `test_error_payloads_are_structured` | N/A | Type verification only |
| `test_plugin_context_accepts_real_recorder` | YES | Uses real recorder |
| `test_edge_info_immutability` | N/A | Dataclass contract test |
| `test_routing_mode_is_enum_throughout_dag` | NO | Acceptable - testing enum preservation |
| `test_plugin_node_id_on_all_plugin_types` | YES | Uses real PluginManager |
| `test_landscape_recorder_integration` | YES | Uses real recorder |

## Defects

None identified.

## Missing Coverage

1. **Low:** No negative test for plugin discovery (e.g., unknown plugin name)
2. **Low:** No test for `EdgeInfo` with invalid data

## Recommendations

1. **Use fixtures for database cleanup** - Convert manual `db.close()` calls to fixtures for better resource management

2. **Consider removing gate plugin assertions** - Since gates were removed, the `>= 0` assertion is a no-op

3. **Add production path verification** - One test should verify the fixes work through `ExecutionGraph.from_plugin_instances()`

## Overall Assessment

**Quality: Good**

The tests adequately verify the integration fixes they were designed for. Most tests appropriately use production components (PluginManager, LandscapeRecorder). The manual graph construction is acceptable for the DAG utility tests.
