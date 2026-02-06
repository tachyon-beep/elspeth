# Audit: tests/property/contracts/test_serialization_properties.py

## Overview
Property-based tests for contract dataclass serialization - verifying TokenInfo, TransformResult, and RoutingAction serialize correctly for audit storage.

**Lines:** 558
**Test Classes:** 6
**Test Methods:** 17

## Audit Results

### 1. Defects
**PASS** - No defects found.

Tests correctly verify:
- TokenInfo preserves all fields through construction
- TransformResult JSON round-trip preserves data
- RoutingAction JSON round-trip preserves routing decisions
- Optional fields handled correctly

### 2. Overmocking
**PASS** - No mocking used.

Tests directly exercise dataclass serialization with `json.dumps(asdict(...))`.

### 3. Missing Coverage
**MINOR** - Some gaps:

1. **TransformResult.skip()**: Not tested for serialization
2. **RoutingAction.skip()**: Not tested
3. **Large row data**: Tests use `row_data` strategy with max_size=20, could test larger
4. **PipelineRow with contract metadata**: Tests use OBSERVED contracts only

### 4. Tests That Do Nothing
**PASS** - All tests have meaningful assertions.

Good pattern for round-trip testing:
```python
serialized = json.dumps(_token_to_dict(token))
parsed = json.loads(serialized)
assert parsed["row_id"] == row_id
assert parsed["token_id"] == token_id
```

### 5. Inefficiency
**MEDIUM** - Code duplication in strategies.

Lines 107-129 define gate reason strategies that could be shared:
- `config_gate_reasons`
- `plugin_gate_reasons`

These are similar to strategies that might exist elsewhere. Consider moving to `conftest.py`.

### 6. Structural Issues
**MINOR** - Helper function placement.

`_routing_action_to_dict()` is defined at the bottom of the file (lines 547-558) but used earlier. Should be with other helpers at the top.

Also, `_make_observed_contract()` and `_wrap_dict_as_pipeline_row()` are good helpers but could be in conftest for reuse.

## PipelineRow Handling

The test file handles the transition from dict to PipelineRow correctly:
```python
def _wrap_dict_as_pipeline_row(data: dict[str, Any]) -> PipelineRow:
    """Wrap dict as PipelineRow with OBSERVED contract for property tests."""
    return PipelineRow(data, _make_observed_contract())
```

This is necessary because TokenInfo now expects PipelineRow, not dict.

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | No mocking needed |
| Missing Coverage | MINOR | skip() variants not tested |
| Tests That Do Nothing | PASS | All assertions meaningful |
| Inefficiency | MEDIUM | Strategy duplication |
| Structural Issues | MINOR | Helper placement |

**Overall:** HIGH QUALITY - Good serialization round-trip testing. Could benefit from strategy consolidation.
