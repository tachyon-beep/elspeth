# Test Audit: test_plugin_detection.py

**File:** `/home/john/elspeth-rapid/tests/engine/test_plugin_detection.py`
**Lines:** 236
**Audit Date:** 2026-02-05
**Auditor:** Claude

## Summary

Tests for type-safe plugin detection in the processor. Verifies that `isinstance`-based plugin detection works correctly with the base class hierarchy (`BaseTransform`, `BaseGate`). This is a critical security/integrity test that ensures duck-typed plugins are rejected.

**Overall Assessment:** GOOD - Tests verify both the detection mechanism (`isinstance`) and the enforcement mechanism (processor rejection).

## Test Classes

### TestPluginTypeDetection (4 tests)

Basic isinstance checks for plugin types.

### TestPluginInheritanceHierarchy (1 test)

Verifies transforms are not gates.

### TestProcessorRejectsDuckTypedPlugins (2 tests)

Critical tests that verify the processor actually rejects duck-typed plugins at runtime.

## Findings

### 1. POSITIVE: Two-Layer Testing Strategy

**Severity:** N/A (Good Practice)

The tests correctly implement a two-layer strategy:
1. **Layer 1 (TestPluginTypeDetection):** Verifies `isinstance()` returns correct values
2. **Layer 2 (TestProcessorRejectsDuckTypedPlugins):** Verifies processor enforces the rejection

This ensures that even if `isinstance` works correctly, the processor actually uses it:

```python
# Lines 170-178
with pytest.raises(TypeError, match="Unknown transform type"):
    processor.process_row(
        row_index=0,
        source_row=SourceRow.valid({"value": 1}, contract=_make_observed_contract({"value": 1})),
        transforms=[duck],
        ctx=ctx,
    )
```

### 2. POSITIVE: Documents Behavior Change

**Severity:** N/A (Good Practice)

Test docstrings clearly document why this matters:

```python
# Lines 60-65
def test_duck_typed_transform_not_recognized(self) -> None:
    """Duck-typed transforms without inheritance should NOT be recognized.

    This is the key behavior change - hasattr checks would have accepted
    this class, but isinstance checks correctly reject it.
    """
```

### 3. Minor Issue: Type Ignore Comments for Known Behavior

**Severity:** Info

Several `# type: ignore[unreachable]` comments are used where mypy knows the check will always return False. This is correct behavior - the comments document that the runtime check is intentional even though mypy knows the answer:

```python
# Line 78
assert not isinstance(duck, BaseTransform)  # type: ignore[unreachable]
```

This is appropriate since the tests verify runtime behavior that mypy can statically prove.

### 4. POSITIVE: Direct Processor Integration Testing

**Severity:** N/A (Good Practice)

`TestProcessorRejectsDuckTypedPlugins` creates real `LandscapeDB`, `LandscapeRecorder`, and `RowProcessor` instances rather than mocking them:

```python
# Lines 144-162
db = LandscapeDB.in_memory()
recorder = LandscapeRecorder(db)
run = recorder.begin_run(config={}, canonical_version="v1")
# ... register source ...
processor = RowProcessor(
    recorder=recorder,
    span_factory=SpanFactory(),
    run_id=run.run_id,
    source_node_id=NodeID(source.node_id),
)
```

This ensures the test catches real integration bugs.

### 5. Unused Import

**Severity:** Low
**Type:** Code Quality

Line 13 imports `NodeID` and `NodeType` which are used, but `SourceRow` from line 13 is only used in `TestProcessorRejectsDuckTypedPlugins` where it's redundantly available. The import is fine since it's used.

### 6. Note on Deleted Aggregation Tests

**Severity:** Info

The module docstring notes that BaseAggregation tests were deleted in an aggregation structural cleanup. This is documented:

```python
# Lines 7-8
NOTE: BaseAggregation tests were DELETED in aggregation structural cleanup.
Aggregation is now handled by batch-aware transforms (is_batch_aware=True).
```

## Missing Coverage

### 1. Batch-Aware Transform Detection

**Severity:** Medium

Since BaseAggregation was removed and replaced with `is_batch_aware=True` on transforms, there should be tests verifying:
- Transforms with `is_batch_aware=True` are detected correctly
- Duck-typed classes with `is_batch_aware=True` attribute are still rejected

This ensures the new pattern is also type-safe.

### 2. Gate Detection in Processor

**Severity:** Low

While `test_processor_rejects_duck_typed_gate` exists, it passes the duck gate to `transforms=[duck]`. The processor might handle gates differently in a different code path. Consider verifying gate-specific handling if gates have a separate path.

### 3. Protocol vs Base Class

**Severity:** Low

No test verifies that `TransformProtocol` and `GateProtocol` (runtime_checkable Protocols) behave correctly with duck typing. The tests focus on base classes. If protocol checks are used elsewhere, they could inadvertently accept duck-typed objects.

## Structural Issues

None identified. All test classes have "Test" prefix and will be discovered by pytest.

## Recommendations

1. **Add batch-aware transform detection tests** to verify the new aggregation pattern is also type-safe.

2. **Consider adding protocol-based detection tests** if protocols are used for plugin detection anywhere in the codebase.

3. **Verify gate code path** - ensure the test actually exercises the gate-specific rejection path if one exists.

## Verdict

**PASS** - Tests effectively verify that the processor enforces type-safe plugin detection, rejecting duck-typed objects that don't inherit from the proper base classes. The two-layer testing strategy (isinstance checks + processor enforcement) provides good coverage.
