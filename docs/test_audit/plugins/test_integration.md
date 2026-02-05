# Audit: tests/plugins/test_integration.py

## Summary
Integration tests for the plugin system demonstrating source -> transform -> sink workflow.

## Findings

### 1. Good Practices
- Full workflow test with custom plugins
- Tests schema compatibility checking
- Verifies BaseAggregation removal (regression test)
- Uses real PluginManager for registration
- Tests actual data flow through pipeline

### 2. Issues

#### ClassVar for State Storage
- **Location**: Line 80
- **Issue**: `MemorySink.collected: ClassVar[list[dict[str, Any]]] = []`
- **Impact**: Medium - shared state between tests if not reset
- **Mitigation**: Line 130 resets `MemorySink.collected = []`

#### Type Ignores for Plugin Construction
- **Location**: Lines 126-128
- **Issue**: `source_cls({"values": [10, 50, 100]})  # type: ignore[call-arg]`
- **Impact**: Low - protocol doesn't define __init__ but concrete classes do
- **Note**: This is a known limitation of protocol-based design

#### Manual Schema Contract Creation
- **Location**: Lines 43-55
- **Issue**: Test creates SchemaContract manually in load()
- **Impact**: Low - necessary for test but shows complexity

### 3. Missing Coverage

#### No Error Path Testing
- What happens when transform fails?
- What happens when sink write fails?
- No retry/recovery testing

#### No Async Plugin Testing
- All plugins are synchronous
- Async workflow not tested

#### No Batch Transform Testing
- Only row-by-row transform tested
- Batch transforms (is_batch_aware=True) not tested here

### 4. Schema Compatibility Test

test_schema_validation_in_pipeline verifies:
- Incompatible schemas are detected
- Missing fields are reported

## Verdict
**PASS** - Good end-to-end integration test. Some edge cases not covered.

## Risk Assessment
- **Defects**: None
- **Overmocking**: None - uses real components
- **Missing Coverage**: Medium - error paths not tested
- **Tests That Do Nothing**: None
- **Inefficiency**: Low - ClassVar state needs explicit reset
