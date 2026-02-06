# Test Audit: test_telemetry_wiring.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_telemetry_wiring.py`
**Lines:** 371
**Batch:** 107

## Overview

Integration tests verifying that Orchestrator correctly wires `telemetry_emit` to PluginContext. These tests catch the wiring bugs that unit tests miss by using production Orchestrator, not manual PluginContext.

## Audit Findings

### 1. POSITIVE: Correct Test Path Usage

The tests explicitly use production code paths:

```python
def create_test_graph(config: PipelineConfig) -> ExecutionGraph:
    """Build a graph using the production factory path."""
    return build_production_graph(config)
```

Uses `build_production_graph()` from `orchestrator_test_helpers.py` as required.

---

### 2. POSITIVE: Captures Actual Callback for Verification

**Location:** Lines 195-252

Clever test design that captures the actual callback wired by the orchestrator:

```python
class CallbackCapturingTransform(SimpleTransform):
    def on_start(self, ctx: Any) -> None:
        nonlocal captured_callback
        captured_callback = ctx.telemetry_emit

# Later verification:
assert captured_callback is not None, "ctx.telemetry_emit was not set"
callback_name = getattr(captured_callback, "__name__", str(captured_callback))
assert callback_name != "<lambda>", "..."
```

This ensures the production code path actually wires the callback.

---

### 3. STRUCTURAL: SimpleTransform Missing Protocol Requirements

**Severity:** Low
**Location:** Lines 78-110

`SimpleTransform` doesn't inherit from `_TestTransformBase`:

```python
class SimpleTransform:
    """Transform that passes through rows unchanged."""
    name = "simple_transform"
    # ... direct attribute definition
```

While this works, it's inconsistent with other test helpers. Minor maintainability concern.

---

### 4. MISSING COVERAGE: Telemetry Filtering by Granularity

**Severity:** Medium

Tests set granularity but don't verify filtering:

```python
config = MockTelemetryConfig(granularity=TelemetryGranularity.FULL)
```

Should add tests verifying that:
- `LIFECYCLE` granularity filters out row-level events
- `ROWS` granularity filters out external call details
- `FULL` emits everything

---

### 5. MISSING COVERAGE: Error Event Telemetry

**Severity:** Medium

No tests for:
- Telemetry emission when transforms fail
- Telemetry for quarantined rows
- `RunFailed` event emission

---

### 6. POSITIVE: Tests Both Enabled and Disabled States

Tests verify behavior with and without telemetry manager:

```python
class TestNoTelemetryWithoutManager:
    def test_no_crash_without_telemetry_manager(self, ...):
        # No telemetry_manager - should use default no-op
        orchestrator = Orchestrator(landscape_db)
        result = orchestrator.run(...)
        assert result.status == RunStatus.COMPLETED

    def test_context_telemetry_emit_is_noop_without_manager(self, ...):
        # Verify it's callable without error
        captured_callback(RunStarted(...))
```

---

### 7. INCOMPLETE: Resume Path Test

**Severity:** Medium
**Location:** Lines 254-293

The test documents that it only tests the main path:

```python
def test_telemetry_wiring_works_in_resume_path(self, ...):
    """Telemetry is also wired correctly in the resume code path.
    ...
    """
    # This test verifies the main path works (resume path is harder to test
    # without setting up a partial run). The fix added telemetry_emit to both.
```

This is acknowledged but should be addressed with a proper resume path test.

---

### 8. STRUCTURAL: DynamicSchema Defined But Only Used Internally

**Severity:** Low
**Location:** Lines 57-60

```python
class DynamicSchema(PluginSchema):
    """Dynamic schema for testing - allows any fields."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
```

This is fine, but could be extracted to conftest.py for reuse.

---

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Positive Findings | 4 | N/A |
| Missing Coverage | 3 | Medium, Medium, Medium |
| Structural Issues | 2 | Low |
| Defects | 0 | N/A |

## Recommendations

1. **MEDIUM:** Add tests for telemetry granularity filtering behavior
2. **MEDIUM:** Add tests for error/failure telemetry events
3. **MEDIUM:** Implement proper resume path telemetry test with partial run setup
4. **LOW:** Consider extracting DynamicSchema to conftest.py
5. **LOW:** Have SimpleTransform inherit from _TestTransformBase for consistency

## Overall Assessment

This is a well-designed integration test file that properly uses production code paths. The core telemetry wiring verification is sound. The main gaps are in coverage of edge cases (errors, granularity filtering) and the resume path.
