# Test Audit: test_orchestrator_payload_store.py

## Metadata
- **File:** `/home/john/elspeth-rapid/tests/engine/test_orchestrator_payload_store.py`
- **Lines:** 387
- **Tests:** 5 test methods across 2 test classes
- **Audit:** PASS

## Summary

This test file provides comprehensive acceptance tests for the mandatory `payload_store` requirement in `orchestrator.run()`. Tests verify audit compliance requirements - that payload storage is mandatory, happens before source loading, and correctly populates `source_data_ref` in the audit trail. All tests use the production graph construction path via `build_production_graph()`.

## Test Classes and Coverage

| Class | Tests | Purpose |
|-------|-------|---------|
| `TestOrchestratorPayloadStoreRequirement` | 4 | Verify payload_store is mandatory and correctly wired |
| `TestOrchestratorPayloadStoreIntegration` | 1 | Verify payload storage with transforms in pipeline |

## Findings

### Positive Findings

1. **Production Code Path Usage (Lines 94, 165, 239, 366)**: All tests use `build_production_graph(config)` helper which wraps `ExecutionGraph.from_plugin_instances()`. This ensures tests exercise the same graph construction code as production.

2. **Critical Audit Compliance Test (Lines 39-101)**: `test_run_raises_without_payload_store` verifies:
   - ValueError raised when `payload_store=None`
   - Error raised BEFORE source loading (verified via `load_called` flag)
   - This is essential for audit integrity - no rows should be created without payload storage

3. **Audit Trail Verification (Lines 174-184, 378-387)**: Tests query `LandscapeRecorder.get_rows()` to verify `source_data_ref` is populated - proper integration testing of audit compliance.

4. **Parameter Wiring Test (Lines 186-253)**: `test_execute_run_receives_payload_store` uses a spy to verify the `payload_store` parameter is correctly passed through to `_execute_run`. This catches "orphaned parameter" bugs explicitly.

5. **Clear Error Messages in Assertions**: Assertions include helpful messages that reference CLAUDE.md requirements (Lines 182-184, 384-386).

6. **Proper Fixture Usage**: Tests use the `payload_store` fixture from conftest.py which provides `MockPayloadStore` instances with proper isolation.

### Acceptable Patterns

1. **Inline Test Classes (Lines 47-81, 68-81, etc.)**: The test file defines minimal source/sink/transform classes inline. While verbose, this is acceptable for clarity - each test's requirements are self-contained and explicit.

2. **Spy Pattern (Lines 242-253)**: Using `Mock(wraps=original)` as a spy to verify parameter passing is appropriate here since we need to verify internal wiring without changing behavior.

### Minor Issues

1. **Repeated Test Class Definitions**: `MinimalSource`, `MinimalSink`, `ListSource`, `PassthroughSink`, `CollectSink` are defined multiple times across tests. Consider extracting to module-level fixtures for DRYness.

2. **Fixture Isolation Test (Lines 255-277)**: `test_payload_store_fixture_isolation` only verifies that stored content exists after storing it - it doesn't verify isolation from OTHER tests. However, the fixture documentation and pytest's function-scoped default provides this guarantee implicitly.

## Test Quality Assessment

| Criterion | Assessment |
|-----------|------------|
| Defects | None found |
| Overmocking | Minimal - spy used appropriately for parameter verification |
| Missing Coverage | Adequate for payload_store requirements |
| Tests That Do Nothing | None - all tests verify meaningful behavior |
| Inefficiency | Minor - repeated inline class definitions |
| Structural Issues | None |

## Specific Test Analysis

### test_run_raises_without_payload_store
- **Lines:** 39-101
- **Verdict:** Excellent - Verifies critical audit invariant with temporal ordering check

### test_run_with_payload_store_populates_source_data_ref
- **Lines:** 103-184
- **Verdict:** Excellent - Full integration test with audit trail verification

### test_execute_run_receives_payload_store
- **Lines:** 186-253
- **Verdict:** Good - Parameter wiring verification, appropriate use of spy

### test_payload_store_fixture_isolation
- **Lines:** 255-277
- **Verdict:** Good - Tests fixture contract, though isolation is implicitly guaranteed by pytest

### test_run_with_transform_populates_source_data_ref
- **Lines:** 283-387
- **Verdict:** Excellent - Verifies payload storage happens before transform processing

## Verdict

**PASS** - High-quality acceptance tests for a critical audit compliance feature. Tests use production code paths, verify audit trail integrity, and include appropriate temporal checks. The tests would catch regressions in payload store requirement enforcement and audit trail population.
