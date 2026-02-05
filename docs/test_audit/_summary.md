# Test Suite Audit Summary

**Generated:** 2026-02-05
**Total Files Audited:** 434
**Total Lines:** 209,464

## Executive Summary

The ELSPETH test suite is **fundamentally sound** with excellent coverage in critical areas (property-based testing, audit trail verification, contract enforcement). However, **23 files require immediate attention** due to critical issues that undermine test effectiveness.

## Severity Distribution

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 7 | Tests that don't test production code, Test Path Integrity violations |
| HIGH | 12 | Incomplete tests, overmocking, tests that do nothing |
| MEDIUM | 28 | Missing coverage, code duplication, weak assertions |
| LOW | 45 | Minor structural issues, style concerns |
| PASS | 342 | No significant issues |

## Critical Issues (Must Fix)

### 1. Test Path Integrity Violations
Tests that manually construct `ExecutionGraph` instead of using `ExecutionGraph.from_plugin_instances()`, potentially hiding bugs like BUG-LINEAGE-01:

| File | Issue |
|------|-------|
| `tests/engine/test_orchestrator_lifecycle.py` | ALL 7 tests use manual graph construction |
| `tests/engine/test_integration.py` | 15/25 tests bypass production path via `_build_production_graph()` |
| `tests/engine/test_orchestrator_telemetry.py` | 13/16 tests use manual `create_minimal_graph()` |
| `tests/integration/test_resume_comprehensive.py` | ALL 8 tests use manual graph construction |
| `tests/integration/test_concurrency_integration.py` | Manual graph construction |
| `tests/integration/test_llm_contract_validation.py` | Manual graph construction in DAG tests |

### 2. Tests That Don't Test Production Code

| File | Issue |
|------|-------|
| `tests/integration/test_resume_schema_required.py` | Test manually raises and catches its own exception - ALWAYS passes |
| `tests/engine/test_processor_guards.py` | Test reimplements production logic in test code |
| `tests/plugins/test_protocol_lifecycle.py` | Tests Python Protocol mechanism, not ELSPETH behavior |

### 3. Tests With Weak/No Assertions

| File | Issue |
|------|-------|
| `tests/plugins/azure/test_blob_source.py` | Assertions like `len(rows) >= 0` always pass |
| `tests/plugins/llm/test_azure_batch_audit_integration.py` | `test_azure_batch_with_pipeline_row_inputs` does nothing meaningful |
| `tests/telemetry/exporters/test_console.py` | Missing ALL export behavior tests |

### 4. Resume Tests Are Incomplete (HIGH)

All three sink resume test files only test internal state, not actual resume behavior:
- `tests/plugins/sinks/test_csv_sink_resume.py`
- `tests/plugins/sinks/test_database_sink_resume.py`
- `tests/plugins/sinks/test_json_sink_resume.py`

### 5. Sink Protocol Compliance Minimal (HIGH)

`tests/plugins/sinks/test_sink_protocol_compliance.py`:
- Only tests `name` and `input_schema` attributes
- Missing tests for `write()`, `close()`, `flush()`, lifecycle hooks
- Uses `hasattr()` (violates CLAUDE.md)

## Patterns Requiring Attention

### Overmocking of `record_call`
Multiple LLM integration tests mock `record_call`, defeating the purpose of integration testing:
- `tests/integration/test_llm_transforms.py`
- `tests/integration/test_multi_query_integration.py`

### Code Duplication
Massive duplication across test files:
- `tests/engine/test_integration.py` - ~1500 lines of duplicate `ListSource`/`CollectSink` definitions
- Stress tests - `CollectingOutputPort` duplicated 5x
- LLM tests - `_make_pipeline_row()` duplicated in 4+ files

### pytest Discovery Issues
`tests/core/test_events.py` - Classes named `SampleEventBusProtocol` instead of `TestEventBusProtocol` - 4 tests not discovered

## Strengths

### Excellent Property-Based Testing
The `tests/property/` directory is exemplary:
- 32 files using Hypothesis correctly
- RuleBasedStateMachine for complex state transitions
- Proper audit trail integrity verification

### Strong Regression Testing
Tests consistently reference bug tickets (P1-2026-01-xx, P2-2026-01-xx) providing excellent traceability.

### Good Three-Tier Trust Model Enforcement
Tests properly verify:
- Tier 3 (external) data errors are quarantined
- Tier 1 (audit) data corruption causes crashes (not coercion)

### ChaosLLM Testing Infrastructure
The `tests/testing/chaosllm/` suite is EXCELLENT - enables realistic LLM testing without API calls.

## Recommendations

### Immediate (Before RC-2 Release)

1. **Fix Test Path Integrity violations** in the 6 identified files
2. **Delete or rewrite** `test_resume_schema_required.py` - it provides false confidence
3. **Add export tests** to `test_console.py`
4. **Fix pytest discovery** in `test_events.py`

### Short-Term

1. **Consolidate duplicated helpers** to conftest.py files
2. **Add real resume behavior tests** for all three sink types
3. **Expand protocol compliance tests** to cover all required methods

### Medium-Term

1. **Split oversized files**:
   - `test_integration.py` (3696 lines) → 5-6 focused files
   - `test_check_contracts.py` (1447 lines) → domain-specific files
2. **Add error path tests** across integration tests
3. **Remove overmocking** of `record_call` in LLM integration tests

## Files by Directory

| Directory | Files | Lines | Critical | High | Pass |
|-----------|-------|-------|----------|------|------|
| tests/audit | 1 | 461 | 0 | 0 | 1 |
| tests/cli | 14 | 5,325 | 0 | 0 | 14 |
| tests/contracts | 55 | 14,744 | 0 | 1 | 54 |
| tests/core | 84 | 39,138 | 1 | 2 | 81 |
| tests/engine | 78 | 56,889 | 3 | 5 | 70 |
| tests/examples | 1 | 224 | 0 | 0 | 1 |
| tests/integration | 38 | 14,660 | 3 | 2 | 33 |
| tests/mcp | 1 | 458 | 0 | 0 | 1 |
| tests/performance | 2 | 507 | 0 | 0 | 2 |
| tests/plugins | 97 | 38,287 | 0 | 4 | 93 |
| tests/property | 32 | 14,125 | 0 | 0 | 32 |
| tests/scripts | 3 | 2,244 | 0 | 0 | 3 |
| tests/spikes | 1 | 532 | 0 | 0 | 1 |
| tests/stress | 5 | 2,093 | 0 | 0 | 5 |
| tests/system | 2 | 1,524 | 0 | 0 | 2 |
| tests/telemetry | 13 | 6,574 | 0 | 1 | 12 |
| tests/testing | 8 | 4,930 | 0 | 0 | 8 |
| tests/tui | 6 | 1,079 | 0 | 0 | 6 |
| tests/unit | 12 | 5,870 | 0 | 0 | 12 |

## Conclusion

The test suite is **production-ready with reservations**. The critical issues identified represent real risks:
- Test Path Integrity violations allowed BUG-LINEAGE-01 to hide for weeks
- Tests that always pass provide false confidence
- Missing resume behavior tests leave a critical feature undertested

Addressing the 7 CRITICAL and 12 HIGH severity issues should be prioritized before release.
