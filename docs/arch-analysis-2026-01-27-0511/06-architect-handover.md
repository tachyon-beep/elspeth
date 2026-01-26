# Architect Handover Document

**Prepared:** 2026-01-27
**Purpose:** Enable systematic improvement planning based on architecture analysis

---

## Overview

This document provides actionable guidance for architects planning improvements to ELSPETH. It synthesizes findings from the architecture analysis into prioritized improvement opportunities with implementation guidance.

---

## Improvement Roadmap

### Phase 1: RC-1 Stabilization (Immediate)

| ID | Improvement | Priority | Effort | Risk |
|----|-------------|----------|--------|------|
| S1 | Add coalesce timeout/deadlock detection | Critical | Medium | Medium |
| S2 | Document all RC-1 known limitations | Critical | Low | Low |
| S3 | Complete TUI or mark as "Preview" | High | High | Low |
| S4 | Add missing coalesce edge case tests | High | Medium | Low |

### Phase 2: Post-RC-1 Maintainability (1-2 months)

| ID | Improvement | Priority | Effort | Risk |
|----|-------------|----------|--------|------|
| M1 | Split orchestrator.py into modules | High | Medium | Medium |
| M2 | Split dag.py validation logic | High | Medium | Medium |
| M3 | Split config.py settings models | Medium | Medium | Low |
| M4 | Extract processor phases | Medium | High | Medium |
| M5 | Generate API reference docs | Low | Low | Low |

### Phase 3: Future Enhancements (3-6 months)

| ID | Improvement | Priority | Effort | Risk |
|----|-------------|----------|--------|------|
| F1 | Parallel row processing | Medium | High | High |
| F2 | Performance benchmarking suite | Medium | Medium | Low |
| F3 | Enhanced error context messages | Low | Low | Low |
| F4 | Plugin sandboxing (user plugins) | Low | High | Medium |

---

## Detailed Improvement Specifications

### S1: Coalesce Timeout/Deadlock Detection

**Problem:** If a fork gate produces branches ["A", "B"] but a downstream gate only routes to "A", branch "B" never arrives at coalesce. Token waits forever.

**Current Behavior:**
- `coalesce_executor.py` holds tokens until all expected branches arrive
- No timeout mechanism
- `flush_pending()` is manual, caller must invoke

**Proposed Solution:**

```python
# coalesce_executor.py
class CoalesceExecutor:
    def __init__(self, ..., deadlock_timeout_seconds: float = 300.0):
        self._deadlock_timeout = deadlock_timeout_seconds
        self._pending_timestamps: dict[str, float] = {}

    def accept(self, token: TokenInfo, ...) -> CoalesceOutcome:
        coalesce_key = self._get_coalesce_key(token)

        # Record first arrival time
        if coalesce_key not in self._pending_timestamps:
            self._pending_timestamps[coalesce_key] = time.monotonic()

        # Check for deadlock
        elapsed = time.monotonic() - self._pending_timestamps[coalesce_key]
        if elapsed > self._deadlock_timeout:
            return CoalesceOutcome(
                held=False,
                merged_token=None,
                failure_reason=f"Deadlock timeout after {elapsed:.1f}s waiting for branches",
                missing_branches=self._get_missing_branches(coalesce_key)
            )

        # ... existing logic
```

**Acceptance Criteria:**
- [ ] Configurable timeout per coalesce node
- [ ] Clear error message with missing branch names
- [ ] Audit trail records timeout event
- [ ] Test coverage for timeout scenario

**Estimated Effort:** 2-3 days

---

### M1: Split orchestrator.py

**Problem:** 92KB, 2058 lines - too large for effective maintenance.

**Current Structure:**
```
orchestrator.py
├── Orchestrator class (~1500 lines)
│   ├── run() - main entry
│   ├── _load_source() - source handling
│   ├── _process_rows() - main processing loop
│   ├── _write_sinks() - sink output
│   ├── _handle_progress() - progress events
│   └── _validate_routes() - route validation
└── Supporting functions (~500 lines)
```

**Proposed Structure:**
```
engine/
├── orchestrator.py (~300 lines)
│   └── Orchestrator - coordinates modules
├── orchestrator_source.py (~200 lines)
│   └── SourceLoader - source loading logic
├── orchestrator_processing.py (~400 lines)
│   └── ProcessingLoop - main row processing
├── orchestrator_sinks.py (~200 lines)
│   └── SinkWriter - sink output logic
├── orchestrator_progress.py (~150 lines)
│   └── ProgressManager - events and progress
└── orchestrator_validation.py (~200 lines)
    └── RouteValidator - route validation
```

**Migration Strategy:**
1. Create new modules with extracted classes
2. Orchestrator delegates to new modules
3. Add deprecation warnings for direct access
4. Remove deprecated access in next release

**Acceptance Criteria:**
- [ ] Each module < 400 lines
- [ ] No circular imports
- [ ] All tests pass
- [ ] No public API changes

**Estimated Effort:** 3-5 days

---

### M2: Split dag.py Validation

**Problem:** 38KB single file with mixed concerns.

**Current Structure:**
```
dag.py
├── ExecutionGraph class
├── from_plugin_instances() - factory with embedded validation
├── validate() - structural validation
├── validate_edge_compatibility() - schema validation
├── ID mapping methods (6+)
└── Helper functions
```

**Proposed Structure:**
```
core/
├── dag/
│   ├── __init__.py - re-exports
│   ├── graph.py (~400 lines)
│   │   └── ExecutionGraph - core graph operations
│   ├── factory.py (~300 lines)
│   │   └── from_plugin_instances() - graph construction
│   ├── validation.py (~200 lines)
│   │   └── GraphValidator - structural + schema validation
│   ├── id_mapping.py (~150 lines)
│   │   └── ID mapping methods
│   └── errors.py (~50 lines)
│       └── GraphValidationError, etc.
```

**Acceptance Criteria:**
- [ ] Clear separation of concerns
- [ ] No circular imports
- [ ] Public API unchanged
- [ ] All tests pass

**Estimated Effort:** 2-3 days

---

### M4: Extract Processor Phases

**Problem:** `_process_single_token()` is 390 lines handling multiple concerns.

**Current Structure:**
```python
def _process_single_token(self, token, start_step, ...):
    # Lines 661-868: Transform execution
    # Lines 872-951: Gate handling
    # Lines 953-1001: Coalesce handling
    # Lines 1003-1048: Result composition
```

**Proposed Structure:**
```python
def _process_single_token(self, token, start_step, ...):
    # Orchestrate phases
    token = self._execute_transforms_phase(token, start_step, ...)
    if token.needs_gate_evaluation:
        gate_result = self._execute_gate_phase(token, ...)
        if gate_result.is_fork:
            return self._handle_fork(gate_result)
    if token.at_coalesce:
        return self._execute_coalesce_phase(token, ...)
    return self._compose_result(token)

def _execute_transforms_phase(self, token, start_step, ...) -> TokenState:
    """Execute transforms from start_step to next gate/coalesce."""
    ...

def _execute_gate_phase(self, token, ...) -> GatePhaseResult:
    """Evaluate gate condition and determine routing."""
    ...

def _execute_coalesce_phase(self, token, ...) -> CoalescePhaseResult:
    """Handle coalesce barrier."""
    ...
```

**Acceptance Criteria:**
- [ ] Each phase method < 100 lines
- [ ] Clear data contracts between phases
- [ ] No behavior changes
- [ ] All tests pass

**Estimated Effort:** 3-5 days

---

### F1: Parallel Row Processing

**Problem:** Single-threaded execution limits throughput.

**Current Architecture:**
```
Orchestrator
    └── for row in source:
            processor.process_row(row)  # Sequential
```

**Proposed Architecture:**
```
Orchestrator
    └── ThreadPoolExecutor(max_workers=N)
            └── processor.process_row(row)  # Parallel within limits
```

**Considerations:**
1. **Audit Ordering:** Row recording must maintain source order
2. **Aggregation State:** Shared state needs synchronization
3. **Coalesce Barriers:** Cross-row coordination
4. **Token ID Generation:** Must be thread-safe
5. **Database Writes:** Connection pooling needed

**Implementation Approach:**
1. Introduce `ProcessingMode.PARALLEL` configuration
2. Add thread-safe ID generation
3. Add result ordering buffer (similar to batching)
4. Add connection pooling for Landscape
5. Synchronize aggregation buffers

**Acceptance Criteria:**
- [ ] Configurable parallelism level
- [ ] Audit trail maintains source order
- [ ] Aggregation correctness preserved
- [ ] Performance improvement measurable
- [ ] Fallback to sequential on error

**Estimated Effort:** 2-3 weeks

**Risk:** High - cross-cutting change affecting multiple subsystems

---

## Architecture Decision Records (ADRs) Needed

### ADR-001: Large File Decomposition Strategy

**Context:** Several files exceed maintainability thresholds.

**Decision:** [To be decided]

**Options:**
1. Extract to sibling modules (current namespace)
2. Create sub-packages (new namespace hierarchy)
3. Functional decomposition (by operation type)
4. Domain decomposition (by entity type)

### ADR-002: TUI Implementation Strategy

**Context:** TUI is placeholder, needs decision on scope.

**Decision:** [To be decided]

**Options:**
1. Full implementation with lineage exploration
2. Minimal implementation with basic queries
3. Mark as "Preview" and defer to post-1.0
4. Remove TUI, CLI-only interface

### ADR-003: Parallel Processing Architecture

**Context:** Single-threaded limits throughput for large pipelines.

**Decision:** [To be decided]

**Options:**
1. Thread-based parallelism within process
2. Process-based parallelism with multiprocessing
3. Async/await with asyncio
4. External parallelism via orchestration (Airflow, etc.)

---

## Technical Debt Tracking

### Debt Items by Subsystem

| Subsystem | Item | Impact | Effort | Interest |
|-----------|------|--------|--------|----------|
| Engine | orchestrator.py size | Maintainability | Medium | Accumulating |
| Core | dag.py size | Maintainability | Medium | Stable |
| Core | config.py size | Maintainability | Medium | Stable |
| Engine | _process_single_token complexity | Maintainability | High | Accumulating |
| TUI | Placeholder implementation | Feature gap | High | Stable |
| Engine | Coalesce deadlock potential | Reliability | Medium | Critical |

### Debt Interest Rates

- **Accumulating:** Gets worse as features are added
- **Stable:** Constant cost, not getting worse
- **Critical:** Potential production impact

---

## Refactoring Patterns

### Pattern 1: Module Extraction

```python
# Before: Large orchestrator.py
class Orchestrator:
    def _load_source(self, ...): ...
    def _process_rows(self, ...): ...

# After: Extracted modules
# orchestrator_source.py
class SourceLoader:
    def load(self, source: SourceProtocol, ctx: PluginContext) -> Iterator[SourceRow]: ...

# orchestrator.py
from .orchestrator_source import SourceLoader

class Orchestrator:
    def __init__(self, ...):
        self._source_loader = SourceLoader(...)

    def run(self, ...):
        rows = self._source_loader.load(source, ctx)
```

### Pattern 2: Phase Extraction

```python
# Before: Monolithic method
def _process_single_token(self, token, ...):
    # 390 lines of mixed concerns

# After: Phase methods
def _process_single_token(self, token, ...):
    state = self._run_transform_phase(token, ...)
    if state.at_gate:
        state = self._run_gate_phase(state, ...)
    if state.at_coalesce:
        state = self._run_coalesce_phase(state, ...)
    return self._finalize(state)
```

### Pattern 3: Configuration Extraction

```python
# Before: All in config.py
class GateSettings(BaseModel): ...
class SinkSettings(BaseModel): ...
class ElspethSettings(BaseModel): ...

# After: Split by domain
# config/gates.py
class GateSettings(BaseModel): ...

# config/sinks.py
class SinkSettings(BaseModel): ...

# config/settings.py
from .gates import GateSettings
from .sinks import SinkSettings

class ElspethSettings(BaseModel):
    gates: list[GateSettings]
    sinks: dict[str, SinkSettings]
```

---

## Testing Strategy for Improvements

### Unit Test Requirements

Each improvement must include:
1. **Behavior preservation tests** - Old behavior unchanged
2. **New behavior tests** - New functionality covered
3. **Error case tests** - Edge cases and errors
4. **Performance tests** - No regression (where applicable)

### Integration Test Requirements

1. Full pipeline execution with improvement active
2. Checkpoint/resume with improvement active
3. Multi-sink routing with improvement active

### Property Test Requirements

For structural changes (dag, processor):
1. Invariants preserved across all inputs
2. Determinism maintained
3. Token lineage correctness

---

## Risk Assessment

### High Risk Improvements

| Improvement | Risk | Mitigation |
|-------------|------|------------|
| Parallel Processing | State corruption, ordering | Feature flag, extensive testing |
| Processor Extraction | Behavior changes | High test coverage, incremental |

### Medium Risk Improvements

| Improvement | Risk | Mitigation |
|-------------|------|------------|
| Orchestrator Split | Import cycles | Careful interface design |
| DAG Split | API surface change | Maintain public API |

### Low Risk Improvements

| Improvement | Risk | Mitigation |
|-------------|------|------------|
| Config Split | None significant | Standard refactoring |
| Documentation | None | Review process |

---

## Success Metrics

### Maintainability

- All files < 500 lines (except data files)
- No function > 100 lines
- Cyclomatic complexity < 15 per function

### Performance

- No regression from refactoring
- Parallel processing: 2x+ throughput improvement

### Quality

- Test coverage maintained or improved
- No new technical debt introduced
- Documentation updated with changes

---

## Appendix: File Inventory for Refactoring

### Priority 1 (> 1000 lines)

| File | Lines | Action |
|------|-------|--------|
| orchestrator.py | 2058 | Split to 5+ modules |
| recorder.py | ~2400 | Split by entity type |
| executors.py | 1654 | Extract individual executors |
| processor.py | 1048 | Extract phases |

### Priority 2 (500-1000 lines)

| File | Lines | Action |
|------|-------|--------|
| dag.py | ~1000 | Split to sub-package |
| config.py | ~1200 | Split settings models |
| azure_batch.py | ~800 | Review for extraction |

### Priority 3 (Complexity Hotspots)

| Function | Location | Action |
|----------|----------|--------|
| _process_single_token | processor.py | Extract phases |
| from_plugin_instances | dag.py | Extract helpers |
| validate_routes | config.py | Extract to validator |

---

## Conclusion

This handover document provides a structured approach to improving ELSPETH's architecture. The improvements are prioritized by:

1. **Immediate:** RC-1 stabilization (critical reliability)
2. **Short-term:** Maintainability improvements (reduce complexity)
3. **Long-term:** Performance enhancements (parallel processing)

Each improvement includes clear specifications, acceptance criteria, and risk assessment to enable informed decision-making and successful implementation.
