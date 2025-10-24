# Execution Plan: Suite Runner Refactoring

**Target:** `src/elspeth/core/experiments/suite_runner.py::run()`
**Current Complexity:** 69
**Target Complexity:** ≤15
**Strategy:** Systematic extraction using Template Method pattern (proven with runner.py refactoring)

---

## Executive Summary

Following the successful refactoring of `runner.py::run()` (complexity 73→11, 85% reduction), we now tackle the second-highest complexity function in the codebase: `suite_runner.py::run()` at complexity 69.

This method orchestrates the execution of multiple experiments in a suite, managing:
- Sink resolution across 4 configuration layers
- Middleware lifecycle hooks with deduplication tracking
- Baseline experiment comparison with dynamic plugin loading
- Experiment context propagation

**Key Success Factors from runner.py refactoring:**
1. ✅ Characterization tests before any changes
2. ✅ Incremental extraction with continuous testing
3. ✅ Dataclasses for complex state management
4. ✅ Clear helper method naming reveals intent
5. ✅ Security-first design (fail-closed validation)

---

## Baseline Metrics

**File:** `src/elspeth/core/experiments/suite_runner.py`
- **Total Lines:** 419
- **run() Method Lines:** 138 (lines 281-419)
- **Cognitive Complexity:** 69 (CRITICAL)
- **Test Coverage:** 85%
- **Related Tests:** 10 integration tests

**Complexity Breakdown:**
```
run() method (138 lines, complexity 69):
├── Setup (23 lines, complexity ~5)
│   ├── Initialize defaults and results
│   ├── Build experiments list (baseline first)
│   ├── Create suite_metadata
│   └── Setup notified_middlewares tracking
│
├── Main Loop (88 lines, complexity ~55) ← PRIMARY HOTSPOT
│   ├── Sink resolution (4-level conditionals, ~12)
│   ├── Context creation and propagation (~5)
│   ├── Middleware lifecycle management (~15)
│   │   ├── on_suite_loaded (deduplicated)
│   │   ├── on_experiment_start
│   │   └── on_experiment_complete
│   ├── Experiment execution (~2)
│   ├── Baseline tracking (~3)
│   └── Baseline comparison (18 lines, ~18)
│       ├── Plugin definition merging (3 layers)
│       ├── Plugin instantiation loop
│       ├── Comparison execution
│       └── Middleware on_baseline_comparison
│
└── Cleanup (5 lines, complexity ~2)
    └── Middleware on_suite_complete
```

**Key Characteristics:**
1. **Sink Resolution Complexity:** 4-level nested conditionals (experiment → pack → defaults → factory)
2. **State Tracking:** `notified_middlewares` dict prevents duplicate hooks
3. **Nested Loops:** Experiments × middlewares × (suite_loaded + start + complete + comparison)
4. **Configuration Merging:** Baseline plugin definitions from 3 sources
5. **Conditional Logic:** Multiple `hasattr()` checks for middleware capabilities

---

## Complexity Drivers (SonarQube S3776)

### 1. Sink Resolution Logic (Lines 329-336)
```python
if experiment.sink_defs:
    sinks = self._instantiate_sinks(experiment.sink_defs)
elif pack and pack.get("sinks"):
    sinks = self._instantiate_sinks(pack["sinks"])
elif defaults.get("sink_defs"):
    sinks = self._instantiate_sinks(defaults["sink_defs"])
else:
    sinks = sink_factory(experiment) if sink_factory else self.sinks
```
**Complexity:** +4 (nested conditionals)

### 2. Middleware Lifecycle Hooks (Lines 358-374)
```python
middlewares = runner.llm_middlewares or []
suite_notified = []
for mw in middlewares:
    key = id(mw)
    if hasattr(mw, "on_suite_loaded") and key not in notified_middlewares:
        mw.on_suite_loaded(suite_metadata, preflight_info)
        notified_middlewares[key] = mw
        suite_notified.append(mw)
    if hasattr(mw, "on_experiment_start"):
        mw.on_experiment_start(experiment.name, {...})
```
**Complexity:** +8 (nested loops + conditionals + state tracking)

### 3. Baseline Comparison Logic (Lines 396-413)
```python
if baseline_payload and experiment != self.suite.baseline:
    comp_defs = list(defaults.get("baseline_plugin_defs", []))
    if pack and pack.get("baseline_plugins"):
        comp_defs = list(pack.get("baseline_plugins", [])) + comp_defs
    if experiment.baseline_plugin_defs:
        comp_defs += experiment.baseline_plugin_defs
    comparisons = {}
    for defn in comp_defs:
        plugin = create_baseline_plugin(defn, parent_context=experiment_context)
        diff = plugin.compare(baseline_payload, payload)
        if diff:
            comparisons[plugin.name] = diff
    if comparisons:
        payload["baseline_comparison"] = comparisons
        results[experiment.name]["baseline_comparison"] = comparisons
        for mw in middlewares:
            if hasattr(mw, "on_baseline_comparison"):
                mw.on_baseline_comparison(experiment.name, comparisons)
```
**Complexity:** +18 (deeply nested loops, conditionals, plugin creation)

---

## Refactoring Strategy

**Pattern:** Template Method (proven in runner.py refactoring)

**Approach:** Extract the run() method into a clean orchestration template that calls well-named helper methods for each responsibility.

**Target Structure:**
```python
def run(self, df, defaults=None, sink_factory=None, preflight_info=None):
    """Execute all experiments in suite (orchestration template)."""
    # Phase 1: Setup
    context = self._prepare_suite_context(defaults, preflight_info)

    # Phase 2: Execute experiments
    for experiment in context.experiments:
        experiment_result = self._run_single_experiment(
            experiment, df, context, sink_factory
        )
        context.results[experiment.name] = experiment_result

    # Phase 3: Cleanup
    self._finalize_suite(context)

    return context.results
```

---

## Phase 0: Safety Net Construction

**Goal:** Create comprehensive characterization tests documenting current behavior.

**Tasks:**
1. Create `tests/test_suite_runner_characterization.py`
2. Document behavioral invariants:
   - Suite result structure (all experiments present)
   - Baseline identification and tracking
   - Middleware hook ordering and deduplication
   - Sink resolution priority (experiment > pack > defaults > factory)
   - Context propagation to sinks
   - Baseline comparison plugin execution
3. Capture baseline metrics:
   - Test count
   - Coverage percentage
   - Line counts

**Success Criteria:**
- ✅ 6+ characterization tests passing
- ✅ All existing tests still passing
- ✅ Behavioral invariants documented

**Estimated Effort:** 2-3 hours

---

## Phase 1: Supporting Classes

**Goal:** Create dataclasses to manage complex state and configuration.

### 1.1 SuiteExecutionContext (Dataclass)
**Purpose:** Manage suite-level execution state
```python
@dataclass
class SuiteExecutionContext:
    """Encapsulates suite execution state."""
    defaults: dict[str, Any]
    prompt_packs: dict[str, Any]
    experiments: list[ExperimentConfig]
    baseline_payload: dict[str, Any] | None
    results: dict[str, Any]
    preflight_info: dict[str, Any]
    notified_middlewares: dict[int, Any]

    @classmethod
    def create(cls, suite, defaults, preflight_info):
        """Factory method for initialization."""
        ...
```

**Benefits:**
- Eliminates local variables scattered across run()
- Clear ownership of suite-level state
- Easy to pass to helper methods
- Type-safe attribute access

### 1.2 ExperimentExecutionConfig (Dataclass)
**Purpose:** Encapsulate experiment execution configuration
```python
@dataclass
class ExperimentExecutionConfig:
    """Configuration for a single experiment execution."""
    experiment: ExperimentConfig
    pack: dict[str, Any] | None
    sinks: list[ResultSink]
    runner: ExperimentRunner
    context: PluginContext
    middlewares: list[Any]
```

**Benefits:**
- Groups related configuration together
- Reduces parameter passing
- Clear separation of concerns

**Estimated Effort:** 1 hour

---

## Phase 2: Simple Helper Extractions

**Goal:** Extract simple, focused helper methods with clear responsibilities.

### 2.1 _prepare_suite_context()
**Signature:** `(self, defaults, preflight_info) -> SuiteExecutionContext`

**Extracts:** Lines 299-323 (setup phase)
- Initialize defaults
- Build experiments list (baseline first)
- Create suite_metadata
- Setup preflight_info
- Initialize notified_middlewares tracking

**Complexity Reduction:** ~5 → ~2 per extracted method

### 2.2 _resolve_experiment_sinks()
**Signature:** `(self, experiment, pack, defaults, sink_factory) -> list[ResultSink]`

**Extracts:** Lines 329-336 (4-level sink resolution)
```python
def _resolve_experiment_sinks(
    self,
    experiment: ExperimentConfig,
    pack: dict[str, Any] | None,
    defaults: dict[str, Any],
    sink_factory: Callable | None,
) -> list[ResultSink]:
    """Resolve sinks from experiment, pack, defaults, or factory (priority order)."""
    if experiment.sink_defs:
        return self._instantiate_sinks(experiment.sink_defs)

    if pack and pack.get("sinks"):
        return self._instantiate_sinks(pack["sinks"])

    if defaults.get("sink_defs"):
        return self._instantiate_sinks(defaults["sink_defs"])

    return sink_factory(experiment) if sink_factory else self.sinks
```

**Complexity Reduction:** 4-level nesting → Early returns (complexity ~6 → ~2)

### 2.3 _get_experiment_context()
**Signature:** `(self, runner) -> PluginContext`

**Extracts:** Lines 343-357 (context retrieval with fallback)

**Complexity Reduction:** ~5 → ~2

### 2.4 _finalize_suite()
**Signature:** `(self, context: SuiteExecutionContext) -> None`

**Extracts:** Lines 415-417 (cleanup phase)
```python
def _finalize_suite(self, context: SuiteExecutionContext) -> None:
    """Notify all middlewares that suite execution is complete."""
    for mw in context.notified_middlewares.values():
        if hasattr(mw, "on_suite_complete"):
            mw.on_suite_complete()
```

**Complexity Reduction:** ~2 → ~1

**Estimated Effort:** 2-3 hours

---

## Phase 3: Complex Method Extractions

**Goal:** Extract complex orchestration logic into focused methods.

### 3.1 _notify_middleware_suite_loaded()
**Signature:** `(self, middlewares, suite_metadata, preflight_info, context) -> None`

**Extracts:** Lines 359-365 (suite_loaded hook with deduplication)
```python
def _notify_middleware_suite_loaded(
    self,
    middlewares: list[Any],
    suite_metadata: list[dict[str, Any]],
    preflight_info: dict[str, Any],
    context: SuiteExecutionContext,
) -> None:
    """Notify middlewares of suite start (deduplicated across experiments)."""
    for mw in middlewares:
        key = id(mw)
        if hasattr(mw, "on_suite_loaded") and key not in context.notified_middlewares:
            mw.on_suite_loaded(suite_metadata, preflight_info)
            context.notified_middlewares[key] = mw
```

**Complexity Reduction:** ~8 → ~3

### 3.2 _notify_middleware_experiment_lifecycle()
**Signature:** `(self, middlewares, experiment, phase, payload=None) -> None`

**Extracts:** Lines 366-394 (experiment start/complete hooks)
```python
def _notify_middleware_experiment_lifecycle(
    self,
    middlewares: list[Any],
    experiment: ExperimentConfig,
    phase: Literal["start", "complete"],
    payload: dict[str, Any] | None = None,
) -> None:
    """Notify middlewares of experiment lifecycle events."""
    event_metadata = {
        "temperature": experiment.temperature,
        "max_tokens": experiment.max_tokens,
        "is_baseline": experiment.is_baseline,
    }

    for mw in middlewares:
        if phase == "start" and hasattr(mw, "on_experiment_start"):
            mw.on_experiment_start(experiment.name, event_metadata)
        elif phase == "complete" and hasattr(mw, "on_experiment_complete"):
            mw.on_experiment_complete(experiment.name, payload, event_metadata)
```

**Complexity Reduction:** ~10 → ~4

### 3.3 _run_baseline_comparison()
**Signature:** `(self, experiment, baseline_payload, payload, pack, defaults, middlewares, context) -> dict[str, Any] | None`

**Extracts:** Lines 396-413 (baseline comparison logic)
```python
def _run_baseline_comparison(
    self,
    experiment: ExperimentConfig,
    baseline_payload: dict[str, Any],
    current_payload: dict[str, Any],
    pack: dict[str, Any] | None,
    defaults: dict[str, Any],
    middlewares: list[Any],
    experiment_context: PluginContext,
) -> dict[str, Any] | None:
    """Execute baseline comparison plugins and return results."""
    # Early exit: only compare non-baseline experiments
    if experiment == self.suite.baseline:
        return None

    # Merge baseline plugin definitions (3 sources)
    comp_defs = self._merge_baseline_plugin_defs(experiment, pack, defaults)
    if not comp_defs:
        return None

    # Execute comparison plugins
    comparisons = {}
    for defn in comp_defs:
        plugin = create_baseline_plugin(defn, parent_context=experiment_context)
        diff = plugin.compare(baseline_payload, current_payload)
        if diff:
            comparisons[plugin.name] = diff

    if not comparisons:
        return None

    # Notify middlewares
    for mw in middlewares:
        if hasattr(mw, "on_baseline_comparison"):
            mw.on_baseline_comparison(experiment.name, comparisons)

    return comparisons
```

**Complexity Reduction:** ~18 → ~6

### 3.4 _merge_baseline_plugin_defs()
**Signature:** `(self, experiment, pack, defaults) -> list[dict[str, Any]]`

**Extracts:** Baseline plugin definition merging (lines 397-401)
```python
def _merge_baseline_plugin_defs(
    self,
    experiment: ExperimentConfig,
    pack: dict[str, Any] | None,
    defaults: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge baseline plugin definitions from defaults, pack, and experiment."""
    comp_defs = list(defaults.get("baseline_plugin_defs", []))

    if pack and pack.get("baseline_plugins"):
        comp_defs = list(pack.get("baseline_plugins", [])) + comp_defs

    if experiment.baseline_plugin_defs:
        comp_defs += experiment.baseline_plugin_defs

    return comp_defs
```

**Complexity Reduction:** ~5 → ~2

### 3.5 _run_single_experiment()
**Signature:** `(self, experiment, df, context, sink_factory) -> dict[str, Any]`

**Extracts:** Main experiment execution loop body (lines 325-413)
```python
def _run_single_experiment(
    self,
    experiment: ExperimentConfig,
    df: pd.DataFrame,
    context: SuiteExecutionContext,
    sink_factory: Callable | None,
) -> dict[str, Any]:
    """Execute a single experiment and return its result."""
    # Resolve configuration
    pack = self._resolve_pack(experiment, context)
    sinks = self._resolve_experiment_sinks(experiment, pack, context.defaults, sink_factory)

    # Build and configure runner
    runner = self.build_runner(experiment, {**context.defaults, "prompt_packs": context.prompt_packs, "prompt_pack": pack}, sinks)
    experiment_context = self._get_experiment_context(runner)
    middlewares = list(runner.llm_middlewares or [])

    # Notify middleware hooks
    suite_metadata = self._build_suite_metadata(context.experiments)
    self._notify_middleware_suite_loaded(middlewares, suite_metadata, context.preflight_info, context)
    self._notify_middleware_experiment_lifecycle(middlewares, experiment, "start")

    # Execute experiment
    payload = runner.run(df)

    # Track baseline
    if context.baseline_payload is None and (experiment.is_baseline or experiment == self.suite.baseline):
        context.baseline_payload = payload

    # Notify completion
    self._notify_middleware_experiment_lifecycle(middlewares, experiment, "complete", payload)

    # Run baseline comparison
    if context.baseline_payload:
        comparisons = self._run_baseline_comparison(
            experiment, context.baseline_payload, payload, pack, context.defaults, middlewares, experiment_context
        )
        if comparisons:
            payload["baseline_comparison"] = comparisons

    return {"payload": payload, "config": experiment}
```

**Complexity Reduction:** ~55 → ~12

**Estimated Effort:** 4-5 hours

---

## Phase 4: Final Orchestration Cleanup

**Goal:** Simplify the main run() method into a clear template.

### 4.1 Final run() Method
**Target Lines:** ~25-30 (down from 138)
**Target Complexity:** ~8-10 (down from 69)

```python
def run(
    self,
    df: pd.DataFrame,
    defaults: dict[str, Any] | None = None,
    sink_factory: Callable[[ExperimentConfig], list[ResultSink]] | None = None,
    preflight_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute all experiments in the suite.

    Orchestrates experiment execution with shared resources, middleware hooks,
    and baseline comparison across all experiments in the suite.

    Args:
        df: Input DataFrame for experiments
        defaults: Default configuration values
        sink_factory: Optional factory for creating experiment-specific sinks
        preflight_info: Optional metadata about the run environment

    Returns:
        Dictionary containing results for all experiments
    """
    # Phase 1: Setup suite execution context
    context = self._prepare_suite_context(defaults, preflight_info)

    # Phase 2: Execute each experiment
    for experiment in context.experiments:
        result = self._run_single_experiment(experiment, df, context, sink_factory)
        context.results[experiment.name] = result

    # Phase 3: Finalize and cleanup
    self._finalize_suite(context)

    return context.results
```

### 4.2 Add Navigation Comments
Add section comments similar to runner.py refactoring:
```python
# ============================================================================
# Suite Orchestration (Main Entry Point)
# ============================================================================

# ============================================================================
# Experiment Execution Helpers
# ============================================================================

# ============================================================================
# Configuration Resolution Helpers
# ============================================================================

# ============================================================================
# Middleware Lifecycle Helpers
# ============================================================================

# ============================================================================
# Baseline Comparison Helpers
# ============================================================================

# ============================================================================
# Supporting Classes
# ============================================================================
```

**Estimated Effort:** 1-2 hours

---

## Testing Strategy

### Characterization Tests (Phase 0)
**File:** `tests/test_suite_runner_characterization.py`

**Test Coverage:**
1. `test_run_result_structure()` - Verify suite result dictionary structure
2. `test_baseline_identification()` - Verify baseline is tracked correctly
3. `test_sink_resolution_priority()` - Verify experiment > pack > defaults > factory
4. `test_middleware_hook_ordering()` - Verify hook call sequence
5. `test_middleware_deduplication()` - Verify shared middlewares only get on_suite_loaded once
6. `test_baseline_comparison_execution()` - Verify comparison plugins run
7. `test_context_propagation_to_sinks()` - Verify PluginContext applied to sinks
8. `test_experiment_execution_order()` - Verify baseline runs first

### Safety Tests
**File:** `tests/test_suite_runner_safety.py`

**Edge Cases:**
1. Empty suite (no experiments)
2. No baseline experiment
3. Missing sink definitions (all layers)
4. Middleware without lifecycle hooks
5. No baseline comparison plugins

### Integration Tests (Existing)
**Ensure no regressions:**
- `test_suite_runner_executes_with_defaults_and_packs`
- `test_suite_runner_requires_prompts_when_missing`
- `test_suite_runner_builds_controls_and_early_stop`
- All 10 existing suite_runner tests

---

## Success Metrics

**Complexity Reduction:**
- run() method: 69 → ≤15 (target: ~85% reduction, matching runner.py)
- Total extracted methods: ~10-12 helpers

**Code Quality:**
- Lines in run(): 138 → ~25-30 (78% reduction)
- Test coverage: 85% → maintain or improve
- MyPy: Clean (no new type errors)

**Test Safety:**
- All 1276 existing tests passing
- 6+ new characterization tests
- 5+ new safety tests
- Zero behavioral changes

**Documentation:**
- Comprehensive docstrings for all helpers
- Navigation section comments
- Updated execution plan with discoveries

---

## Risk Mitigation

### High Risks
1. **Middleware Hook Ordering:** Must preserve exact hook call sequence
   - **Mitigation:** Characterization test for hook ordering
   - **Validation:** Log hook calls during refactoring

2. **Middleware Deduplication Logic:** `notified_middlewares` dict tracking
   - **Mitigation:** Dedicated test for deduplication behavior
   - **Validation:** Verify same middleware instance only gets on_suite_loaded once

3. **Baseline Comparison Timing:** Must run after baseline experiment completes
   - **Mitigation:** Test baseline tracking and comparison execution
   - **Validation:** Verify baseline_payload is set before comparisons

### Medium Risks
1. **Sink Resolution Priority:** 4-level fallback chain
   - **Mitigation:** Dedicated characterization test
   - **Validation:** Test each resolution path

2. **Context Propagation:** PluginContext must reach all sinks
   - **Mitigation:** Test context propagation
   - **Validation:** Verify security_level on sinks

### Low Risks
1. **Configuration Merging:** Already handled by ConfigMerger in build_runner()
2. **Type Safety:** Incremental refactoring maintains type hints

---

## Rollback Strategy

**If Tests Fail:**
1. Revert to previous commit
2. Analyze failure in isolation
3. Fix issue in smaller incremental change
4. Re-run full test suite

**Git Strategy:**
- Commit after each phase completion
- Use descriptive commit messages
- Never commit broken tests

---

## Timeline Estimate

| Phase | Description | Effort | Cumulative |
|-------|-------------|--------|------------|
| 0 | Safety Net Construction | 2-3 hours | 2-3 hours |
| 1 | Supporting Classes | 1 hour | 3-4 hours |
| 2 | Simple Helper Extractions | 2-3 hours | 5-7 hours |
| 3 | Complex Method Extractions | 4-5 hours | 9-12 hours |
| 4 | Final Orchestration Cleanup | 1-2 hours | 10-14 hours |
| **Total** | **Complete Refactoring** | **10-14 hours** | - |

**Note:** Timeline based on runner.py refactoring experience. Actual time may vary based on discovered edge cases.

---

## Comparison to runner.py Refactoring

**Similarities:**
- Similar complexity level (69 vs 73)
- Main orchestration method
- Configuration merging complexity
- Plugin lifecycle management
- State tracking requirements

**Differences:**
- Suite-level vs single-experiment orchestration
- Middleware deduplication logic (suite_runner specific)
- Baseline comparison logic (suite_runner specific)
- Sink resolution across multiple experiments
- Context propagation to multiple runners

**Lessons Learned from runner.py:**
1. ✅ Characterization tests are CRITICAL for safety
2. ✅ Dataclasses clarify state management
3. ✅ Early returns reduce nesting significantly
4. ✅ Clear method names improve discoverability
5. ✅ Incremental commits enable safe rollback
6. ✅ Security-first design (fail-closed validation)

**Expected Improvements:**
- Faster execution (learned patterns)
- Better test coverage from start
- Clearer helper method boundaries
- More comprehensive characterization tests

---

## Discovery Log

**2025-10-24: Initial Analysis**
- Identified complexity 69 in run() method
- Mapped 3 primary complexity drivers:
  1. Sink resolution (4-level conditionals)
  2. Middleware lifecycle hooks (deduplication tracking)
  3. Baseline comparison (nested plugin execution)
- Confirmed suite_runner.py has 85% coverage (good starting point)
- Found 10 existing integration tests (safety net)

---

## Notes

**Key Insights:**
1. The run() method is doing too much: orchestration, configuration, lifecycle, comparison
2. Middleware deduplication via `notified_middlewares` dict is a hidden complexity driver
3. Baseline comparison logic is deeply nested in the main loop (18 lines, complexity ~18)
4. Sink resolution follows the same pattern as config merging (experiment > pack > defaults)

**Potential Optimizations:**
1. Extract middleware lifecycle into dedicated helper class (similar to CheckpointManager pattern)
2. Consider BaselineComparisonManager class for comparison logic encapsulation
3. SinkResolver helper could unify sink resolution logic

**Open Questions:**
1. Should we extract MiddlewareLifecycleManager as a separate class?
2. Is there shared logic with build_runner() that could be further unified?
3. Should baseline comparison be a separate phase after all experiments complete?

**References:**
- runner.py refactoring: PR #10
- Execution plan: EXECUTION_PLAN_runner_refactor.md
- Characterization tests: tests/test_runner_characterization.py
- Refactoring summary: REFACTORING_COMPLETE_summary.md

---

**Status:** PLANNING COMPLETE - Ready for Phase 0 execution
