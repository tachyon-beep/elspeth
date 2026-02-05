# Test Audit: tests/engine/test_processor_modes.py

**Lines:** 1144
**Test count:** 9 test functions across 3 test classes
**Audit date:** 2026-02-05
**Batch:** 86

## Summary

Tests for aggregation output modes (passthrough and transform) in RowProcessor. Verifies correct token identity behavior, row count validation, downstream transform continuation, and proper outcome recording for batch-aware transforms.

## Test Inventory

| Class | Test | Lines | Purpose |
|-------|------|-------|---------|
| TestProcessorPassthroughMode | test_aggregation_passthrough_mode | 50-192 | Passthrough mode preserves token IDs |
| TestProcessorPassthroughMode | test_aggregation_passthrough_validates_row_count | 194-277 | Validates error on wrong row count |
| TestProcessorPassthroughMode | test_aggregation_passthrough_continues_to_next_transform | 279-427 | Passthrough rows continue to next transform |
| TestProcessorTransformMode | test_aggregation_transform_mode | 433-584 | Transform mode creates new tokens from N->M |
| TestProcessorTransformMode | test_aggregation_transform_mode_single_row_output | 586-703 | Transform mode N->1 with new token |
| TestProcessorTransformMode | test_aggregation_transform_mode_continues_to_next_transform | 705-865 | Transform output continues downstream |
| TestProcessorSingleMode | test_aggregation_single_mode_continues_to_next_transform | 879-1033 | Transform mode aggregated row continues |
| TestProcessorSingleMode | test_aggregation_transform_mode_no_downstream_completes_immediately | 1035-1144 | No downstream = immediate COMPLETED |

## Findings

### Defects

None found.

### Overmocking

None - Tests use real `LandscapeDB.in_memory()` and `LandscapeRecorder`.

### Missing Coverage

1. **No test for timeout-triggered flush behavior**
   - All tests use count triggers (`TriggerConfig(count=N)`)
   - Timeout triggers have different behavior (checked before row processing)
   - Should have at least one test with `TriggerConfig(timeout_seconds=X)`

2. **No test for empty batch output in transform mode**
   - Transform mode allows N->0 (filter all rows)
   - No test verifies behavior when transform returns empty list

3. **No test for mixed-mode DAG**
   - All tests have single aggregation node
   - No coverage for passthrough aggregation followed by transform aggregation

### Tests That Do Nothing

None - All tests have meaningful assertions on outcomes and data.

### Inefficiency

1. **Lines 24-44, 61-106, 290-332, etc. - Heavy boilerplate per test**
   - Each test defines its own transform class with identical schema contract construction
   - Could use factory function: `make_test_transform(name, process_fn)` in conftest.py
   - Estimated 200+ lines could be reduced to ~50 with shared factories

2. **Duplicate `make_source_row()` helper**
   - Lines 24-44 duplicate helper from other test files
   - Should be in `tests/engine/conftest.py` (already has other shared fixtures)

### Structural Issues

1. **Class name mismatch: TestProcessorSingleMode**
   - Lines 868-1144: Class docstring says "'single' mode was removed"
   - But class is named `TestProcessorSingleMode` despite testing transform mode
   - Should be renamed to `TestProcessorTransformModeRegression` or similar

2. **Inconsistent transform class naming**
   - Some use descriptive names: `PassthroughEnricher`, `GroupSplitter`
   - Others use generic: `SumTransform`, `AddMarker`
   - Not a bug, but inconsistent style

### Test Path Integrity

**PASS** - Tests use production components:
- `RowProcessor` constructed with real parameters
- Real `LandscapeRecorder` and `LandscapeDB.in_memory()`
- No manual graph construction - tests processor directly
- Aggregation settings use production `AggregationSettings` dataclass

### Info

1. **Lines 879-889: Excellent historical documentation**
   - Docstring explains why 'single' mode was removed
   - Documents the bug: "triggering token was reused for aggregated output"
   - This is valuable audit trail for architectural decisions

2. **Lines 179-183: Good token identity verification**
   - Explicitly verifies buffered tokens reappear in completed results
   - This is the core invariant of passthrough mode

3. **Lines 582-584: Transform mode token disjointness check**
   - `assert completed_tokens.isdisjoint(consumed_tokens)`
   - Correctly verifies new tokens are created, not reused

## Verdict

**KEEP** - Comprehensive coverage of aggregation output modes with good real-infrastructure testing. Minor issues with boilerplate and class naming don't warrant rejection. The historical documentation in TestProcessorSingleMode is particularly valuable.

## Recommendations

1. Rename `TestProcessorSingleMode` to `TestProcessorTransformModeRegression`
2. Move `make_source_row()` to `tests/engine/conftest.py`
3. Add test for timeout-triggered flush
4. Add test for empty batch output (N->0 transform)
