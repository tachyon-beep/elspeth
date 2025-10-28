# Baseline Flow Diagram: Suite Runner

**Purpose:** Document the exact baseline tracking and comparison timing logic in `suite_runner.py::run()` to prevent regressions during refactoring.

**Critical Insight:** Baseline tracking has an implicit timing dependency - `baseline_payload` must be set before comparisons run. This is enforced by experiment ordering (baseline first) rather than explicit checks.

---

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ Suite Execution Start                                           │
│ baseline_payload = None  ← Initial state                        │
│ results = {}                                                    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Build Experiment List (line 304-306)                           │
│ experiments = []                                                │
│ if suite.baseline:                                              │
│     experiments.append(suite.baseline)  ← Baseline FIRST        │
│ experiments.extend(other experiments)                           │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ FOR EACH experiment in experiments:                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │ Build Runner & Get Context           │
        │ Resolve Sinks                         │
        │ Notify middleware: on_experiment_start│
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │ Execute Experiment                    │
        │ payload = runner.run(df)              │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │ Is This Baseline?                     │
        │ (experiment.is_baseline OR            │
        │  experiment == suite.baseline)        │
        └───────────────────────────────────────┘
                            │
                 Yes ┌──────┴──────┐ No
                     │             │
                     ▼             ▼
    ┌────────────────────────┐  ┌──────────────────┐
    │ Track Baseline Payload │  │ Skip Tracking    │
    │ (line 377-378)         │  │                  │
    │                        │  │                  │
    │ if baseline_payload is │  │                  │
    │    None and (is_base   │  │                  │
    │    or == baseline):    │  │                  │
    │   baseline_payload =   │  │                  │
    │      payload           │  │                  │
    └────────────────────────┘  └──────────────────┘
                     │             │
                     └──────┬──────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │ Store Results                         │
        │ results[experiment.name] = {          │
        │   "payload": payload,                 │
        │   "config": experiment                │
        │ }                                     │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │ Notify middleware:                    │
        │ on_experiment_complete                │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────────────┐
        │ Should Run Baseline Comparison?              │
        │ (line 396)                                    │
        │                                               │
        │ if baseline_payload AND                       │
        │    experiment != suite.baseline:              │
        └───────────────────────────────────────────────┘
                            │
                 Yes ┌──────┴──────┐ No (Skip)
                     │             │
                     ▼             ▼
    ┌────────────────────────────┐  ┌──────────────────┐
    │ Run Baseline Comparison    │  │ Skip Comparison  │
    │ (lines 396-413)            │  │                  │
    │                            │  │ Reasons:         │
    │ 1. Merge plugin defs:      │  │ - No baseline    │
    │    defaults + pack + exp   │  │   payload yet    │
    │                            │  │ - This IS the    │
    │ 2. Create plugins          │  │   baseline exp   │
    │                            │  │                  │
    │ 3. Run comparisons         │  │                  │
    │                            │  │                  │
    │ 4. Store in payload &      │  │                  │
    │    results dict            │  │                  │
    │                            │  │                  │
    │ 5. Notify middleware:      │  │                  │
    │    on_baseline_comparison  │  │                  │
    └────────────────────────────┘  └──────────────────┘
                     │             │
                     └──────┬──────┘
                            │
                            ▼
            ┌───────────────────────────┐
            │ More Experiments?         │
            └───────────────────────────┘
                            │
                 Yes ┌──────┴──────┐ No
                     │             │
              (loop back)          ▼
                          ┌─────────────────┐
                          │ Notify middleware│
                          │ on_suite_complete│
                          └─────────────────┘
                                    │
                                    ▼
                          ┌─────────────────┐
                          │ Return results  │
                          └─────────────────┘
```

---

## Critical Code Locations

### 1. Baseline Tracking (Lines 377-378)
```python
if baseline_payload is None and (experiment.is_baseline or experiment == self.suite.baseline):
    baseline_payload = payload
```

**Key Points:**
- Uses `None` check to track FIRST baseline
- Supports two ways to identify baseline:
  1. `experiment.is_baseline = True`
  2. `experiment == self.suite.baseline` (object identity)
- Tracking happens AFTER experiment completes
- Once set, `baseline_payload` never changes (first baseline wins)

### 2. Baseline Comparison Guard (Line 396)
```python
if baseline_payload and experiment != self.suite.baseline:
    # ... run comparison plugins
```

**Key Points:**
- Two-part guard:
  1. `baseline_payload` must exist (baseline completed)
  2. `experiment != suite.baseline` (don't compare baseline to itself)
- Comparison runs AFTER experiment completes
- Comparison runs for EVERY non-baseline experiment (if baseline exists)

### 3. Experiment Ordering (Lines 304-306)
```python
experiments: list[ExperimentConfig] = []
if self.suite.baseline:
    experiments.append(self.suite.baseline)
experiments.extend(exp for exp in self.suite.experiments if exp != self.suite.baseline)
```

**Key Points:**
- **Baseline is ALWAYS first** in execution order
- Other experiments filtered to avoid duplicates
- This ordering is CRITICAL for timing - ensures baseline completes before comparisons
- Implicit contract: baseline must be in list position 0

---

## Timing Invariants

**INVARIANT 1: Baseline Tracking Happens Before Comparisons**
- Baseline experiment runs first (lines 304-306)
- Baseline payload tracked immediately after completion (line 377-378)
- Comparisons check for `baseline_payload` existence (line 396)
- **Result:** Comparisons can never run before baseline completes

**INVARIANT 2: Baseline Never Compares to Itself**
- Guard explicitly checks `experiment != suite.baseline` (line 396)
- Even if baseline were somehow last in list, guard prevents self-comparison
- **Result:** Baseline experiment result never includes `baseline_comparison` key

**INVARIANT 3: First Baseline Wins**
- `if baseline_payload is None` means only first baseline is tracked
- If multiple experiments have `is_baseline=True`, only first sets `baseline_payload`
- **Result:** Consistent baseline reference even with malformed config

**INVARIANT 4: All Non-Baseline Experiments Get Compared**
- Every experiment after baseline (where `baseline_payload` exists) runs comparison
- No filtering - ALL non-baseline experiments compared
- **Result:** Consistent comparison behavior across all variants

---

## Edge Cases & Behaviors

### Case 1: No Baseline Experiment
```python
baseline_payload = None  # Never set
# All experiments skip comparison (baseline_payload is None)
```
**Result:** No comparisons run, no errors

### Case 2: Baseline is Last Experiment (Malformed Config)
```python
# Code at lines 304-306 prevents this!
# Baseline is ALWAYS moved to front
```
**Result:** Ordering code prevents this edge case

### Case 3: Multiple Baselines (Malformed Config)
```python
baseline_payload = None
# First baseline: is None → set baseline_payload
# Second baseline: is NOT None → skip tracking (first wins)
# Second baseline: != suite.baseline → runs comparison!
```
**Result:** First baseline tracked, subsequent "baselines" compared to it

### Case 4: Baseline Experiment Fails
```python
# runner.run(df) returns payload with empty results or failures
# baseline_payload still gets set (no exception handling)
# Comparisons run against failed baseline
```
**Result:** Comparisons proceed even if baseline failed (potentially empty comparison)

---

## Test Coverage

**Existing Tests (test_suite_runner_middleware_hooks.py):**
1. ✅ `test_baseline_comparison_only_after_baseline_completes` - Timing dependency
2. ✅ `test_middleware_hook_call_sequence_basic` - Baseline first in sequence

**Additional Tests Needed (in test_suite_runner_baseline_flow.py):**
1. ✅ `test_baseline_tracked_on_first_baseline_only` - First baseline wins
2. ✅ `test_baseline_comparison_skipped_when_no_baseline` - No baseline edge case
3. ✅ `test_baseline_never_compares_to_itself` - Self-comparison guard
4. ✅ `test_all_non_baseline_experiments_get_compared` - Comprehensive comparison
5. ✅ `test_baseline_ordering_enforced` - Baseline always first

---

## Refactoring Guidance

**When extracting baseline logic, preserve these behaviors:**

1. **Maintain experiment ordering** - Baseline must be first
2. **Preserve None-check pattern** - `baseline_payload is None` for first-tracking
3. **Keep dual-guard pattern** - Both `baseline_payload` existence AND `!= baseline` check
4. **Don't add early-exit logic** - Let all experiments run (even after baseline set)

**Recommended extraction:**
```python
def _should_track_baseline(
    self,
    experiment: ExperimentConfig,
    baseline_payload: dict | None
) -> bool:
    """Check if this experiment should be tracked as baseline."""
    return baseline_payload is None and (
        experiment.is_baseline or experiment == self.suite.baseline
    )

def _should_run_baseline_comparison(
    self,
    experiment: ExperimentConfig,
    baseline_payload: dict | None,
) -> bool:
    """Check if baseline comparison should run for this experiment."""
    return baseline_payload is not None and experiment != self.suite.baseline
```

---

## Security & Data Integrity Considerations

**Baseline Payload Security:**
- Baseline payload contains full experiment results (including sensitive data)
- Stored in memory for entire suite execution
- Passed to comparison plugins (potential data exposure)
- **Mitigation:** Security level enforcement on comparison plugins

**Baseline Immutability:**
- Once `baseline_payload` is set, it never changes
- No deep-copy - same dict reference used for all comparisons
- Comparison plugins could mutate baseline payload
- **Risk:** Medium - comparison plugins trusted, but no immutability enforcement

**Comparison Plugin Isolation:**
- Each comparison plugin receives same baseline_payload reference
- Plugins could interfere with each other via mutation
- No error handling if comparison plugin fails
- **Risk:** Medium - one failing plugin could crash entire suite

---

## Performance Characteristics

**Memory:**
- `baseline_payload` held in memory for full suite duration
- Could be large (thousands of rows × metadata)
- Not released until suite complete
- **Impact:** O(n) memory where n = baseline result size

**Comparison Plugin Execution:**
- Runs for EVERY non-baseline experiment
- No caching of comparison results
- Plugins re-execute even if comparing same data
- **Impact:** O(m × p) where m = experiments, p = comparison plugins

---

## Documentation References

**Related Files:**
- `suite_runner.py`: Lines 281-419 (run method)
- `test_suite_runner_middleware_hooks.py`: Timing tests
- `EXECUTION_PLAN_suite_runner_refactor.md`: Refactoring plan

**Related Behaviors:**
- Middleware `on_baseline_comparison` hooks (lines 411-413)
- Baseline plugin definitions merging (lines 397-401)
- Plugin context propagation (lines 343-357)

---

**Status:** DOCUMENTED - Ready for refactoring reference
**Last Updated:** 2025-10-24
**Risk Level:** HIGH (timing dependency, implicit ordering contract)
