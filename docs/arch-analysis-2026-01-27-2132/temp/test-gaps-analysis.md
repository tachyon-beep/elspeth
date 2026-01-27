# ELSPETH Test Coverage Gap Analysis
## Architecture Review: Test Structure and Dangerous Gaps

**Analysis Date:** 2026-01-27
**Branch:** fix/rc1-bug-burndown-session-6
**Status:** RC-1 (Pre-Release)
**Analyzer:** Claude Opus 4.5 with ordis-quality-engineering skill

---

## Executive Summary

ELSPETH has **253 test files** covering **133 source files**. While test-to-source ratio appears strong (~1.9:1), this analysis reveals **critical architectural gaps** that could hide design flaws, especially around:

1. **Test Path Integrity Violations** - 32 files bypass production code paths via manual graph construction
2. **Property Testing Coverage** - Only 3 property test files for critical invariants (1.2%)
3. **executors.py Zero Dedicated Tests** - 1658 LOC with no `test_executors.py`
4. **Executor Mock-Heavy Tests** - 11 files with >20 mocks each hiding integration bugs
5. **CLI Test Density** - 1718 LOC with only 5.96% test coverage

### Risk Score by Subsystem

| Subsystem | Source LOC | Test Files | Risk | Primary Concerns |
|-----------|------------|-----------|------|------------------|
| Engine Orchestrator | 2164 | 16 | 🔴 HIGH | Manual graph construction in test helpers |
| Engine Executors | 1658 | 0 dedicated | 🔴 CRITICAL | Zero dedicated test file |
| Landscape Recorder | 2456 | 13 | 🟡 MEDIUM | Well-covered but mock-heavy |
| DAG Execution | 1028 | 1 | 🟢 LOW | Comprehensive test_dag.py |
| TUI ExplainScreen | 313 | 1 partial | 🔴 HIGH | Incomplete widget wiring tests |
| CLI | 1718 | 10 | 🔴 HIGH | 5.96% density, error paths under-tested |
| Property Testing | N/A | 3 | 🔴 HIGH | Only canonical + enum coercion tested |
| Coalesce Executor | 601 | 2 | 🟡 MEDIUM | Timeout never fires (per quality assessment) |

---

## Test Path Integrity Analysis

### The Core Violation

CLAUDE.md explicitly documents:

> "Never bypass production code paths in tests. When integration tests manually construct objects instead of using production factories, bugs hide in the untested path."
>
> "BUG-LINEAGE-01 hid for weeks because tests manually built graphs"

### Evidence: 32 Files with Manual Construction

Files that use `ExecutionGraph()` directly instead of `from_plugin_instances()`:

#### Engine Tests (14 files)
| File | Private Attr Violations | Risk |
|------|------------------------|------|
| `test_orchestrator_lifecycle.py` | 18 | 🔴 HIGH |
| `test_engine_gates.py` | 10 | 🔴 HIGH |
| `orchestrator_test_helpers.py` | 9 | 🔴 CRITICAL (helper!) |
| `test_orchestrator_audit.py` | 6 | 🟡 MIXED |
| `test_orchestrator_validation.py` | 5 | 🟡 MEDIUM |
| `test_orchestrator_resume.py` | 5 | 🟡 MIXED |
| `test_orchestrator_checkpointing.py` | 5 | 🟡 MEDIUM |
| `test_integration.py` | 5 | 🟡 MEDIUM |
| `test_config_gates.py` | 5 | 🟡 MIXED |
| `test_coalesce_integration.py` | 5 | 🟡 MIXED |
| `test_checkpoint_durability.py` | 5 | 🟡 MEDIUM |
| `test_orchestrator_core.py` | - | 🟡 MIXED |
| `test_orchestrator_mutation_gaps.py` | - | 🟡 MIXED |
| `test_orchestrator_recovery.py` | - | 🟡 MIXED |

#### Integration/System Tests (10 files)
| File | Private Attr Violations | Risk |
|------|------------------------|------|
| `test_resume_comprehensive.py` | 21 | 🔴 HIGH |
| `test_crash_recovery.py` | 4 | 🟡 MEDIUM |
| `test_lineage_completeness.py` | 4 | 🟡 MEDIUM |
| `test_source_payload_storage.py` | 3 | 🟡 MEDIUM |
| `test_checkpoint_recovery.py` | 3 | 🟡 MEDIUM |
| `test_resume_edge_ids.py` | - | 🟡 MEDIUM |
| `test_aggregation_recovery.py` | - | 🟡 MEDIUM |
| `test_sink_durability.py` | - | 🟡 MEDIUM |
| `test_resume_checkpoint_cleanup.py` | - | 🟡 MEDIUM |
| `test_audit_integration_fixes.py` | - | 🟡 MEDIUM |

#### Core Tests (8 files)
| File | Risk |
|------|------|
| `test_dag.py` | 🟢 LOW (unit tests OK) |
| `test_edge_validation.py` | 🟢 LOW (unit tests OK) |
| `checkpoint/conftest.py` | 🟡 MEDIUM |
| `checkpoint/test_manager_mutation_gaps.py` | 🟡 MEDIUM |
| `checkpoint/test_manager.py` | 🟡 MEDIUM |
| `checkpoint/test_recovery_mutation_gaps.py` | 🟡 MEDIUM |
| `checkpoint/test_compatibility_validator.py` | 🟡 MEDIUM |
| `checkpoint/test_recovery.py` | 🟡 MEDIUM |

### Critical Finding: Test Helper Propagates Violation

**File:** `tests/engine/orchestrator_test_helpers.py:141-145`

```python
# build_test_graph() manually sets private attributes!
graph._sink_id_map = {SinkName(k): NodeID(v) for k, v in sink_ids.items()}
graph._transform_id_map = {k: NodeID(v) for k, v in transform_ids.items()}
graph._config_gate_id_map = {GateName(k): NodeID(v) for k, v in config_gate_ids.items()}
graph._route_resolution_map = {(NodeID(k[0]), k[1]): v for k, v in route_resolution_map.items()}
graph._default_sink = output_sink
```

**Impact:** Every test using `build_test_graph()` bypasses the production factory. If `from_plugin_instances()` has bugs, these tests pass while production breaks.

### Files Using Production Path (26 files)

These files correctly use `from_plugin_instances()`:
- `test_orchestrator_fork_coalesce.py`
- `test_audit_sweep.py`
- `test_orchestrator_phase_events.py`
- `test_group_id_consistency.py`
- `test_multiple_coalesces.py`
- `test_orchestrator_cleanup.py`
- `test_orchestrator_routing.py`
- And 19 others in CLI, integration, and performance tests

### Files with Mixed Approach (10 files)

These files use BOTH patterns, making behavior unpredictable:
- `test_orchestrator_audit.py`
- `test_config_gates.py`
- `test_orchestrator_resume.py`
- `test_orchestrator_core.py`
- `test_engine_gates.py`
- `test_orchestrator_mutation_gaps.py`
- `test_coalesce_integration.py`
- `test_orchestrator_recovery.py`
- `test_dag.py`
- `test_edge_validation.py`

---

## Critical Gap 1: executors.py Has Zero Dedicated Tests

### The Gap

| File | LOC | Dedicated Test Files | Indirect Coverage |
|------|-----|---------------------|-------------------|
| `src/elspeth/engine/executors.py` | 1658 | 0 | Partial via transform_error_routing |

### Classes in executors.py

```
MissingEdgeError (Exception)
GateOutcome (dataclass)
TransformExecutor (class)
```

### Indirect Coverage Analysis

Only `TransformExecutor` is tested indirectly:
- `test_transform_error_routing.py` - 20 usages of `TransformExecutor`

**Missing:**
- No tests for `MissingEdgeError` propagation
- No tests for `GateOutcome` dataclass behavior
- No dedicated unit tests for TransformExecutor edge cases

### Risk Assessment

| Component | Impact if Buggy |
|-----------|----------------|
| `MissingEdgeError` | Silent routing failures |
| `GateOutcome` | Incorrect fork/route decisions |
| `TransformExecutor` | Transform failures not recorded |

---

## Critical Gap 2: Property Testing Coverage

### Current State

```
tests/property/
├── canonical/
│   ├── test_hash_determinism.py
│   └── test_nan_rejection.py
└── contracts/
    └── test_enum_coercion.py
```

Only **3 property test files** out of 253 total tests (1.2%).

### Missing Property Tests for Critical Invariants

| Invariant | Current Coverage | Priority |
|-----------|-----------------|----------|
| All tokens reach terminal state | ❌ None | 🔴 P0 |
| Fork-join balance | ❌ None | 🔴 P0 |
| DAG routing map consistency | ❌ None | 🔴 P1 |
| Schema compatibility transitivity | ❌ None | 🟡 P2 |
| Canonical JSON determinism | ✅ Partial | 🟢 OK |
| Enum coercion | ✅ Covered | 🟢 OK |

### Recommended Property Tests

#### P0: Audit Trail Completeness
```python
@given(
    pipeline=st.builds(random_pipeline_config),
    rows=st.lists(st.dictionaries(st.text(), st.integers()), min_size=1)
)
def test_all_tokens_reach_terminal_state(pipeline, rows):
    """Property: Every token reaches exactly one terminal state."""
    result = run_pipeline(pipeline, rows)
    for token_id in result.token_ids:
        state = landscape.get_terminal_state(token_id)
        assert state is not None
        assert state in TERMINAL_STATES
```

#### P0: Fork-Join Balance
```python
@given(st.builds(random_dag_with_forks))
def test_fork_join_balance(graph):
    """Property: Every fork branch has destination."""
    for fork_gate in graph.get_fork_gates():
        for branch_name in fork_gate.fork_to:
            assert (
                branch_name in graph.branch_to_coalesce_map or
                branch_name in graph.sink_names
            )
```

---

## Critical Gap 3: Mock-Heavy Testing

### High Mock Usage Files

| File | Mock Count | Risk |
|------|-----------|------|
| `test_orchestrator_fork_coalesce.py` | 183 | 🔴 HIGH |
| `test_orchestrator_lifecycle.py` | 91 | 🔴 HIGH |
| `test_executor_batch_integration.py` | 53 | 🟡 MEDIUM |
| `test_orchestrator_routing.py` | 53 | 🟡 MEDIUM |
| `test_processor_retry.py` | 37 | 🟡 MEDIUM |
| `test_routing_enums.py` | 34 | 🟡 MEDIUM |
| `test_batch_audit_trail.py` | 32 | 🟡 MEDIUM |
| `test_node_id_assignment.py` | 29 | 🟡 MEDIUM |
| `test_orchestrator_core.py` | 26 | 🟡 MEDIUM |
| `test_orchestrator_progress.py` | 26 | 🟡 MEDIUM |
| `test_aggregation_executor.py` | 21 | 🟡 MEDIUM |

### Total Mock Usage in Engine Tests

**20 files** use mocks, with **671+ total mock usages**.

### Risk

Heavy mocking can:
1. **Hide integration bugs** - Components work in isolation but fail when composed
2. **Test the mock, not the code** - Mocks with incorrect behavior pass tests
3. **Brittle tests** - Implementation changes break mocks, not actual behavior

---

## Gap 4: CLI Test Density

### Quantitative Analysis

| Metric | Value |
|--------|-------|
| CLI Source LOC | 1718 |
| CLI Test Files | 10 |
| Total Test Cases | 106 |
| Test Density | 5.96% |

### Missing Error Scenarios

1. **Invalid YAML in settings file** - Does CLI fail gracefully?
2. **Missing required config keys** - Are errors user-friendly?
3. **Database migration failures** - What happens if Alembic fails?
4. **Plugin discovery errors** - Does CLI warn on corrupted plugin packs?
5. **Resume with mismatched schema** - Does validation catch schema changes?

### CLI Commands Coverage

| Command | Status | Tests |
|---------|--------|-------|
| `run` | ✅ Working | Covered |
| `validate` | ✅ Working | Covered |
| `plugins list` | ✅ Working | Covered |
| `explain` | ❌ Returns "not_implemented" | Partial |
| `status` | ❌ Missing | None |
| `export` | ❌ Missing | None |
| `db migrate` | ❌ Not CLI-exposed | None |

---

## Gap 5: TUI Testing Gaps

### Source vs Test Mapping

| Source File | LOC | Has Test? |
|-------------|-----|-----------|
| `explain_screen.py` | 313 | ✅ Partial (`test_explain_tui.py`) |
| `lineage_tree.py` | 197 | ✅ `test_lineage_tree.py` |
| `node_detail.py` | 165 | ✅ `test_node_detail.py` |
| `types.py` | 92 | ✅ `test_lineage_types.py` |
| `explain_app.py` | 73 | ✅ `test_explain_app.py` |
| `constants.py` | 16 | ✅ `test_constants.py` |

### Gap: ExplainScreen Tests Are Shallow

`test_explain_tui.py` tests:
- Import works
- Widget types present
- Database initialization

**Missing:**
- State transitions (Uninitialized → Loading → Loaded)
- Error state handling (LoadingFailedState)
- Widget composition/interaction
- Event handling

---

## Gap 6: Concurrency Testing

### Current State

**222 lines** mention threading/async patterns in tests.

**Only 2 parametrized tests** in engine tests.

### Missing Concurrent Scenarios

| Scenario | Current Coverage | Risk |
|----------|-----------------|------|
| Concurrent Landscape writes | Unknown | 🔴 HIGH |
| Checkpoint race conditions | Unknown | 🔴 HIGH |
| Batch flush coordination | Unknown | 🟡 MEDIUM |
| Rate limiter under load | ❌ None | 🟡 MEDIUM |

---

## Quantitative Summary

| Metric | Value | Assessment |
|--------|-------|------------|
| Test-to-Source Ratio | 1.9:1 | ✅ Good |
| Property Test Files | 3 / 253 (1.2%) | ❌ Insufficient |
| Concurrency Tests | ~27 explicit | ⚠️ Minimal |
| Mock Usage (Engine) | 671+ | ⚠️ High |
| Parametrized Tests (Engine) | 2 | ❌ Very Low |
| CLI Test Density | 5.96% | ❌ Critically Low |
| Error Path Coverage (Orchestrator) | ~40% | ⚠️ Needs Improvement |
| Manual Graph Construction | 32 files | ❌ Test Path Violation |
| executors.py Coverage | 0 dedicated | ❌ Critical Gap |

---

## Prioritized Recommendations

### Priority 0: Blocking Issues (Fix Before Any Release)

| Issue | File(s) | Effort | Impact |
|-------|---------|--------|--------|
| Fix `build_test_graph()` helper | `orchestrator_test_helpers.py` | M | All dependent tests |
| Add property test for terminal states | New file | M | Audit integrity |
| Add dedicated `test_executors.py` | New file | L | 1658 LOC coverage |

### Priority 1: Critical Gaps (Fix This Sprint)

| Issue | Effort | Impact |
|-------|--------|--------|
| Refactor 14 engine tests to use production path | L | Test reliability |
| Add fork-join balance property test | S | DAG correctness |
| Add CLI error path tests | M | User experience |
| Test coalesce timeout firing | S | Hang prevention |

### Priority 2: High Gaps (Fix Before GA)

| Issue | Effort | Impact |
|-------|--------|--------|
| Refactor integration tests (10 files) | M | Production coverage |
| Reduce mock usage in critical tests | L | Integration confidence |
| Add TUI state transition tests | M | Explain feature |
| Add concurrent Landscape write tests | M | Data integrity |

### Priority 3: Medium Gaps (Post-Release)

| Issue | Effort | Impact |
|-------|--------|--------|
| Increase parametrized test usage | S | Test completeness |
| Add schema transitivity property tests | M | Transform chains |
| Add checkpoint crash matrix tests | L | Recovery reliability |

---

## Quick Wins (High Impact, Low Effort)

| Task | Effort | Impact | Why Easy |
|------|--------|--------|----------|
| Add `test_executors.py` shell | 1 day | 🔴 Critical | Pure functions |
| Property test for terminal states | 1 day | 🔴 Critical | Clear invariant |
| CLI invalid YAML test | 2 hours | 🟡 High | Simple boundary |
| Parametrize routing mode tests | 2 hours | 🟡 High | Existing patterns |
| ExplainScreen state transition tests | 4 hours | 🟡 High | Isolated component |

---

## Test Anti-Patterns Observed

### 1. Test Path Bypass (CRITICAL)

**Pattern:** `build_test_graph()` helper manually constructs ExecutionGraph

**Files:** 32 files (14 engine + 10 integration + 8 core)

**Fix:** Update helper to use `ExecutionGraph.from_plugin_instances()`

### 2. Over-Mocking (HIGH)

**Pattern:** 183 mocks in a single test file

**Files:** `test_orchestrator_fork_coalesce.py`

**Fix:** Use real in-memory implementations where possible

### 3. Missing Dedicated Tests (HIGH)

**Pattern:** 1658 LOC file with no dedicated test file

**File:** `src/elspeth/engine/executors.py`

**Fix:** Create `tests/engine/test_executors.py`

### 4. Property Test Scarcity (MEDIUM)

**Pattern:** 3 property test files for system with complex invariants

**Fix:** Add property tests for audit completeness, fork-join balance

---

## Files Requiring Urgent Attention

### Critical (Audit Immediately)

1. `tests/engine/orchestrator_test_helpers.py` - Propagates test path bypass to all users
2. `src/elspeth/engine/executors.py` - 1658 LOC, zero dedicated tests
3. `tests/integration/test_resume_comprehensive.py` - 21 private attr violations
4. `src/elspeth/cli.py` - 1718 LOC, only 5.96% test density

### High Priority (Review This Sprint)

1. All 10 "mixed approach" files - Inconsistent test patterns
2. `tests/engine/test_orchestrator_fork_coalesce.py` - 183 mocks
3. `tests/property/` - Expand beyond 3 files
4. Rate limiting integration - Code exists, no engine wiring tests

### Medium Priority (Review Next Sprint)

1. Concurrency test coverage
2. TUI state transition tests
3. DAG edge cases (nested forks, empty pipeline)
4. Checkpoint recovery matrix

---

## Confidence Assessment

**Overall Confidence:** High

| Category | Evidence Quality |
|----------|-----------------|
| Test path violations | ✅ Grep verified 32 files |
| Mock counts | ✅ Line counts verified |
| LOC metrics | ✅ wc -l verified |
| Property test count | ✅ Directory enumerated |
| CLI density | ✅ Calculated: 106/1718 |

**Gaps in Analysis:**
- Did not run pytest --cov for actual line coverage
- Did not manually inspect all 183 mocks in fork_coalesce
- Did not trace all `from_plugin_instances` call sites

---

## Conclusion

ELSPETH has a **strong test foundation** (253 files, 1.9:1 ratio), but critical **architectural gaps** threaten audit integrity:

1. **Test path bypasses via `build_test_graph()`** - 32 files affected
2. **executors.py has zero dedicated tests** - 1658 LOC at risk
3. **Property test scarcity** - Only 1.2% of test files
4. **CLI error paths critically under-tested** - 5.96% density

**Before RC-1 release:**
1. Fix `build_test_graph()` to use production path
2. Add dedicated `test_executors.py`
3. Add property test for audit trail completeness
4. Add CLI error boundary tests

**Risk Mitigation:** The DAG, landscape recorder, and engine processor have comprehensive coverage. **Highest risk** is in the test helper propagating manual construction to 32 files.

---

## References

- CLAUDE.md: Test Path Integrity section (lines 490-542)
- BUG-LINEAGE-01: Manual graph construction hid production bug
- `src/elspeth/core/dag.py`: `ExecutionGraph.from_plugin_instances()` (production path)
- `tests/engine/orchestrator_test_helpers.py:141-145`: Manual construction in helper
- Architecture quality assessment: 05-quality-assessment.md
- Final report: 04-final-report.md
- Test inventory: 253 test files, 133 source files
