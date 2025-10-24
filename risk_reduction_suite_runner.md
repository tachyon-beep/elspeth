# Risk Reduction Activities: Suite Runner Refactoring

**Target:** `suite_runner.py::run()` (complexity 69)
**Strategy:** De-risk the refactoring BEFORE writing code

---

## Overview

Based on lessons learned from the successful runner.py refactoring (PR #10), this document outlines proactive risk reduction activities to execute BEFORE Phase 0 begins.

**Key Insight from runner.py:** Characterization tests alone aren't enough for complex orchestration code. We need to:
1. **Understand** current behavior deeply
2. **Document** hidden assumptions
3. **Trace** execution flows
4. **Validate** edge cases

---

## High-Risk Areas in suite_runner.py

### 1. Middleware Hook Deduplication (HIGHEST RISK)
**Location:** Lines 359-365
**Complexity Driver:** State tracking via `notified_middlewares` dict

**Risk:** The deduplication logic prevents the same middleware instance from receiving `on_suite_loaded()` multiple times when shared across experiments. This is subtle state management that's easy to break.

**Current Code:**
```python
for mw in middlewares:
    key = id(mw)
    if hasattr(mw, "on_suite_loaded") and key not in notified_middlewares:
        mw.on_suite_loaded(suite_metadata, preflight_info)
        notified_middlewares[key] = mw
        suite_notified.append(mw)
```

**Why Risky:**
- Uses Python `id()` for object identity
- Stateful tracking across experiment loop iterations
- Multiple experiments may share middleware instances
- Hook must fire exactly once per unique instance

### 2. Baseline Comparison Timing (HIGH RISK)
**Location:** Lines 396-413
**Complexity Driver:** Conditional execution based on baseline_payload availability

**Risk:** Baseline comparisons must only run AFTER the baseline experiment completes. The timing dependency is implicit.

**Current Code:**
```python
if baseline_payload and experiment != self.suite.baseline:
    # ... comparison logic
```

**Why Risky:**
- Depends on baseline_payload being set first
- Baseline experiment must be in experiments list
- Comparison skipped for baseline itself
- Plugin definitions merged from 3 sources

### 3. Sink Resolution Priority (MEDIUM RISK)
**Location:** Lines 329-336
**Complexity Driver:** 4-level nested conditionals

**Risk:** Sink resolution follows experiment > pack > defaults > factory priority. Each path has different instantiation logic.

**Why Risky:**
- 4 different code paths to same end result
- Short-circuit evaluation order matters
- Factory fallback requires callable check
- Each path calls different sources

---

## Risk Reduction Activities

### Activity 1: Middleware Hook Call Tracer (2 hours)

**Goal:** Create a test fixture that captures ALL middleware hook calls with full context.

**Implementation:**
```python
# tests/fixtures/middleware_tracer.py
class MiddlewareHookTracer:
    """Captures all middleware hook calls for verification."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def on_suite_loaded(self, suite_metadata, preflight_info):
        self.calls.append({
            "hook": "on_suite_loaded",
            "instance_id": id(self),
            "suite_metadata": suite_metadata,
            "preflight_info": preflight_info,
        })

    def on_experiment_start(self, name, metadata):
        self.calls.append({
            "hook": "on_experiment_start",
            "instance_id": id(self),
            "experiment": name,
            "metadata": metadata,
        })

    def on_experiment_complete(self, name, payload, metadata):
        self.calls.append({
            "hook": "on_experiment_complete",
            "instance_id": id(self),
            "experiment": name,
            "metadata": metadata,
        })

    def on_baseline_comparison(self, name, comparisons):
        self.calls.append({
            "hook": "on_baseline_comparison",
            "instance_id": id(self),
            "experiment": name,
            "comparisons": comparisons,
        })

    def on_suite_complete(self):
        self.calls.append({
            "hook": "on_suite_complete",
            "instance_id": id(self),
        })

    def get_call_sequence(self) -> list[str]:
        """Return hook names in call order."""
        return [call["hook"] for call in self.calls]

    def get_suite_loaded_count(self) -> int:
        """Count on_suite_loaded calls (should be 1 for shared instances)."""
        return len([c for c in self.calls if c["hook"] == "on_suite_loaded"])
```

**Usage in Tests:**
```python
def test_middleware_hook_call_sequence():
    """INVARIANT: Middleware hooks fire in correct order."""
    tracer = MiddlewareHookTracer()

    suite = ExperimentSuite(
        baseline=ExperimentConfig(name="baseline", is_baseline=True),
        experiments=[ExperimentConfig(name="exp1")],
    )

    defaults = {
        "llm_middlewares": [tracer],
        "prompt_system": "Test",
        "prompt_template": "{{ text }}",
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # Verify exact sequence
    expected = [
        "on_suite_loaded",      # Once at start
        "on_experiment_start",   # Baseline start
        "on_experiment_complete", # Baseline complete
        "on_experiment_start",   # Exp1 start
        "on_experiment_complete", # Exp1 complete
        "on_baseline_comparison", # Exp1 baseline comparison
        "on_suite_complete",     # Once at end
    ]

    assert tracer.get_call_sequence() == expected
    assert tracer.get_suite_loaded_count() == 1  # Only once!
```

**Deliverables:**
- MiddlewareHookTracer fixture in conftest.py
- Test documenting exact hook sequence
- Test verifying shared middleware deduplication

**Value:** Provides executable specification of middleware hook behavior.

---

### Activity 2: Sink Resolution Path Documentation (1 hour)

**Goal:** Document and test all 4 sink resolution paths with examples.

**Documentation:**
```markdown
# Sink Resolution Priority (suite_runner.py)

Priority order (first match wins):

1. **Experiment-level sink_defs** (highest priority)
   - Location: `experiment.sink_defs`
   - Use case: Experiment-specific sinks
   - Example: A/B test with different output formats

2. **Prompt pack sinks**
   - Location: `pack["sinks"]`
   - Use case: Pack-specific output requirements
   - Example: Benchmark pack requires CSV + JSON

3. **Suite defaults sink_defs**
   - Location: `defaults["sink_defs"]`
   - Use case: Organization-wide standard outputs
   - Example: All suites log to audit sink

4. **Sink factory callback** (lowest priority)
   - Location: `sink_factory(experiment)`
   - Use case: Dynamic sink creation per experiment
   - Example: Create sink based on experiment metadata
   - Fallback: If no factory, use `self.sinks`

## Testing All Paths

| Test Case | Path | Configuration |
|-----------|------|---------------|
| test_sink_resolution_experiment_wins | 1 | experiment.sink_defs = [csv] |
| test_sink_resolution_pack_fallback | 2 | pack["sinks"] = [json] |
| test_sink_resolution_defaults_fallback | 3 | defaults["sink_defs"] = [audit] |
| test_sink_resolution_factory_fallback | 4 | sink_factory = lambda e: [custom] |
| test_sink_resolution_self_sinks_fallback | 4 | (no factory, use self.sinks) |
```

**Test Implementation:**
```python
def test_sink_resolution_all_paths():
    """INVARIANT: Sink resolution follows experiment > pack > defaults > factory priority."""

    # Path 1: Experiment wins
    experiment_sink = CollectingSink()
    experiment = ExperimentConfig(
        name="exp1",
        sink_defs=[{"plugin": "csv_file", "options": {"path": "/tmp/exp.csv"}}],
    )
    # ... verify experiment_sink used

    # Path 2: Pack wins when experiment has no sinks
    pack_sink = CollectingSink()
    pack = {"sinks": [{"plugin": "json_file", "options": {"path": "/tmp/pack.json"}}]}
    # ... verify pack_sink used

    # Path 3: Defaults win when no experiment or pack
    defaults_sink = CollectingSink()
    defaults = {"sink_defs": [{"plugin": "audit", "options": {}}]}
    # ... verify defaults_sink used

    # Path 4: Factory used when all else fails
    factory_sink = CollectingSink()
    sink_factory = lambda exp: [factory_sink]
    # ... verify factory_sink used

    # Path 5: self.sinks used when no factory
    runner = ExperimentSuiteRunner(suite, llm, [fallback_sink])
    # ... verify fallback_sink used
```

**Deliverables:**
- Sink resolution documentation in execution plan
- 5 tests covering all resolution paths
- Comment in code documenting priority order

**Value:** Eliminates guesswork about sink resolution behavior.

---

### Activity 3: Baseline Comparison Flow Diagram (30 minutes)

**Goal:** Visualize baseline tracking and comparison timing.

**Diagram:**
```
Suite Execution Flow: Baseline Tracking & Comparison

┌─────────────────────────────────────────────────────┐
│ Suite Start                                         │
│ baseline_payload = None                             │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│ Experiment Loop (baseline first by design)         │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────┐
        │ Run Experiment            │
        │ payload = runner.run(df)  │
        └───────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────┐
        │ Is this baseline?         │
        │ (is_baseline OR ==        │
        │  suite.baseline)          │
        └───────────────────────────┘
                        │
             Yes ┌──────┴──────┐ No
                 │             │
                 ▼             ▼
    ┌─────────────────┐    ┌──────────────────┐
    │ Track Baseline  │    │ Skip Tracking    │
    │ baseline_       │    │                  │
    │ payload = payload│   │                  │
    └─────────────────┘    └──────────────────┘
                 │             │
                 └──────┬──────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │ Run Baseline Comparison?      │
        │ (baseline_payload exists AND  │
        │  experiment != suite.baseline)│
        └───────────────────────────────┘
                        │
             Yes ┌──────┴──────┐ No
                 │             │
                 ▼             ▼
    ┌─────────────────┐    ┌──────────────────┐
    │ Execute         │    │ Skip Comparison  │
    │ Comparison      │    │                  │
    │ Plugins         │    │                  │
    └─────────────────┘    └──────────────────┘
                 │             │
                 └──────┬──────┘
                        │
                        ▼
            ┌───────────────────┐
            │ More experiments? │
            └───────────────────┘
                        │
                 Yes ┌──┴──┐ No
                     │     │
                     ▼     ▼
              (loop back) (exit)

KEY INSIGHTS:
1. baseline_payload set on FIRST baseline experiment
2. Comparisons only run if baseline_payload exists
3. Baseline experiment NEVER compares to itself
4. Experiments list ordered: baseline first, then others (line 304-306)
```

**Characterization Test:**
```python
def test_baseline_comparison_timing():
    """INVARIANT: Baseline comparisons only run after baseline completes."""

    comparison_plugin = CountingComparisonPlugin()

    suite = ExperimentSuite(
        baseline=ExperimentConfig(name="baseline", is_baseline=True),
        experiments=[
            ExperimentConfig(name="exp1"),
            ExperimentConfig(name="exp2"),
        ],
    )

    defaults = {
        "prompt_system": "Test",
        "prompt_template": "{{ text }}",
        "baseline_plugin_defs": [{"plugin": "counting_comparison"}],
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # Baseline experiment should NOT have comparison
    assert "baseline_comparison" not in results["baseline"]["payload"]

    # Non-baseline experiments SHOULD have comparison
    assert "baseline_comparison" in results["exp1"]["payload"]
    assert "baseline_comparison" in results["exp2"]["payload"]

    # Comparison plugin should run exactly twice (exp1, exp2)
    assert comparison_plugin.call_count == 2
```

**Deliverables:**
- Flow diagram in execution plan
- Test verifying baseline tracking
- Test verifying comparison timing

**Value:** Makes implicit baseline logic explicit and testable.

---

### Activity 4: Existing Test Analysis with Verbose Logging (1 hour)

**Goal:** Run existing tests with enhanced logging to understand current behavior patterns.

**Implementation:**
```python
# Add temporary debug logging to suite_runner.py::run()
import logging
logger = logging.getLogger(__name__)

def run(self, df, defaults=None, sink_factory=None, preflight_info=None):
    """Execute all experiments in suite."""
    logger.info(f"=== Suite Execution Start ===")
    logger.info(f"Defaults keys: {defaults.keys() if defaults else 'None'}")
    logger.info(f"Sink factory: {'provided' if sink_factory else 'None'}")

    # ... existing code with strategic logging:

    for experiment in experiments:
        logger.info(f"--- Experiment: {experiment.name} ---")
        logger.info(f"  is_baseline: {experiment.is_baseline}")
        logger.info(f"  sink_defs: {experiment.sink_defs is not None}")

        # After sink resolution
        logger.info(f"  Resolved {len(sinks)} sinks")

        # After middleware notification
        logger.info(f"  Notified {len(suite_notified)} middlewares for suite_loaded")
        logger.info(f"  Total notified_middlewares: {len(notified_middlewares)}")

        # After baseline tracking
        if baseline_payload is None and ...:
            logger.info(f"  *** BASELINE TRACKED: {experiment.name} ***")

        # After comparison
        if baseline_payload and experiment != self.suite.baseline:
            logger.info(f"  Ran {len(comparisons)} comparison plugins")
```

**Test Execution:**
```bash
# Run with verbose logging
pytest tests/test_suite_runner*.py -v -s --log-cli-level=INFO 2>&1 | tee suite_runner_behavior_log.txt
```

**Analysis:**
1. Review log for hook call patterns
2. Identify sink resolution path distributions
3. Verify baseline tracking timing
4. Check middleware deduplication behavior

**Deliverables:**
- Annotated log file with observations
- Updated risk assessment based on findings
- List of edge cases discovered

**Value:** Empirical data about current behavior patterns.

---

### Activity 5: Edge Case Catalog (1 hour)

**Goal:** Document and test edge cases that could break during refactoring.

**Edge Cases:**

| Case | Scenario | Expected Behavior | Test Name |
|------|----------|-------------------|-----------|
| EC1 | Empty suite | Returns empty results dict | `test_empty_suite` |
| EC2 | No baseline | baseline_payload stays None, no comparisons | `test_no_baseline` |
| EC3 | Baseline not first | Still tracked correctly | `test_baseline_not_first_in_list` |
| EC4 | Shared middleware | on_suite_loaded called once per instance | `test_shared_middleware_dedup` |
| EC5 | Multiple baselines | First one wins | `test_multiple_baselines` |
| EC6 | No comparison plugins | No comparisons run | `test_no_comparison_plugins` |
| EC7 | Middleware without hooks | No errors, simply skipped | `test_middleware_without_hooks` |
| EC8 | All sinks from factory | Factory called for each experiment | `test_all_sinks_from_factory` |

**Test Implementation:**
```python
# tests/test_suite_runner_safety.py

def test_empty_suite():
    """SAFETY: Empty suite returns empty results."""
    suite = ExperimentSuite(baseline=None, experiments=[])
    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    results = runner.run(pd.DataFrame([{"text": "test"}]))
    assert results == {}

def test_shared_middleware_deduplication():
    """SAFETY: Shared middleware instance only gets on_suite_loaded once."""
    tracer = MiddlewareHookTracer()

    suite = ExperimentSuite(
        baseline=None,
        experiments=[
            ExperimentConfig(name="exp1"),
            ExperimentConfig(name="exp2"),
        ],
    )

    # Same middleware instance shared across experiments
    defaults = {
        "llm_middlewares": [tracer],
        "prompt_system": "Test",
        "prompt_template": "{{ text }}",
    }

    runner = ExperimentSuiteRunner(suite, SimpleLLM(), [])
    runner.run(pd.DataFrame([{"text": "test"}]), defaults)

    # Critical: on_suite_loaded should be called EXACTLY ONCE
    assert tracer.get_suite_loaded_count() == 1

    # But on_experiment_start called twice (once per experiment)
    assert len([c for c in tracer.calls if c["hook"] == "on_experiment_start"]) == 2
```

**Deliverables:**
- 8 edge case safety tests
- Updated risk assessment
- Documentation of edge case handling

**Value:** Prevents regressions in corner cases.

---

### Activity 6: Refactoring Risk Assessment Matrix (30 minutes)

**Goal:** Quantify and prioritize refactoring risks.

**Risk Matrix:**

| Risk | Impact | Probability | Mitigation | Residual Risk |
|------|--------|-------------|------------|---------------|
| Middleware hook ordering breaks | CRITICAL | Medium | Activity 1: Hook tracer tests | Low |
| Deduplication logic breaks | CRITICAL | Medium | Activity 1: Dedup test | Low |
| Baseline timing breaks | HIGH | Low | Activity 3: Flow diagram + test | Very Low |
| Sink resolution priority wrong | HIGH | Low | Activity 2: All paths tested | Very Low |
| Context propagation broken | MEDIUM | Low | Existing tests + new safety test | Very Low |
| Edge case regression | MEDIUM | Medium | Activity 5: Edge case catalog | Low |
| Performance regression | LOW | Very Low | Existing benchmarks | Very Low |

**Scoring:**
- Impact: CRITICAL (10), HIGH (7), MEDIUM (5), LOW (2)
- Probability: High (70%), Medium (40%), Low (15%), Very Low (5%)
- Risk Score = Impact × Probability

**Top 3 Risks by Score:**
1. Middleware deduplication breaks: 10 × 0.40 = 4.0
2. Hook ordering breaks: 10 × 0.40 = 4.0
3. Baseline timing breaks: 7 × 0.15 = 1.05

**Mitigation Strategy:**
Focus Activities 1 and 3 (hook tracer + baseline flow) as highest value risk reduction.

**Deliverables:**
- Risk matrix in execution plan
- Prioritized mitigation activities
- Updated Phase 0 plan

**Value:** Data-driven prioritization of safety activities.

---

## Summary

### Total Effort: ~6-7 hours

| Activity | Effort | Value | Priority |
|----------|--------|-------|----------|
| 1. Middleware Hook Tracer | 2 hours | CRITICAL | P0 (Must Do) |
| 2. Sink Resolution Docs | 1 hour | HIGH | P0 (Must Do) |
| 3. Baseline Flow Diagram | 30 min | HIGH | P0 (Must Do) |
| 4. Verbose Logging Analysis | 1 hour | MEDIUM | P1 (Should Do) |
| 5. Edge Case Catalog | 1 hour | MEDIUM | P1 (Should Do) |
| 6. Risk Assessment Matrix | 30 min | LOW | P2 (Nice to Have) |

### Recommended Execution Order:

**Day 0: Risk Reduction (6-7 hours)**
1. Activity 6: Risk Assessment Matrix (30 min) - Framework
2. Activity 1: Middleware Hook Tracer (2 hours) - Highest risk
3. Activity 3: Baseline Flow Diagram (30 min) - Second highest risk
4. Activity 2: Sink Resolution Docs (1 hour) - Third highest risk
5. Activity 5: Edge Case Catalog (1 hour) - Safety net
6. Activity 4: Verbose Logging Analysis (1 hour) - Optional validation

**Day 1: Phase 0 - Safety Net Construction**
- Leverage outputs from Activities 1-5
- Build comprehensive characterization tests
- Capture baseline metrics

### Success Criteria:

✅ All risk reduction activities complete
✅ Middleware hook behavior fully documented and tested
✅ All 4 sink resolution paths tested
✅ Baseline comparison timing validated
✅ 8+ edge cases documented and tested
✅ Risk matrix shows all risks mitigated to Low or Very Low

---

## Lessons from runner.py Applied

**What Worked:**
1. ✅ Characterization tests caught regressions
2. ✅ Incremental commits enabled safe rollback
3. ✅ Security-first design improved quality
4. ✅ Clear helper names improved discoverability

**What We'll Improve:**
1. ✅ More comprehensive edge case testing (Activity 5)
2. ✅ Visual flow diagrams for complex logic (Activity 3)
3. ✅ Explicit hook behavior documentation (Activity 1)
4. ✅ Empirical behavior analysis before refactoring (Activity 4)

**New Insights:**
- Middleware deduplication is suite_runner-specific complexity
- Baseline comparison timing dependency isn't obvious from code
- Sink resolution has 5 paths (not 4 - factory + self.sinks fallback)
- Hook call sequence is an implicit contract with middleware authors

---

**Status:** RISK REDUCTION PLAN COMPLETE - Ready for execution
